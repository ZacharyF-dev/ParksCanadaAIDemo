from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pc411_directory_mcp.db import db_cursor


STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="PC411 Directory Dashboard")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/organization-tree")
    def organization_tree() -> dict[str, Any]:
        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT o.id, o.name, o.parent_id, o.depth,
                       COUNT(p.id) AS people_count
                FROM organizations o
                LEFT JOIN people p ON p.organization_id = o.id
                GROUP BY o.id
                ORDER BY o.path
                """
            )
            organizations = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT first_name || ' ' || last_name AS name, title, organization_id
                FROM people
                ORDER BY is_manager DESC, last_name, first_name
                """
            )
            people_by_organization: dict[int, list[dict[str, str]]] = {}
            for person in cursor.fetchall():
                people_by_organization.setdefault(person["organization_id"], []).append(
                    {"name": person["name"], "title": person["title"]}
                )

        nodes = {
            organization["id"]: {
                **organization,
                "people": people_by_organization.get(organization["id"], []),
                "children": [],
            }
            for organization in organizations
        }
        roots = []
        for organization in organizations:
            node = nodes[organization["id"]]
            if organization["parent_id"] is None:
                roots.append(node)
            else:
                nodes[organization["parent_id"]]["children"].append(node)
        return {"roots": roots, "organization_count": len(organizations)}

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8011, log_level="info")


if __name__ == "__main__":
    main()
