from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

from fastmcp import FastMCP

from parks_canada_booking_mcp.db import (
    db_cursor,
    dates_in_stay,
    decode_json_fields,
    is_in_operating_season,
    reservation_conflicts,
    row_to_dict,
)
from parks_canada_booking_mcp.settings import settings

mcp = FastMCP("parks-canada-booking")


def validate_party_and_equipment(party_size: int, equipment_type: str) -> str:
    if party_size < 1:
        raise ValueError("party_size must be at least 1")
    normalized = equipment_type.strip().lower()
    allowed = {"tent", "rv", "trailer", "roofed"}
    if normalized not in allowed:
        raise ValueError("equipment_type must be one of: tent, RV, trailer, roofed")
    return normalized


def site_record(cursor: Any, site_id: int) -> dict[str, Any]:
    cursor.execute(
        """
         SELECT s.*, c.name AS campground_name, c.park_id, c.operating_season_start, c.operating_season_end,
             p.name AS park_name, p.province
        FROM sites s
        JOIN campgrounds c ON c.id = s.campground_id
        JOIN parks p ON p.id = c.park_id
        WHERE s.id = ?
        """,
        (site_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Site {site_id} not found")
    return decode_json_fields(row_to_dict(row))


def accommodation_record(cursor: Any, accommodation_id: int) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT a.*, c.name AS campground_name, p.name AS park_name, p.province
        FROM accommodations a
        LEFT JOIN campgrounds c ON c.id = a.campground_id
        JOIN parks p ON p.id = a.park_id
        WHERE a.id = ?
        """,
        (accommodation_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Accommodation {accommodation_id} not found")
    return decode_json_fields(row_to_dict(row))


@mcp.tool()
def search_parks(query: str, province: str | None = None, park_type: str | None = None) -> list[dict[str, Any]]:
    """Find Parks Canada demo parks by name, province, natural region, or park type."""
    if not query.strip() and not province and not park_type:
        raise ValueError("Provide a query, province, or park_type")
    conditions: list[str] = []
    parameters: list[str] = []
    if query.strip():
        like = f"%{query.strip()}%"
        conditions.append("(p.name LIKE ? OR p.province LIKE ? OR p.natural_region LIKE ? OR p.description LIKE ?)")
        parameters.extend([like] * 4)
    if province:
        conditions.append("p.province LIKE ?")
        parameters.append(f"%{province.strip()}%")
    if park_type:
        conditions.append("p.park_type = ?")
        parameters.append(park_type.strip().lower())
    with db_cursor() as cursor:
        cursor.execute(
            "SELECT p.*, COUNT(c.id) AS campground_count FROM parks p LEFT JOIN campgrounds c ON c.park_id = p.id WHERE "
            + " AND ".join(conditions)
            + " GROUP BY p.id ORDER BY p.name LIMIT 50",
            parameters,
        )
        return [row_to_dict(row) for row in cursor.fetchall()]


@mcp.tool()
def browse_availability(
    location: str,
    month: str,
    party_size: int = 1,
    equipment_type: str = "tent",
) -> dict[str, Any]:
    """Show when each matching site or accommodation is available during a YYYY-MM month.

    Use this before asking a guest to choose dates. It returns continuous available date ranges
    for each matching unit, including its operating season and nightly price.
    """
    normalized_equipment = validate_party_and_equipment(party_size, equipment_type)
    try:
        start = datetime.strptime(f"{month}-01", "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("month must use YYYY-MM format") from exc
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    if not location.strip():
        raise ValueError("location must not be empty")

    all_dates = []
    current = start
    while current < end:
        all_dates.append(current)
        current = current.fromordinal(current.toordinal() + 1)
    location_like = f"%{location.strip()}%"
    units: list[dict[str, Any]] = []

    with db_cursor() as cursor:
        if normalized_equipment == "roofed":
            cursor.execute(
                """
                SELECT a.*, c.name AS campground_name, p.name AS park_name
                FROM accommodations a
                LEFT JOIN campgrounds c ON c.id = a.campground_id
                JOIN parks p ON p.id = a.park_id
                WHERE (p.name LIKE ? OR c.name LIKE ?) AND a.sleeps_max >= ?
                ORDER BY p.name, a.name
                """,
                (location_like, location_like, party_size),
            )
            candidates = [decode_json_fields(row_to_dict(row)) for row in cursor.fetchall()]
            for unit in candidates:
                available_dates = [
                    day.isoformat()
                    for day in all_dates
                    if not reservation_conflicts(
                        cursor,
                        accommodation_id=unit["id"],
                        arrival_date=day.isoformat(),
                        departure_date=day.fromordinal(day.toordinal() + 1).isoformat(),
                    )
                ]
                units.append({
                    "unit_kind": "accommodation",
                    "accommodation_id": unit["id"],
                    "name": unit["name"],
                    "park": unit["park_name"],
                    "campground": unit["campground_name"],
                    "price_per_night_cad": unit["price_per_night_cad"],
                    "available_date_ranges": date_ranges(available_dates),
                })
        else:
            cursor.execute(
                """
                SELECT s.*, c.name AS campground_name, c.operating_season_start, c.operating_season_end,
                       p.name AS park_name
                FROM sites s
                JOIN campgrounds c ON c.id = s.campground_id
                JOIN parks p ON p.id = c.park_id
                WHERE (p.name LIKE ? OR c.name LIKE ?) AND s.max_party_size >= ?
                ORDER BY p.name, c.name, s.site_number
                """,
                (location_like, location_like, party_size),
            )
            candidates = [decode_json_fields(row_to_dict(row)) for row in cursor.fetchall()]
            for unit in candidates:
                if normalized_equipment not in {entry.lower() for entry in unit["equipment_allowed"]}:
                    continue
                available_dates = [
                    day.isoformat()
                    for day in all_dates
                    if is_in_operating_season(day.isoformat()[5:], unit["operating_season_start"], unit["operating_season_end"])
                    and not reservation_conflicts(
                        cursor,
                        site_id=unit["id"],
                        arrival_date=day.isoformat(),
                        departure_date=day.fromordinal(day.toordinal() + 1).isoformat(),
                    )
                ]
                units.append({
                    "unit_kind": "site",
                    "site_id": unit["id"],
                    "name": f"Site {unit['site_number']}",
                    "park": unit["park_name"],
                    "campground": unit["campground_name"],
                    "type": unit["site_type"],
                    "price_per_night_cad": unit["price_per_night_cad"],
                    "available_date_ranges": date_ranges(available_dates),
                })
    return {"location": location, "month": month, "party_size": party_size, "equipment_type": equipment_type, "units": units}


def date_ranges(available_dates: list[str]) -> list[dict[str, str]]:
    """Compress individual available nights into readable, contiguous date ranges."""
    if not available_dates:
        return []
    dates = [datetime.strptime(value, "%Y-%m-%d").date() for value in available_dates]
    ranges: list[dict[str, str]] = []
    range_start = range_end = dates[0]
    for day in dates[1:]:
        if day.toordinal() == range_end.toordinal() + 1:
            range_end = day
            continue
        ranges.append({"start_date": range_start.isoformat(), "end_date": range_end.isoformat()})
        range_start = range_end = day
    ranges.append({"start_date": range_start.isoformat(), "end_date": range_end.isoformat()})
    return ranges


@mcp.tool()
def search_availability(
    location: str,
    arrival_date: str,
    departure_date: str,
    party_size: int,
    equipment_type: str,
    electrical_hookup: bool | None = None,
    pet_friendly: bool | None = None,
    accessible: bool | None = None,
) -> list[dict[str, Any]]:
    """Return bookable demo campsites or roofed accommodations for every requested night.

    location matches park or campground names. equipment_type supports tent, RV, trailer, or roofed.
    Optional filters require an electrical hookup, pet-friendly unit, or accessible unit.
    """
    normalized_equipment = validate_party_and_equipment(party_size, equipment_type)
    stay_dates = dates_in_stay(arrival_date, departure_date)
    if not location.strip():
        raise ValueError("location must not be empty")
    location_like = f"%{location.strip()}%"
    results: list[dict[str, Any]] = []

    with db_cursor() as cursor:
        if normalized_equipment == "roofed":
            cursor.execute(
                """
                SELECT a.*, c.name AS campground_name, p.name AS park_name, p.province
                FROM accommodations a
                LEFT JOIN campgrounds c ON c.id = a.campground_id
                JOIN parks p ON p.id = a.park_id
                WHERE (p.name LIKE ? OR c.name LIKE ?) AND a.sleeps_max >= ?
                ORDER BY p.name, a.name
                """,
                (location_like, location_like, party_size),
            )
            for row in cursor.fetchall():
                unit = decode_json_fields(row_to_dict(row))
                if pet_friendly is not None and unit["is_pet_friendly"] != pet_friendly:
                    continue
                if accessible is not None and unit["is_accessible"] != accessible:
                    continue
                if reservation_conflicts(cursor, accommodation_id=unit["id"], arrival_date=arrival_date, departure_date=departure_date):
                    continue
                results.append({
                    "unit_kind": "accommodation",
                    "accommodation_id": unit["id"],
                    "name": unit["name"],
                    "type": unit["accommodation_type"],
                    "park": unit["park_name"],
                    "campground": unit["campground_name"],
                    "price_per_night_cad": unit["price_per_night_cad"],
                    "total_price_cad": round(unit["price_per_night_cad"] * len(stay_dates), 2),
                    "available_dates": stay_dates,
                    "amenities": unit["amenities"],
                    "pet_friendly": unit["is_pet_friendly"],
                    "accessible": unit["is_accessible"],
                })
            return results

        cursor.execute(
            """
            SELECT s.*, c.name AS campground_name, c.operating_season_start, c.operating_season_end,
                   p.name AS park_name, p.province
            FROM sites s
            JOIN campgrounds c ON c.id = s.campground_id
            JOIN parks p ON p.id = c.park_id
            WHERE (p.name LIKE ? OR c.name LIKE ?) AND s.max_party_size >= ?
            ORDER BY p.name, c.name, s.site_number
            """,
            (location_like, location_like, party_size),
        )
        for row in cursor.fetchall():
            unit = decode_json_fields(row_to_dict(row))
            allowed_equipment = {entry.lower() for entry in unit["equipment_allowed"]}
            if normalized_equipment not in allowed_equipment:
                continue
            if electrical_hookup is not None and unit["electrical_hookup"] != electrical_hookup:
                continue
            if pet_friendly is not None and unit["is_pet_friendly"] != pet_friendly:
                continue
            if accessible is not None and unit["is_accessible"] != accessible:
                continue
            if not all(is_in_operating_season(day[5:], unit["operating_season_start"], unit["operating_season_end"]) for day in stay_dates):
                continue
            if reservation_conflicts(cursor, site_id=unit["id"], arrival_date=arrival_date, departure_date=departure_date):
                continue
            results.append({
                "unit_kind": "site",
                "site_id": unit["id"],
                "name": f"Site {unit['site_number']}",
                "type": unit["site_type"],
                "park": unit["park_name"],
                "campground": unit["campground_name"],
                "price_per_night_cad": unit["price_per_night_cad"],
                "total_price_cad": round(unit["price_per_night_cad"] * len(stay_dates), 2),
                "available_dates": stay_dates,
                "electrical_hookup": unit["electrical_hookup"],
                "pet_friendly": unit["is_pet_friendly"],
                "accessible": unit["is_accessible"],
                "equipment_allowed": unit["equipment_allowed"],
            })
    return results


@mcp.tool()
def get_site_details(site_id: int) -> dict[str, Any]:
    """Get site details, amenities, permitted equipment, and location for a campsite."""
    with db_cursor() as cursor:
        return site_record(cursor, site_id)


@mcp.tool()
def get_site_calendar(site_id: int, month: str) -> dict[str, Any]:
    """Return one site's daily availability calendar for a YYYY-MM month."""
    try:
        start = datetime.strptime(f"{month}-01", "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("month must use YYYY-MM format") from exc
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    with db_cursor() as cursor:
        site = site_record(cursor, site_id)
        calendar = []
        current = start
        while current < end:
            day = current.isoformat()
            in_season = is_in_operating_season(day[5:], site["operating_season_start"], site["operating_season_end"])
            calendar.append({
                "date": day,
                "is_available": in_season and not reservation_conflicts(
                    cursor, site_id=site_id, arrival_date=day, departure_date=(current.fromordinal(current.toordinal() + 1)).isoformat()
                ),
                "price_per_night_cad": site["price_per_night_cad"] if in_season else None,
            })
            current = current.fromordinal(current.toordinal() + 1)
        return {"site_id": site_id, "month": month, "calendar": calendar}


def ensure_user(cursor: Any, user_id: int | None, user_name: str | None, user_email: str | None, phone: str | None) -> int:
    if user_id is not None:
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"User {user_id} not found")
        return user_id
    if not user_name or not user_email:
        raise ValueError("Provide user_id or both user_name and user_email")
    cursor.execute("SELECT id FROM users WHERE email = ?", (user_email.strip().lower(),))
    existing = cursor.fetchone()
    if existing:
        return int(existing["id"])
    cursor.execute("INSERT INTO users (name, email, phone) VALUES (?, ?, ?)", (user_name.strip(), user_email.strip().lower(), phone))
    return int(cursor.lastrowid)


@mcp.tool()
def create_reservation(
    arrival_date: str,
    departure_date: str,
    party_size: int,
    user_id: int | None = None,
    site_id: int | None = None,
    accommodation_id: int | None = None,
    equipment_type: str | None = None,
    user_name: str | None = None,
    user_email: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    """Create a confirmed reservation after a user explicitly selects an available site or accommodation.

    Provide either site_id or accommodation_id, never both. A user can be supplied by user_id or by name and email.
    """
    if (site_id is None) == (accommodation_id is None):
        raise ValueError("Provide exactly one of site_id or accommodation_id")
    stay_dates = dates_in_stay(arrival_date, departure_date)
    if party_size < 1:
        raise ValueError("party_size must be at least 1")

    with db_cursor() as cursor:
        if site_id is not None:
            unit = site_record(cursor, site_id)
            if party_size > unit["max_party_size"]:
                raise ValueError("party_size exceeds the site's maximum")
            if equipment_type is None:
                raise ValueError("equipment_type is required for a campsite")
            normalized = validate_party_and_equipment(party_size, equipment_type)
            if normalized == "roofed" or normalized not in {item.lower() for item in unit["equipment_allowed"]}:
                raise ValueError("The selected site does not allow that equipment_type")
            if not all(is_in_operating_season(day[5:], unit["operating_season_start"], unit["operating_season_end"]) for day in stay_dates):
                raise ValueError("The selected site is outside its operating season for these dates")
            if reservation_conflicts(cursor, site_id=site_id, arrival_date=arrival_date, departure_date=departure_date):
                raise ValueError("The selected site is no longer available for all requested nights")
            price = unit["price_per_night_cad"]
        else:
            unit = accommodation_record(cursor, accommodation_id or 0)
            if party_size > unit["sleeps_max"]:
                raise ValueError("party_size exceeds the accommodation capacity")
            if reservation_conflicts(cursor, accommodation_id=accommodation_id, arrival_date=arrival_date, departure_date=departure_date):
                raise ValueError("The selected accommodation is no longer available for all requested nights")
            price = unit["price_per_night_cad"]
            equipment_type = "roofed"

        confirmed_user_id = ensure_user(cursor, user_id, user_name, user_email, phone)
        confirmation = f"PCD-{datetime.now(UTC):%Y%m%d}-{site_id or accommodation_id:04d}-{confirmed_user_id:04d}"
        total = round(price * len(stay_dates), 2)
        cursor.execute(
            """
            INSERT INTO reservations (
                confirmation_code, user_id, site_id, accommodation_id, arrival_date, departure_date,
                party_size, equipment_type, status, total_price, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?, ?)
            """,
            (confirmation, confirmed_user_id, site_id, accommodation_id, arrival_date, departure_date, party_size, equipment_type, total, datetime.now(UTC).isoformat()),
        )
        reservation_id = int(cursor.lastrowid)
    return get_reservation(reservation_id)


@mcp.tool()
def get_reservation(reservation_id: int) -> dict[str, Any]:
    """Get a reservation confirmation and its booked unit details."""
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT r.*, u.name AS user_name, u.email AS user_email, u.phone AS user_phone
            FROM reservations r JOIN users u ON u.id = r.user_id WHERE r.id = ?
            """,
            (reservation_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Reservation {reservation_id} not found")
        result = row_to_dict(row)
        if result["site_id"] is not None:
            result["unit"] = site_record(cursor, result["site_id"])
        else:
            result["unit"] = accommodation_record(cursor, result["accommodation_id"])
        return result


@mcp.tool()
def cancel_reservation(reservation_id: int) -> dict[str, Any]:
    """Cancel a confirmed reservation. This demo does not apply fees or refunds."""
    with db_cursor() as cursor:
        cursor.execute("SELECT id FROM reservations WHERE id = ?", (reservation_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Reservation {reservation_id} not found")
        cursor.execute("UPDATE reservations SET status = 'cancelled' WHERE id = ?", (reservation_id,))
    return get_reservation(reservation_id)


@mcp.tool()
def list_user_reservations(user_id: int) -> list[dict[str, Any]]:
    """List all reservations for a demo user account."""
    with db_cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"User {user_id} not found")
        cursor.execute("SELECT id FROM reservations WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        reservation_ids = [row["id"] for row in cursor.fetchall()]
    return [get_reservation(reservation_id) for reservation_id in reservation_ids]


def main() -> None:
    mcp.run(transport="http", host=settings.host, port=settings.port, path="/mcp")


if __name__ == "__main__":
    main()
