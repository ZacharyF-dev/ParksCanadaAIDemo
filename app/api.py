from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, HTTPException, Query

from app.db import (
    db_cursor,
    row_to_dict,
    utc_now_iso,
    next_ticket_key,
    log_activity,
    is_overdue,
)
from app.models import (
    TicketCreate,
    CommentCreate,
    TicketUpdateStatus,
    TicketAssign,
    TicketUpdateCategory,
    TicketEscalate,
)

router = APIRouter(prefix="/api", tags=["api"])

PRIORITY_ORDER = ["low", "medium", "high"]


@router.get("/tickets")
def list_tickets(status: str | None = None, q: str | None = None) -> list[dict]:
    sql = "SELECT * FROM tickets WHERE 1=1"
    params: list[str] = []

    if status:
        sql += " AND status = ?"
        params.append(status)

    if q:
        sql += " AND (title LIKE ? OR description LIKE ? OR key LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])

    sql += " ORDER BY id DESC"

    with db_cursor() as cur:
        cur.execute(sql, params)
        tickets = [row_to_dict(row) for row in cur.fetchall()]
        for ticket in tickets:
            ticket["is_overdue"] = is_overdue(ticket)
        return tickets


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int) -> dict:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

        cur.execute(
            "SELECT * FROM comments WHERE ticket_id = ? ORDER BY id ASC",
            (ticket_id,),
        )
        comments = [row_to_dict(comment) for comment in cur.fetchall()]

        cur.execute(
            "SELECT * FROM activity_log WHERE ticket_id = ? ORDER BY id ASC",
            (ticket_id,),
        )
        activity = [row_to_dict(entry) for entry in cur.fetchall()]

        ticket = row_to_dict(row)
        ticket["comments"] = comments
        ticket["activity"] = activity
        ticket["is_overdue"] = is_overdue(ticket)
        return ticket


@router.get("/tickets/{ticket_id}/activity")
def list_activity(ticket_id: int) -> list[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

        cur.execute(
            "SELECT * FROM activity_log WHERE ticket_id = ? ORDER BY id ASC",
            (ticket_id,),
        )
        return [row_to_dict(row) for row in cur.fetchall()]


@router.post("/tickets")
def create_ticket(payload: TicketCreate) -> dict:
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
            (
                key,
                payload.title,
                payload.description,
                "todo",
                payload.priority,
                payload.category,
                payload.assignee,
                payload.requester,
                payload.due_at,
                now,
                now,
            ),
        )
        ticket_id = int(cur.lastrowid)
        log_activity(cur, ticket_id, "created", f"Ticket {key} created", actor="dashboard")
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = row_to_dict(cur.fetchone())
        ticket["is_overdue"] = is_overdue(ticket)
        return ticket


@router.patch("/tickets/{ticket_id}/status")
def update_ticket_status(ticket_id: int, payload: TicketUpdateStatus) -> dict:
    now = utc_now_iso()
    with db_cursor() as cur:
        cur.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,))
        existing = cur.fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

        cur.execute(
            "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
            (payload.status, now, ticket_id),
        )
        log_activity(
            cur,
            ticket_id,
            "status_changed",
            f"{existing['status']} -> {payload.status}",
            actor=payload.actor,
        )
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = row_to_dict(cur.fetchone())
        ticket["is_overdue"] = is_overdue(ticket)
        return ticket


@router.patch("/tickets/{ticket_id}/assign")
def assign_ticket(ticket_id: int, payload: TicketAssign) -> dict:
    now = utc_now_iso()
    with db_cursor() as cur:
        cur.execute("SELECT assignee FROM tickets WHERE id = ?", (ticket_id,))
        existing = cur.fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

        cur.execute(
            "UPDATE tickets SET assignee = ?, updated_at = ? WHERE id = ?",
            (payload.assignee, now, ticket_id),
        )
        prev = existing["assignee"] or "unassigned"
        nxt = payload.assignee or "unassigned"
        log_activity(cur, ticket_id, "assigned", f"{prev} -> {nxt}", actor=payload.actor)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = row_to_dict(cur.fetchone())
        ticket["is_overdue"] = is_overdue(ticket)
        return ticket


@router.patch("/tickets/{ticket_id}/category")
def update_ticket_category(ticket_id: int, payload: TicketUpdateCategory) -> dict:
    now = utc_now_iso()
    with db_cursor() as cur:
        cur.execute("SELECT category FROM tickets WHERE id = ?", (ticket_id,))
        existing = cur.fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

        cur.execute(
            "UPDATE tickets SET category = ?, updated_at = ? WHERE id = ?",
            (payload.category, now, ticket_id),
        )
        log_activity(
            cur,
            ticket_id,
            "category_changed",
            f"{existing['category']} -> {payload.category}",
            actor=payload.actor,
        )
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = row_to_dict(cur.fetchone())
        ticket["is_overdue"] = is_overdue(ticket)
        return ticket


@router.post("/tickets/{ticket_id}/escalate")
def escalate_ticket(ticket_id: int, payload: TicketEscalate) -> dict:
    now = utc_now_iso()
    with db_cursor() as cur:
        cur.execute("SELECT priority FROM tickets WHERE id = ?", (ticket_id,))
        existing = cur.fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

        current_index = PRIORITY_ORDER.index(existing["priority"]) if existing["priority"] in PRIORITY_ORDER else 0
        new_priority = PRIORITY_ORDER[min(current_index + 1, len(PRIORITY_ORDER) - 1)]

        cur.execute(
            "UPDATE tickets SET priority = ?, updated_at = ? WHERE id = ?",
            (new_priority, now, ticket_id),
        )
        detail = f"{existing['priority']} -> {new_priority}"
        if payload.reason:
            detail += f" ({payload.reason})"
        log_activity(cur, ticket_id, "escalated", detail, actor=payload.actor)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = row_to_dict(cur.fetchone())
        ticket["is_overdue"] = is_overdue(ticket)
        return ticket


@router.post("/tickets/{ticket_id}/comments")
def add_comment(ticket_id: int, payload: CommentCreate) -> dict:
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

        cur.execute(
            """
            INSERT INTO comments (ticket_id, author, body, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (ticket_id, payload.author, payload.body, utc_now_iso()),
        )
        comment_id = int(cur.lastrowid)
        cur.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
        return row_to_dict(cur.fetchone())


@router.get("/tickets/{ticket_id}/comments")
def list_comments(ticket_id: int) -> list[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

        cur.execute("SELECT * FROM comments WHERE ticket_id = ? ORDER BY id ASC", (ticket_id,))
        return [row_to_dict(row) for row in cur.fetchall()]


@router.get("/stats")
def get_stats() -> dict:
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
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }