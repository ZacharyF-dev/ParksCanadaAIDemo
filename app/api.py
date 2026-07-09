from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, HTTPException, Query

from app.db import db_cursor, row_to_dict, utc_now_iso, next_ticket_key
from app.models import TicketCreate, CommentCreate, TicketUpdateStatus, TicketAssign

router = APIRouter(prefix="/api", tags=["api"])


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
        return [row_to_dict(row) for row in cur.fetchall()]


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

        ticket = row_to_dict(row)
        ticket["comments"] = comments
        return ticket


@router.post("/tickets")
def create_ticket(payload: TicketCreate) -> dict:
    now = utc_now_iso()
    with db_cursor() as cur:
        key = next_ticket_key(cur)
        cur.execute(
            """
            INSERT INTO tickets (key, title, description, status, priority, assignee, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                payload.title,
                payload.description,
                "todo",
                payload.priority,
                payload.assignee,
                now,
                now,
            ),
        )
        ticket_id = int(cur.lastrowid)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return row_to_dict(cur.fetchone())


@router.patch("/tickets/{ticket_id}/status")
def update_ticket_status(ticket_id: int, payload: TicketUpdateStatus) -> dict:
    now = utc_now_iso()
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

        cur.execute(
            "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
            (payload.status, now, ticket_id),
        )
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return row_to_dict(cur.fetchone())


@router.patch("/tickets/{ticket_id}/assign")
def assign_ticket(ticket_id: int, payload: TicketAssign) -> dict:
    now = utc_now_iso()
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

        cur.execute(
            "UPDATE tickets SET assignee = ?, updated_at = ? WHERE id = ?",
            (payload.assignee, now, ticket_id),
        )
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return row_to_dict(cur.fetchone())


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

        cur.execute("SELECT COUNT(*) AS count FROM comments")
        comments = int(cur.fetchone()["count"])

    return {
        "total_tickets": total,
        "total_comments": comments,
        "by_status": by_status,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }