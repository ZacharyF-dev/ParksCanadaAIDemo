from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from parks_canada_booking_mcp.db import db_cursor, row_to_dict
from parks_canada_booking_mcp.server import browse_availability, cancel_reservation, get_site_calendar, search_availability
from parks_canada_booking_mcp.settings import settings


STATIC_DIR = Path(__file__).resolve().parent / "static"


def reservation_summary(cursor: Any, reservation_id: int) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT r.*, u.name AS guest_name, u.email AS guest_email,
               p.name AS park_name, c.name AS campground_name,
               s.site_number, s.site_type, a.name AS accommodation_name, a.accommodation_type
        FROM reservations r
        JOIN users u ON u.id = r.user_id
        LEFT JOIN sites s ON s.id = r.site_id
        LEFT JOIN accommodations a ON a.id = r.accommodation_id
        LEFT JOIN campgrounds c ON c.id = COALESCE(s.campground_id, a.campground_id)
        LEFT JOIN parks p ON p.id = COALESCE(c.park_id, a.park_id)
        WHERE r.id = ?
        """,
        (reservation_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    item = row_to_dict(row)
    item["unit_name"] = item["accommodation_name"] or f"Site {item['site_number']}"
    item["unit_type"] = item["accommodation_type"] or item["site_type"]
    return item


def create_app() -> FastAPI:
    app = FastAPI(title="Parks Canada Booking Demo Dashboard")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/stats")
    def stats() -> dict[str, Any]:
        with db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM reservations WHERE status = 'confirmed'")
            confirmed = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) AS count FROM reservations WHERE status = 'cancelled'")
            cancelled = cursor.fetchone()["count"]
            cursor.execute("SELECT COALESCE(SUM(total_price), 0) AS value FROM reservations WHERE status = 'confirmed'")
            booking_value = cursor.fetchone()["value"]
            cursor.execute("SELECT COUNT(*) AS count FROM parks")
            parks = cursor.fetchone()["count"]
        return {"confirmed_reservations": confirmed, "cancelled_reservations": cancelled, "booking_value_cad": booking_value, "parks": parks}

    @app.get("/api/parks")
    def parks() -> list[dict[str, str]]:
        """List all seeded parks for the availability explorer."""
        with db_cursor() as cursor:
            cursor.execute("SELECT id, name, province FROM parks ORDER BY name")
            return [row_to_dict(row) for row in cursor.fetchall()]

    @app.get("/api/reservations")
    def reservations(status: str | None = None) -> list[dict[str, Any]]:
        with db_cursor() as cursor:
            sql = "SELECT id FROM reservations"
            params: list[str] = []
            if status:
                sql += " WHERE status = ?"
                params.append(status)
            sql += " ORDER BY arrival_date ASC, id DESC"
            cursor.execute(sql, params)
            return [reservation_summary(cursor, row["id"]) for row in cursor.fetchall()]

    @app.delete("/api/reservations/{reservation_id}")
    def cancel_booking(reservation_id: int) -> dict[str, Any]:
        """Cancel a demo booking so the unit becomes available again."""
        try:
            return cancel_reservation(reservation_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/availability")
    def availability(
        location: str,
        month: str,
        party_size: int = Query(default=1, ge=1),
        equipment_type: str = "tent",
    ) -> dict[str, Any]:
        try:
            return browse_availability(location, month, party_size, equipment_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/search")
    def availability_search(
        location: str,
        arrival_date: str,
        departure_date: str,
        party_size: int = Query(default=1, ge=1),
        equipment_type: str = "tent",
    ) -> list[dict[str, Any]]:
        try:
            return search_availability(location, arrival_date, departure_date, party_size, equipment_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/sites/{site_id}/calendar")
    def site_calendar(site_id: int, month: str) -> dict[str, Any]:
        try:
            return get_site_calendar(site_id, month)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8010, log_level="info")


if __name__ == "__main__":
    main()
