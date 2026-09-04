from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from pc411_directory_mcp.db import db_cursor
from pc411_directory_mcp.settings import settings

mcp = FastMCP("pc411-directory")


def row_to_person(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": f"{row['first_name']} {row['last_name']}",
        "title": row["title"],
        "email": row["email"],
        "organization": row["organization"],
        "organization_path": row["organization_path"],
        "manager": row["manager"],
        "synthetic_data": True,
    }


PERSON_SELECT = """
SELECT p.id, p.first_name, p.last_name, p.title, p.email,
       o.name AS organization, o.path AS organization_path,
       CASE WHEN m.id IS NULL THEN NULL ELSE m.first_name || ' ' || m.last_name END AS manager
FROM people p
JOIN organizations o ON o.id = p.organization_id
LEFT JOIN people m ON m.id = p.manager_id
"""


@mcp.tool()
def search_people(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search synthetic PC411 directory people by name, email, job title, or organization."""
    if not query.strip():
        raise ValueError("query must not be empty")
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    like = f"%{query.strip()}%"
    with db_cursor() as cursor:
        cursor.execute(
            PERSON_SELECT
            + """
            WHERE p.first_name || ' ' || p.last_name LIKE ? OR p.email LIKE ? OR p.title LIKE ?
               OR o.name LIKE ? OR o.path LIKE ?
            ORDER BY p.last_name, p.first_name LIMIT ?
            """,
            (like, like, like, like, like, limit),
        )
        return [row_to_person(row) for row in cursor.fetchall()]


@mcp.tool()
def get_person(email: str) -> dict[str, Any]:
    """Get a synthetic directory profile, including manager and direct reports, by email."""
    with db_cursor() as cursor:
        cursor.execute(PERSON_SELECT + " WHERE p.email = ?", (email.lower().strip(),))
        person = cursor.fetchone()
        if person is None:
            raise ValueError(f"No directory record found for {email}")
        result = row_to_person(person)
        cursor.execute(
            "SELECT first_name || ' ' || last_name AS name, title, email FROM people WHERE manager_id = ? ORDER BY last_name, first_name",
            (person["id"],),
        )
        result["direct_reports"] = [dict(row) for row in cursor.fetchall()]
        return result


@mcp.tool()
def browse_organization(query: str, include_people: bool = False) -> list[dict[str, Any]]:
    """Find synthetic directory organizations by name or hierarchy path, with optional contacts."""
    if not query.strip():
        raise ValueError("query must not be empty")
    like = f"%{query.strip()}%"
    with db_cursor() as cursor:
        cursor.execute(
            "SELECT id, name, path, depth FROM organizations WHERE name LIKE ? OR path LIKE ? ORDER BY path LIMIT 25",
            (like, like),
        )
        organizations = []
        for organization in cursor.fetchall():
            record: dict[str, Any] = dict(organization)
            cursor.execute("SELECT name FROM organizations WHERE parent_id = ? ORDER BY name", (organization["id"],))
            record["child_organizations"] = [row["name"] for row in cursor.fetchall()]
            if include_people:
                cursor.execute(
                    "SELECT first_name || ' ' || last_name AS name, title, email FROM people WHERE organization_id = ? ORDER BY is_manager DESC, last_name, first_name",
                    (organization["id"],),
                )
                record["people"] = [dict(row) for row in cursor.fetchall()]
            organizations.append(record)
        return organizations


@mcp.tool()
def get_organization_contacts(organization_name: str, title_query: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    """List synthetic directory contacts in organizations matching a name, optionally filtering by title."""
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    organization_like = f"%{organization_name.strip()}%"
    title_like = f"%{title_query.strip()}%" if title_query else "%"
    with db_cursor() as cursor:
        cursor.execute(
            PERSON_SELECT
            + " WHERE (o.name LIKE ? OR o.path LIKE ?) AND p.title LIKE ? ORDER BY o.path, p.is_manager DESC, p.last_name LIMIT ?",
            (organization_like, organization_like, title_like, limit),
        )
        return [row_to_person(row) for row in cursor.fetchall()]


@mcp.tool()
def find_reporting_chain(email: str) -> list[dict[str, str]]:
    """Return a synthetic person's manager chain, starting with the person and ending at the top manager."""
    with db_cursor() as cursor:
        cursor.execute("SELECT id FROM people WHERE email = ?", (email.lower().strip(),))
        person = cursor.fetchone()
        if person is None:
            raise ValueError(f"No directory record found for {email}")
        chain = []
        current_id: int | None = person["id"]
        while current_id is not None:
            cursor.execute(
                "SELECT p.id, p.first_name || ' ' || p.last_name AS name, p.title, p.email, p.manager_id FROM people p WHERE p.id = ?",
                (current_id,),
            )
            current = cursor.fetchone()
            if current is None:
                break
            chain.append({"name": current["name"], "title": current["title"], "email": current["email"]})
            current_id = current["manager_id"]
        return chain


@mcp.tool()
def get_directory_stats() -> dict[str, Any]:
    """Summarize the local synthetic PC411 directory data set."""
    with db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM organizations")
        organizations = cursor.fetchone()["count"]
        cursor.execute("SELECT COUNT(*) AS count FROM people")
        people = cursor.fetchone()["count"]
        cursor.execute("SELECT MAX(depth) AS depth FROM organizations")
        max_depth = cursor.fetchone()["depth"] or 0
    return {"organizations": organizations, "people": people, "max_organization_depth": max_depth, "all_person_data_is_synthetic": True}


def main() -> None:
    mcp.run(transport="http", host=settings.host, port=settings.port, path="/mcp")


if __name__ == "__main__":
    main()
