from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP

from app.api import router as api_router, PRIORITY_ORDER
from app.config import settings
from app.db import (
    create_notification,
    db_cursor,
    get_ticket_attachments,
    get_ticket_labels,
    get_ticket_watchers,
    hydrate_ticket,
    row_to_dict,
    utc_now_iso,
    next_ticket_key,
    log_activity,
    is_overdue,
    serialize_filter_definition,
    set_ticket_labels,
)
from app.models import TicketCreate, CommentCreate


mcp = FastMCP("mini-jira")


@mcp.tool()
def create_ticket(
    title: str,
    description: str = "",
    priority: str = "medium",
    category: str = "other",
    labels: list[str] | None = None,
    assignee: str | None = None,
    requester: str | None = None,
    due_at: str | None = None,
    actor: str = "agent",
) -> dict[str, Any]:
    """
    Create a new ticket. category should be one of: hardware, software, network,
    access, other. requester is who reported the issue; assignee is who is
    working it. due_at is an optional ISO-8601 timestamp for SLA tracking.
    """
    now = utc_now_iso()
    with db_cursor() as cur:
        key = next_ticket_key(cur)
        cur.execute(
            """
            INSERT INTO tickets (
                key, title, description, status, priority, category,
                assignee, requester, due_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (key, title, description, "todo", priority, category, assignee, requester, due_at, now, now),
        )
        ticket_id = int(cur.lastrowid or 0)
        set_ticket_labels(cur, ticket_id, labels or [])
        log_activity(cur, ticket_id, "created", f"Ticket {key} created", actor=actor)
        create_notification(cur, f"New ticket created: {key} - {title}", ticket_id)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return hydrate_ticket(cur, cur.fetchone())


@mcp.tool()
def list_tickets(status: str | None = None, query: str | None = None, category: str | None = None, include_archived: bool = False) -> list[dict[str, Any]]:
    """
    List tickets, optionally filtered by status, category, or a text query.
    """
    sql = "SELECT * FROM tickets WHERE 1=1"
    params: list[str] = []

    if not include_archived:
        sql += " AND is_archived = 0"

    if status:
        sql += " AND status = ?"
        params.append(status)

    if category:
        sql += " AND category = ?"
        params.append(category)

    if query:
        sql += " AND (title LIKE ? OR description LIKE ? OR key LIKE ?)"
        like = f"%{query}%"
        params.extend([like, like, like])

    sql += " ORDER BY id DESC"

    with db_cursor() as cur:
        cur.execute(sql, params)
        return [hydrate_ticket(cur, row) for row in cur.fetchall()]


@mcp.tool()
def get_ticket(ticket_id: int) -> dict[str, Any]:
    """
    Get a ticket, its comments, and its full system activity log by ticket id.
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

        cur.execute(
            "SELECT * FROM activity_log WHERE ticket_id = ? ORDER BY id ASC",
            (ticket_id,),
        )
        ticket["activity"] = [row_to_dict(entry) for entry in cur.fetchall()]
        ticket["labels"] = get_ticket_labels(cur, ticket_id)
        ticket["watchers"] = get_ticket_watchers(cur, ticket_id)
        ticket["attachments"] = get_ticket_attachments(cur, ticket_id)
        ticket["is_overdue"] = is_overdue(ticket)
        return ticket


@mcp.tool()
def edit_ticket(
    ticket_id: int,
    title: str,
    description: str = "",
    priority: str = "medium",
    category: str = "other",
    assignee: str | None = None,
    requester: str | None = None,
    due_at: str | None = None,
    actor: str = "agent",
) -> dict[str, Any]:
    """Edit core ticket fields in one call."""
    with db_cursor() as cur:
        cur.execute("SELECT key FROM tickets WHERE id = ?", (ticket_id,))
        existing = cur.fetchone()
        if existing is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        cur.execute(
            """
            UPDATE tickets
            SET title = ?, description = ?, priority = ?, category = ?, assignee = ?, requester = ?, due_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (title, description, priority, category, assignee, requester, due_at, utc_now_iso(), ticket_id),
        )
        log_activity(cur, ticket_id, "edited", "Ticket fields updated", actor=actor)
        create_notification(cur, f"Ticket {existing['key']} was updated", ticket_id)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return hydrate_ticket(cur, cur.fetchone())


@mcp.tool()
def archive_ticket(ticket_id: int, actor: str = "agent") -> dict[str, Any]:
    """Toggle ticket archived state for soft-delete/restore workflows."""
    with db_cursor() as cur:
        cur.execute("SELECT key, is_archived FROM tickets WHERE id = ?", (ticket_id,))
        existing = cur.fetchone()
        if existing is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        next_value = 0 if existing["is_archived"] else 1
        cur.execute("UPDATE tickets SET is_archived = ?, updated_at = ? WHERE id = ?", (next_value, utc_now_iso(), ticket_id))
        state = "archived" if next_value else "restored"
        log_activity(cur, ticket_id, state, f"Ticket {existing['key']} {state}", actor=actor)
        create_notification(cur, f"Ticket {existing['key']} was {state}", ticket_id)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return hydrate_ticket(cur, cur.fetchone())


@mcp.tool()
def update_labels(ticket_id: int, labels: list[str], actor: str = "agent") -> dict[str, Any]:
    """Replace the set of labels attached to a ticket."""
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        set_ticket_labels(cur, ticket_id, labels)
        log_activity(cur, ticket_id, "labels_updated", ", ".join(labels) or "labels cleared", actor=actor)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return hydrate_ticket(cur, cur.fetchone())


@mcp.tool()
def add_watcher(ticket_id: int, watcher: str, actor: str = "agent") -> list[dict[str, Any]]:
    """Add a watcher to a ticket so they can follow updates."""
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        cur.execute(
            "INSERT OR IGNORE INTO watchers (ticket_id, watcher, created_at) VALUES (?, ?, ?)",
            (ticket_id, watcher.strip(), utc_now_iso()),
        )
        log_activity(cur, ticket_id, "watcher_added", watcher.strip(), actor=actor)
        return get_ticket_watchers(cur, ticket_id)


@mcp.tool()
def remove_watcher(ticket_id: int, watcher: str, actor: str = "agent") -> list[dict[str, Any]]:
    """Remove a watcher from a ticket."""
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        cur.execute("DELETE FROM watchers WHERE ticket_id = ? AND watcher = ?", (ticket_id, watcher))
        log_activity(cur, ticket_id, "watcher_removed", watcher, actor=actor)
        return get_ticket_watchers(cur, ticket_id)


@mcp.tool()
def add_attachment(ticket_id: int, filename: str, content_base64: str, uploaded_by: str, content_type: str = "application/octet-stream") -> list[dict[str, Any]]:
    """Attach a file to a ticket using base64 payload content."""
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        cur.execute(
            """
            INSERT INTO attachments (ticket_id, filename, content_type, content_base64, uploaded_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ticket_id, filename, content_type, content_base64, uploaded_by, utc_now_iso()),
        )
        log_activity(cur, ticket_id, "attachment_added", filename, actor=uploaded_by)
        return get_ticket_attachments(cur, ticket_id)


@mcp.tool()
def list_notifications(include_read: bool = False) -> list[dict[str, Any]]:
    """List recent in-app notifications."""
    with db_cursor() as cur:
        sql = "SELECT * FROM notifications"
        if not include_read:
            sql += " WHERE is_read = 0"
        sql += " ORDER BY id DESC LIMIT 50"
        cur.execute(sql)
        return [row_to_dict(row) for row in cur.fetchall()]


@mcp.tool()
def save_filter(name: str, status: str | None = None, category: str | None = None, query: str | None = None, labels: list[str] | None = None) -> dict[str, Any]:
    """Save a named ticket filter preset for later use."""
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO saved_filters (name, definition, created_at) VALUES (?, ?, ?)",
            (
                name,
                serialize_filter_definition({"status": status, "category": category, "query": query, "labels": labels or []}),
                utc_now_iso(),
            ),
        )
        saved_id = int(cur.lastrowid or 0)
        cur.execute("SELECT * FROM saved_filters WHERE id = ?", (saved_id,))
        return row_to_dict(cur.fetchone())


