from __future__ import annotations

import random
import sqlite3

from pc411_directory_mcp.db import db_cursor, init_db
from pc411_directory_mcp.settings import settings

FIRST_NAMES = [
    "Avery", "Cameron", "Daria", "Elliot", "Fatima", "Gavin", "Harper", "Imani", "Jordan", "Kai",
    "Leah", "Morgan", "Noah", "Olivia", "Priya", "Quinn", "Riley", "Sofia", "Theo", "Valerie",
    "William", "Xavier", "Yasmin", "Zoe", "Amir", "Bianca", "Colin", "Danielle", "Ethan", "Farah",
]
LAST_NAMES = [
    "Anderson", "Bouchard", "Chen", "Desai", "Evans", "Fournier", "Green", "Hughes", "Ibrahim", "Jones",
    "Kaur", "Lavoie", "Martin", "Nguyen", "Ouellet", "Patel", "Roy", "Singh", "Taylor", "Wong",
    "Young", "Zhang", "Campbell", "Dubois", "MacLeod", "Tremblay", "Wilson", "Brown", "Gagnon", "Lee",
]


def staff_title(name: str) -> str:
    lowered = name.lower()
    if any(word in lowered for word in ("finance", "budget", "accounting", "comptrollership", "costing")):
        return "Financial Analyst"
    if any(word in lowered for word in ("communications", "media", "brand", "outreach", "web")):
        return "Communications Advisor"
    if any(word in lowered for word in ("human", "hr", "staffing", "compensation", "wellness", "labour")):
        return "Human Resources Advisor"
    if any(word in lowered for word in ("audit", "evaluation")):
        return "Program Evaluation Analyst"
    if any(word in lowered for word in ("procurement", "contract")):
        return "Procurement Officer"
    if any(word in lowered for word in ("information", "digital", "data", "technology", "systems")):
        return "Information Technology Specialist"
    if any(word in lowered for word in ("policy", "planning", "strategy")):
        return "Policy Analyst"
    return "Program Advisor"


def manager_title(name: str, depth: int) -> str:
    if depth == 1:
        return "Chief Executive Officer"
    if "vice-president" in name.lower() or depth == 2:
        return "Vice-President"
    if "executive director" in name.lower() or depth == 3:
        return "Executive Director"
    if "director" in name.lower() or depth == 4:
        return "Director"
    return "Manager"


def unique_identity(rng: random.Random, existing_emails: set[str]) -> tuple[str, str, str]:
    while True:
        first_name = rng.choice(FIRST_NAMES)
        last_name = rng.choice(LAST_NAMES)
        email = f"{first_name.lower()}.{last_name.lower()}@pc.gc.ca"
        if email not in existing_emails:
            existing_emails.add(email)
            return first_name, last_name, email


def seed_directory() -> dict[str, int]:
    init_db()
    rng = random.Random(settings.seed)
    with db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM organizations")
        organization_count = int(cursor.fetchone()["count"])
        if not organization_count:
            raise RuntimeError("No organizations exist. Run pc411-directory-import first.")

        cursor.execute("DELETE FROM people")
        cursor.execute("SELECT id, name, parent_id, depth FROM organizations ORDER BY depth, id")
        organizations = cursor.fetchall()
        manager_by_organization: dict[int, int] = {}
        existing_emails: set[str] = set()
        people_count = 0

        for organization in organizations:
            org_id = int(organization["id"])
            parent_manager_id = manager_by_organization.get(organization["parent_id"])
            first_name, last_name, email = unique_identity(rng, existing_emails)
            cursor.execute(
                """
                INSERT INTO people (first_name, last_name, title, email, organization_id, manager_id, is_manager)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (first_name, last_name, manager_title(organization["name"], organization["depth"]), email, org_id, parent_manager_id),
            )
            manager_id = int(cursor.lastrowid)
            manager_by_organization[org_id] = manager_id
            people_count += 1

            # Keep the sample directory compact enough that its curated fake-name pool remains unique.
            direct_staff = rng.randint(1, 2) if organization["depth"] < 4 else rng.randint(0, 1)
            for _ in range(direct_staff):
                first_name, last_name, email = unique_identity(rng, existing_emails)
                cursor.execute(
                    """
                    INSERT INTO people (first_name, last_name, title, email, organization_id, manager_id, is_manager)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                    """,
                    (first_name, last_name, staff_title(organization["name"]), email, org_id, manager_id),
                )
                people_count += 1
    return {"organizations": organization_count, "people": people_count}


def main() -> None:
    result = seed_directory()
    print(f"Generated {result['people']} synthetic people across {result['organizations']} organizations.")


if __name__ == "__main__":
    main()
