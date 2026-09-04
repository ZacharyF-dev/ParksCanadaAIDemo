from __future__ import annotations

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT


DASHBOARD_DIR = PROJECT_ROOT / "dashboard_static"
SERVICES = [
    {"name": "Jira Board", "description": "Local ticket-management dashboard", "url": "http://127.0.0.1:8001", "health": "http://127.0.0.1:8000/health"},
    {"name": "JiraLite Agent", "description": "Chainlit agent with Jira MCP tools", "url": "http://127.0.0.1:8002", "health": "http://127.0.0.1:8002"},
    {"name": "Workspace Agent", "description": "Chainlit agent using Jira, RAG, and synthetic directory MCP tools", "url": "http://127.0.0.1:8005", "health": "http://127.0.0.1:8005"},
    {"name": "Markdown RAG MCP", "description": "Local vector search over Markdown knowledge", "url": "http://127.0.0.1:8003/mcp", "health": "http://127.0.0.1:8003/health"},
    {"name": "Synthetic PC411 Directory MCP", "description": "Fictional organization and people directory", "url": "http://127.0.0.1:8004/mcp", "health": "http://127.0.0.1:8004/health"},
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
