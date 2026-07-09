from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP

from app.api import router as api_router
from app.config import settings
from app.db import db_cursor, row_to_dict, utc_now_iso, next_ticket_key
from app.models import TicketCreate, CommentCreate


mcp = FastMCP("mini-jira")


@mcp.tool()
def create_ticket(
    title: str,
    description: str = "",
    priority: str = "medium",
    assignee: str | None = None,
) -> dict[str, Any]:
    """
    Create a new ticket.
    """
    now = utc_now_iso()
    with db_cursor() as cur:
        key = next_ticket_key(cur)
        cur.execute(
            """
            INSERT INTO tickets (key, title, description, status, priority, assignee, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (key, title, description, "todo", priority, assignee, now, now),
        )
        ticket_id = int(cur.lastrowid)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return row_to_dict(cur.fetchone())


@mcp.tool()
def list_tickets(status: str | None = None, query: str | None = None) -> list[dict[str, Any]]:
    """
    List tickets, optionally filtered by status or a text query.
    """
    sql = "SELECT * FROM tickets WHERE 1=1"
    params: list[str] = []

    if status:
        sql += " AND status = ?"
        params.append(status)

    if query:
        sql += " AND (title LIKE ? OR description LIKE ? OR key LIKE ?)"
        like = f"%{query}%"
        params.extend([like, like, like])

    sql += " ORDER BY id DESC"

    with db_cursor() as cur:
        cur.execute(sql, params)
        return [row_to_dict(row) for row in cur.fetchall()]


@mcp.tool()
def get_ticket(ticket_id: int) -> dict[str, Any]:
    """
    Get a ticket and its comments by ticket id.
    """
    with db_cursor() as cur:
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Ticket {ticket_id} not found")

        ticket = row_to_dict(row)
        cur.execute(
            "SELECT * FROM comments WHERE ticket_id = ? ORDER BY id ASC",
            (ticket_id,),
        )
        ticket["comments"] = [row_to_dict(comment) for comment in cur.fetchall()]
        return ticket


@mcp.tool()
def add_comment(ticket_id: int, author: str, body: str) -> dict[str, Any]:
    """
    Add a comment to a ticket.
    """
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise ValueError(f"Ticket {ticket_id} not found")

        cur.execute(
            """
            INSERT INTO comments (ticket_id, author, body, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (ticket_id, author, body, utc_now_iso()),
        )
        comment_id = int(cur.lastrowid)
        cur.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
        return row_to_dict(cur.fetchone())


@mcp.tool()
def update_status(ticket_id: int, status: str) -> dict[str, Any]:
    """
    Update a ticket status. Allowed values: todo, in_progress, blocked, done.
    """
    allowed = {"todo", "in_progress", "blocked", "done"}
    if status not in allowed:
        raise ValueError(f"Invalid status '{status}'. Allowed: {sorted(allowed)}")

    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise ValueError(f"Ticket {ticket_id} not found")

        cur.execute(
            "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_now_iso(), ticket_id),
        )
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return row_to_dict(cur.fetchone())


@mcp.tool()
def assign_ticket(ticket_id: int, assignee: str | None) -> dict[str, Any]:
    """
    Assign or unassign a ticket. Pass null/None to clear assignee.
    """
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise ValueError(f"Ticket {ticket_id} not found")

        cur.execute(
            "UPDATE tickets SET assignee = ?, updated_at = ? WHERE id = ?",
            (assignee, utc_now_iso(), ticket_id),
        )
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return row_to_dict(cur.fetchone())


@mcp.tool()
def list_comments(ticket_id: int) -> list[dict[str, Any]]:
    """
    List comments for a ticket.
    """
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise ValueError(f"Ticket {ticket_id} not found")

        cur.execute("SELECT * FROM comments WHERE ticket_id = ? ORDER BY id ASC", (ticket_id,))
        return [row_to_dict(row) for row in cur.fetchall()]


def create_backend_app() -> FastAPI:
    mcp_app = mcp.http_app(path="/")

    app = FastAPI(
        title="Mini Jira MCP Backend",
        description="Backend API and MCP server for Mini Jira.",
        version="1.0.0",
        lifespan=mcp_app.lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    @app.get("/", tags=["meta"])
    def root() -> dict[str, Any]:
        return {
            "name": "mini-jira-backend",
            "status": "ok",
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
            "health": "/health",
            "liveness": "/health/live",
            "readiness": "/health/ready",
            "mcp": "/mcp",
        }

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/live", tags=["health"])
    def health_live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready", tags=["health"])
    def health_ready() -> dict[str, Any]:
        try:
            with db_cursor() as cur:
                cur.execute("SELECT 1 as ok")
                row = cur.fetchone()

            return {
                "status": "ready",
                "database": "ok" if row is not None else "unknown",
            }
        except Exception as exc:
            return {
                "status": "not_ready",
                "database": "error",
                "detail": str(exc),
            }

    @app.get("/docs-info", tags=["meta"])
    def docs_info() -> dict[str, Any]:
        return {
            "service": "Mini Jira MCP Backend",
            "version": "1.0.0",
            "description": "Testing and development endpoints for the Mini Jira MCP backend.",
            "routes": {
                "docs": "/docs",
                "redoc": "/redoc",
                "openapi": "/openapi.json",
                "health": "/health",
                "health_live": "/health/live",
                "health_ready": "/health/ready",
                "mcp": "/mcp",
            },
            "tools": [
                "create_ticket",
                "list_tickets",
                "get_ticket",
                "add_comment",
                "update_status",
                "assign_ticket",
                "list_comments",
            ],
        }

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"http://localhost:{settings.frontend_port}"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    app.mount("/mcp", mcp_app)

    return app