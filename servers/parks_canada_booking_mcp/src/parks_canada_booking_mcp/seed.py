from __future__ import annotations

import json

from parks_canada_booking_mcp.db import db_cursor, init_db
from parks_canada_booking_mcp.settings import settings


def seed_database(replace: bool = False) -> dict[str, int]:
    if not settings.seed_path.exists():
        raise FileNotFoundError(f"Seed data not found: {settings.seed_path}")

    source = json.loads(settings.seed_path.read_text(encoding="utf-8"))
    init_db()
    with db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM parks")
        if cursor.fetchone()["count"] and not replace:
            return {name: 0 for name in ("parks", "campgrounds", "sites", "accommodations")}

        if replace:
            cursor.execute("DELETE FROM reservations")
            cursor.execute("DELETE FROM users")
            cursor.execute("DELETE FROM accommodations")
            cursor.execute("DELETE FROM sites")
            cursor.execute("DELETE FROM campgrounds")
            cursor.execute("DELETE FROM parks")

        cursor.executemany(
            """
            INSERT INTO parks (id, name, province, park_type, established, area_km2, natural_region, description)
            VALUES (:id, :name, :province, :park_type, :established, :area_km2, :natural_region, :description)
            """,
            source["parks"],
        )
        cursor.executemany(
            """
            INSERT INTO campgrounds (id, park_id, name, description, operating_season_start, operating_season_end, num_loops)
            VALUES (:id, :park_id, :name, :description, :operating_season_start, :operating_season_end, :num_loops)
            """,
            source["campgrounds"],
        )
        cursor.executemany(
            """
            INSERT INTO sites (
                id, campground_id, site_number, site_type, max_party_size, max_vehicles,
                is_accessible, is_pet_friendly, equipment_allowed, max_equipment_length_ft,
                electrical_hookup, water_hookup, sewer_hookup, price_per_night_cad
            ) VALUES (
                :id, :campground_id, :site_number, :site_type, :max_party_size, :max_vehicles,
                :is_accessible, :is_pet_friendly, :equipment_allowed, :max_equipment_length_ft,
                :electrical_hookup, :water_hookup, :sewer_hookup, :price_per_night_cad
            )
            """,
            [
                {**site, "equipment_allowed": json.dumps(site["equipment_allowed"])}
                for site in source["sites"]
            ],
        )
        cursor.executemany(
            """
            INSERT INTO accommodations (
                id, campground_id, park_id, accommodation_type, name, sleeps_min, sleeps_max,
                amenities, is_pet_friendly, is_accessible, price_per_night_cad, num_units
            ) VALUES (
                :id, :campground_id, :park_id, :type, :name, :sleeps_min, :sleeps_max,
                :amenities, :is_pet_friendly, :is_accessible, :price_per_night_cad, :num_units
            )
            """,
            [
                {**accommodation, "amenities": json.dumps(accommodation["amenities"])}
                for accommodation in source["accommodations"]
            ],
        )
    return {name: len(source[name]) for name in ("parks", "campgrounds", "sites", "accommodations")}


def main() -> None:
    result = seed_database(replace=True)
    print("Seeded Parks Canada booking demo: " + ", ".join(f"{name}={count}" for name, count in result.items()))


if __name__ == "__main__":
    main()