@mcp.tool()
def list_filters() -> list[dict[str, Any]]:
    """List saved filter presets."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM saved_filters ORDER BY name ASC")
        return [row_to_dict(row) for row in cur.fetchall()]


@mcp.tool()
def bulk_update_status(ticket_ids: list[int], status: str, actor: str = "agent") -> dict[str, Any]:
    """Apply one status to many tickets at once."""
    updated: list[int] = []
    with db_cursor() as cur:
        for ticket_id in ticket_ids:
            cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
            if cur.fetchone() is None:
                continue
            cur.execute("UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?", (status, utc_now_iso(), ticket_id))
            log_activity(cur, ticket_id, "bulk_status_changed", status, actor=actor)
            updated.append(ticket_id)
        return {"updated_ticket_ids": updated, "status": status}


@mcp.tool()
def bulk_assign(ticket_ids: list[int], assignee: str | None, actor: str = "agent") -> dict[str, Any]:
    """Assign or unassign many tickets at once."""
    updated: list[int] = []
    with db_cursor() as cur:
        for ticket_id in ticket_ids:
            cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
            if cur.fetchone() is None:
                continue
            cur.execute("UPDATE tickets SET assignee = ?, updated_at = ? WHERE id = ?", (assignee, utc_now_iso(), ticket_id))
            log_activity(cur, ticket_id, "bulk_assigned", assignee or "unassigned", actor=actor)
            updated.append(ticket_id)
        return {"updated_ticket_ids": updated, "assignee": assignee}


@mcp.tool()
def suggest_ticket_response(ticket_id: int) -> dict[str, Any]:
    """Generate a lightweight triage suggestion and comment draft for a ticket."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        ticket = hydrate_ticket(cur, row)
        return {
            "summary": f"{ticket['title']} ({ticket['category']}, {ticket['priority']})",
            "suggested_comment": f"Investigate {ticket['category']} impact, confirm issue with {ticket['requester'] or 'the requester'}, and update the ticket with findings.",
            "suggested_status": "in_progress" if ticket["status"] == "todo" else ticket["status"],
            "suggested_labels": ticket["labels"] or [ticket["category"], ticket["priority"]],
        }


