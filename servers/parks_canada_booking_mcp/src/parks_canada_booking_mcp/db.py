from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

from parks_canada_booking_mcp.settings import settings


@contextmanager
def db_cursor() -> Iterator[sqlite3.Cursor]:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        cursor = connection.cursor()
        yield cursor
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with db_cursor() as cursor:
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS parks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                province TEXT NOT NULL,
                park_type TEXT NOT NULL,
                established INTEGER,
                area_km2 REAL,
                natural_region TEXT,
                description TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_parks_name ON parks(name);
            CREATE INDEX IF NOT EXISTS idx_parks_province ON parks(province);

            CREATE TABLE IF NOT EXISTS campgrounds (
                id INTEGER PRIMARY KEY,
                park_id TEXT NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                operating_season_start TEXT NOT NULL,
                operating_season_end TEXT NOT NULL,
                num_loops INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_campgrounds_park ON campgrounds(park_id);

            CREATE TABLE IF NOT EXISTS sites (
                id INTEGER PRIMARY KEY,
                campground_id INTEGER NOT NULL REFERENCES campgrounds(id) ON DELETE CASCADE,
                site_number TEXT NOT NULL,
                site_type TEXT NOT NULL,
                max_party_size INTEGER NOT NULL,
                max_vehicles INTEGER NOT NULL,
                is_accessible INTEGER NOT NULL,
                is_pet_friendly INTEGER NOT NULL,
                equipment_allowed TEXT NOT NULL,
                max_equipment_length_ft INTEGER,
                electrical_hookup INTEGER NOT NULL,
                water_hookup INTEGER NOT NULL,
                sewer_hookup INTEGER NOT NULL,
                price_per_night_cad REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sites_campground ON sites(campground_id);

            CREATE TABLE IF NOT EXISTS accommodations (
                id INTEGER PRIMARY KEY,
                campground_id INTEGER REFERENCES campgrounds(id) ON DELETE CASCADE,
                park_id TEXT NOT NULL REFERENCES parks(id) ON DELETE CASCADE,
                accommodation_type TEXT NOT NULL,
                name TEXT NOT NULL,
                sleeps_min INTEGER NOT NULL,
                sleeps_max INTEGER NOT NULL,
                amenities TEXT NOT NULL,
                is_pet_friendly INTEGER NOT NULL,
                is_accessible INTEGER NOT NULL,
                price_per_night_cad REAL NOT NULL,
                num_units INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_accommodations_park ON accommodations(park_id);

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT
            );

            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                confirmation_code TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                site_id INTEGER REFERENCES sites(id),
                accommodation_id INTEGER REFERENCES accommodations(id),
                arrival_date TEXT NOT NULL,
                departure_date TEXT NOT NULL,
                party_size INTEGER NOT NULL,
                equipment_type TEXT,
                status TEXT NOT NULL DEFAULT 'confirmed',
                total_price REAL NOT NULL,
                created_at TEXT NOT NULL,
                CHECK ((site_id IS NOT NULL AND accommodation_id IS NULL) OR (site_id IS NULL AND accommodation_id IS NOT NULL))
            );
            CREATE INDEX IF NOT EXISTS idx_reservations_unit_dates ON reservations(site_id, accommodation_id, arrival_date, departure_date);
            """
        )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def dates_in_stay(arrival_date: str, departure_date: str) -> list[str]:
    arrival = date.fromisoformat(arrival_date)
    departure = date.fromisoformat(departure_date)
    if departure <= arrival:
        raise ValueError("departure_date must be after arrival_date")
    return [(arrival + timedelta(days=offset)).isoformat() for offset in range((departure - arrival).days)]


def is_in_operating_season(month_day: str, season_start: str, season_end: str) -> bool:
    if season_start <= season_end:
        return season_start <= month_day <= season_end
    return month_day >= season_start or month_day <= season_end


def reservation_conflicts(
    cursor: sqlite3.Cursor,
    *,
    site_id: int | None = None,
    accommodation_id: int | None = None,
    arrival_date: str,
    departure_date: str,
    exclude_reservation_id: int | None = None,
) -> bool:
    if site_id is None and accommodation_id is None:
        raise ValueError("A site_id or accommodation_id is required")
    field = "site_id" if site_id is not None else "accommodation_id"
    unit_id = site_id if site_id is not None else accommodation_id
    sql = f"""
        SELECT COUNT(*) AS count
        FROM reservations
        WHERE {field} = ? AND status = 'confirmed'
          AND arrival_date < ? AND departure_date > ?
    """
    params: list[Any] = [unit_id, departure_date, arrival_date]
    if exclude_reservation_id is not None:
        sql += " AND id != ?"
        params.append(exclude_reservation_id)
    cursor.execute(sql, params)
    return bool(cursor.fetchone()["count"])


def decode_json_fields(record: dict[str, Any]) -> dict[str, Any]:
    for key in ("equipment_allowed", "amenities"):
        if key in record and isinstance(record[key], str):
            record[key] = json.loads(record[key])
    for key in ("is_accessible", "is_pet_friendly", "electrical_hookup", "water_hookup", "sewer_hookup"):
        if key in record:
            record[key] = bool(record[key])
    return record
