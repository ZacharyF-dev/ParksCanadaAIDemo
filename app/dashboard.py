from __future__ import annotations

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT


DASHBOARD_DIR = PROJECT_ROOT / "dashboard_static"
SERVICES = [
    {"name": "Jira Board", "description": "Local ticket-management dashboard", "url": "http://127.0.0.1:8001", "health": "http://127.0.0.1:8000/health", "category": "application"},
    {"name": "Jira Chat", "description": "Chat interface for Jira tickets and updates", "url": "http://127.0.0.1:8002", "health": "http://127.0.0.1:8002", "category": "chatbot"},
    {"name": "Knowledge Chat", "description": "Chat interface for the Markdown knowledge base", "url": "http://127.0.0.1:8007", "health": "http://127.0.0.1:8007", "category": "chatbot"},
    {"name": "Workspace Chat", "description": "Chat interface for Jira, knowledge, and directory tasks", "url": "http://127.0.0.1:8005", "health": "http://127.0.0.1:8005", "category": "chatbot"},
    {"name": "Parks Booking Chat", "description": "Chat interface for searching and reserving demo sites", "url": "http://127.0.0.1:8009", "health": "http://127.0.0.1:8009", "category": "chatbot"},
    {"name": "Parks Booking Dashboard", "description": "Availability explorer and live booking display", "url": "http://127.0.0.1:8010", "health": "http://127.0.0.1:8010", "category": "application"},
    {"name": "PC411 Organization Dashboard", "description": "Expandable synthetic organization tree with names and titles", "url": "http://127.0.0.1:8011", "health": "http://127.0.0.1:8011", "category": "application"},
    {"name": "Jira MCP", "description": "Ticket-management tools for local clients", "url": "http://127.0.0.1:8000/mcp", "health": "http://127.0.0.1:8000/health", "category": "mcp"},
    {"name": "Markdown Knowledge MCP", "description": "Search tools for local Markdown knowledge", "url": "http://127.0.0.1:8003/mcp", "health": "http://127.0.0.1:8003/health", "category": "mcp"},
    {"name": "PC411 Directory MCP", "description": "Tools for the synthetic organization directory", "url": "http://127.0.0.1:8004/mcp", "health": "http://127.0.0.1:8004/health", "category": "mcp"},
    {"name": "Parks Booking MCP", "description": "Search and booking tools for the local demo", "url": "http://127.0.0.1:8008/mcp", "health": "http://127.0.0.1:8008/health", "category": "mcp"},
]


def create_dashboard_app() -> FastAPI:
    app = FastAPI(title="Local MCP Workspace Dashboard")
    app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(DASHBOARD_DIR / "index.html")

    @app.get("/api/services")
    async def services() -> list[dict[str, str | bool]]:
        async with httpx.AsyncClient(timeout=1.5, follow_redirects=True) as client:
            results = []
            for service in SERVICES:
                try:
                    response = await client.get(service["health"])
                    online = response.status_code < 500
                except httpx.HTTPError:
                    online = False
                results.append({**service, "online": online})
        return results

    return app