@mcp.tool()
def summarize_ticket_handoff(ticket_id: int) -> dict[str, Any]:
    """Summarize the latest ticket state, comments, and audit trail for handoff."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        ticket = hydrate_ticket(cur, row)
        cur.execute("SELECT author, body FROM comments WHERE ticket_id = ? ORDER BY id DESC LIMIT 1", (ticket_id,))
        last_comment = cur.fetchone()
        cur.execute("SELECT event_type, detail, actor FROM activity_log WHERE ticket_id = ? ORDER BY id DESC LIMIT 1", (ticket_id,))
        last_activity = cur.fetchone()
        parts = [
            f"{ticket['key']}: {ticket['title']}",
            f"status={ticket['status']}, priority={ticket['priority']}, assignee={ticket['assignee'] or 'unassigned'}",
        ]
        if last_comment:
            parts.append(f"last comment by {last_comment['author']}: {last_comment['body']}")
        if last_activity:
            parts.append(f"last activity {last_activity['event_type']} by {last_activity['actor']}: {last_activity['detail']}")
        return {"ticket_id": ticket_id, "handoff_summary": " | ".join(parts)}


@mcp.tool()
def list_activity(ticket_id: int) -> list[dict[str, Any]]:
    """
    List the system audit trail (status/assignee/category changes, escalations,
    creation) for a ticket, separate from human/agent comments.
    """
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise ValueError(f"Ticket {ticket_id} not found")

        cur.execute("SELECT * FROM activity_log WHERE ticket_id = ? ORDER BY id ASC", (ticket_id,))
        return [row_to_dict(row) for row in cur.fetchall()]


@mcp.tool()
def add_comment(ticket_id: int, author: str, body: str) -> dict[str, Any]:
    """
    Add a comment to a ticket. Use this for reasoning, findings, or handoff
    notes you want a human to be able to read.
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
        comment_id = int(cur.lastrowid or 0)
        cur.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
        return row_to_dict(cur.fetchone())


@mcp.tool()
def update_status(ticket_id: int, status: str, actor: str = "agent") -> dict[str, Any]:
    """
    Update a ticket status. Allowed values: todo, in_progress, blocked, done.
    actor identifies which agent made the change, for the audit trail.
    """
    allowed = {"todo", "in_progress", "blocked", "done"}
    if status not in allowed:
        raise ValueError(f"Invalid status '{status}'. Allowed: {sorted(allowed)}")

    with db_cursor() as cur:
        cur.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,))
        existing = cur.fetchone()
        if existing is None:
            raise ValueError(f"Ticket {ticket_id} not found")

        cur.execute(
            "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_now_iso(), ticket_id),
        )
        log_activity(cur, ticket_id, "status_changed", f"{existing['status']} -> {status}", actor=actor)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = row_to_dict(cur.fetchone())
        ticket["is_overdue"] = is_overdue(ticket)
        return ticket


@mcp.tool()
def assign_ticket(ticket_id: int, assignee: str | None, actor: str = "agent") -> dict[str, Any]:
    """
    Assign or unassign a ticket. Pass null/None to clear assignee.
    """
    with db_cursor() as cur:
        cur.execute("SELECT assignee FROM tickets WHERE id = ?", (ticket_id,))
        existing = cur.fetchone()
        if existing is None:
            raise ValueError(f"Ticket {ticket_id} not found")

        cur.execute(
            "UPDATE tickets SET assignee = ?, updated_at = ? WHERE id = ?",
            (assignee, utc_now_iso(), ticket_id),
        )
        prev = existing["assignee"] or "unassigned"
        nxt = assignee or "unassigned"
        log_activity(cur, ticket_id, "assigned", f"{prev} -> {nxt}", actor=actor)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = row_to_dict(cur.fetchone())
        ticket["is_overdue"] = is_overdue(ticket)
        return ticket


@mcp.tool()
def update_category(ticket_id: int, category: str, actor: str = "agent") -> dict[str, Any]:
    """
    Re-categorize a ticket. Allowed values: hardware, software, network, access, other.
    """
    allowed = {"hardware", "software", "network", "access", "other"}
    if category not in allowed:
        raise ValueError(f"Invalid category '{category}'. Allowed: {sorted(allowed)}")

    with db_cursor() as cur:
        cur.execute("SELECT category FROM tickets WHERE id = ?", (ticket_id,))
        existing = cur.fetchone()
        if existing is None:
            raise ValueError(f"Ticket {ticket_id} not found")

        cur.execute(
            "UPDATE tickets SET category = ?, updated_at = ? WHERE id = ?",
            (category, utc_now_iso(), ticket_id),
        )
        log_activity(cur, ticket_id, "category_changed", f"{existing['category']} -> {category}", actor=actor)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = row_to_dict(cur.fetchone())
        ticket["is_overdue"] = is_overdue(ticket)
        return ticket


@mcp.tool()
def escalate_ticket(ticket_id: int, reason: str = "", actor: str = "agent") -> dict[str, Any]:
    """
    Bump a ticket's priority one level (low -> medium -> high) and record why.
    Use when a ticket needs more urgent attention than its current priority reflects.
    """
    with db_cursor() as cur:
        cur.execute("SELECT priority FROM tickets WHERE id = ?", (ticket_id,))
        existing = cur.fetchone()
        if existing is None:
            raise ValueError(f"Ticket {ticket_id} not found")

        current_index = PRIORITY_ORDER.index(existing["priority"]) if existing["priority"] in PRIORITY_ORDER else 0
        new_priority = PRIORITY_ORDER[min(current_index + 1, len(PRIORITY_ORDER) - 1)]

        cur.execute(
            "UPDATE tickets SET priority = ?, updated_at = ? WHERE id = ?",
            (new_priority, utc_now_iso(), ticket_id),
        )
        detail = f"{existing['priority']} -> {new_priority}"
        if reason:
            detail += f" ({reason})"
        log_activity(cur, ticket_id, "escalated", detail, actor=actor)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = row_to_dict(cur.fetchone())
        ticket["is_overdue"] = is_overdue(ticket)
        return ticket


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


@mcp.tool()
def get_stats() -> dict[str, Any]:
    """
    Get board-wide stats: ticket counts by status and category, comment and
    activity-event totals, and how many open tickets are past their due date.
    """
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM tickets")
        total = int(cur.fetchone()["count"])

        cur.execute("SELECT status, COUNT(*) AS count FROM tickets GROUP BY status")
        by_status = {row["status"]: row["count"] for row in cur.fetchall()}

        cur.execute("SELECT category, COUNT(*) AS count FROM tickets GROUP BY category")
        by_category = {row["category"]: row["count"] for row in cur.fetchall()}

        cur.execute("SELECT COUNT(*) AS count FROM comments")
        comments = int(cur.fetchone()["count"])

        cur.execute("SELECT COUNT(*) AS count FROM activity_log")
        activity_events = int(cur.fetchone()["count"])

        cur.execute("SELECT * FROM tickets WHERE status != 'done' AND due_at IS NOT NULL")
        open_with_due = [row_to_dict(row) for row in cur.fetchall()]
        overdue = sum(1 for ticket in open_with_due if is_overdue(ticket))

    return {
        "total_tickets": total,
        "total_comments": comments,
        "total_activity_events": activity_events,
        "by_status": by_status,
        "by_category": by_category,
        "overdue_count": overdue,
    }


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
                "edit_ticket",
                "archive_ticket",
                "list_activity",
                "add_comment",
                "list_comments",
                "update_status",
                "assign_ticket",
                "update_category",
                "update_labels",
                "add_watcher",
                "remove_watcher",
                "add_attachment",
                "list_notifications",
                "save_filter",
                "list_filters",
                "bulk_update_status",
                "bulk_assign",
                "suggest_ticket_response",
                "summarize_ticket_handoff",
                "escalate_ticket",
                "get_stats",
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