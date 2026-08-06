from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, HTTPException, Query

from app.db import (
    create_notification,
    db_cursor,
    get_ticket_attachments,
    get_ticket_labels,
    get_ticket_watchers,
    hydrate_ticket,
    row_to_dict,
    serialize_filter_definition,
    set_ticket_labels,
    utc_now_iso,
    next_ticket_key,
    log_activity,
    is_overdue,
)
from app.models import (
    AttachmentCreate,
    BulkAssignUpdate,
    BulkStatusUpdate,
    TicketCreate,
    TicketEdit,
    CommentCreate,
    LabelUpdate,
    SavedFilterCreate,
    TicketUpdateStatus,
    TicketAssign,
    TicketUpdateCategory,
    TicketEscalate,
    WatcherUpdate,
)

router = APIRouter(prefix="/api", tags=["api"])

PRIORITY_ORDER = ["low", "medium", "high"]


@router.get("/tickets")
def list_tickets(status: str | None = None, q: str | None = None, include_archived: bool = False) -> list[dict]:
    sql = "SELECT * FROM tickets WHERE 1=1"
    params: list[str] = []

    if not include_archived:
        sql += " AND is_archived = 0"

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
        return [hydrate_ticket(cur, row) for row in cur.fetchall()]


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
        ticket["labels"] = get_ticket_labels(cur, ticket_id)
        ticket["watchers"] = get_ticket_watchers(cur, ticket_id)
        ticket["attachments"] = get_ticket_attachments(cur, ticket_id)
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
        ticket_id = int(cur.lastrowid or 0)
        set_ticket_labels(cur, ticket_id, payload.labels)
        log_activity(cur, ticket_id, "created", f"Ticket {key} created", actor="dashboard")
        create_notification(cur, f"New ticket created: {key} - {payload.title}", ticket_id)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return hydrate_ticket(cur, cur.fetchone())


@router.put("/tickets/{ticket_id}")
def edit_ticket(ticket_id: int, payload: TicketEdit) -> dict:
    now = utc_now_iso()
    with db_cursor() as cur:
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        existing = cur.fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

        cur.execute(
            """
            UPDATE tickets
            SET title = ?, description = ?, priority = ?, category = ?, assignee = ?, requester = ?, due_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.title,
                payload.description,
                payload.priority,
                payload.category,
                payload.assignee,
                payload.requester,
                payload.due_at,
                now,
                ticket_id,
            ),
        )
        log_activity(cur, ticket_id, "edited", "Ticket fields updated", actor=payload.actor)
        create_notification(cur, f"Ticket {existing['key']} was updated", ticket_id)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return hydrate_ticket(cur, cur.fetchone())


@router.patch("/tickets/{ticket_id}/archive")
def archive_ticket(ticket_id: int) -> dict:
    with db_cursor() as cur:
        cur.execute("SELECT key, is_archived FROM tickets WHERE id = ?", (ticket_id,))
        existing = cur.fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

        next_value = 0 if existing["is_archived"] else 1
        cur.execute("UPDATE tickets SET is_archived = ?, updated_at = ? WHERE id = ?", (next_value, utc_now_iso(), ticket_id))
        state = "archived" if next_value else "restored"
        log_activity(cur, ticket_id, state, f"Ticket {existing['key']} {state}", actor="dashboard")
        create_notification(cur, f"Ticket {existing['key']} was {state}", ticket_id)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return hydrate_ticket(cur, cur.fetchone())


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
        create_notification(cur, f"Ticket assignment changed: {prev} -> {nxt}", ticket_id)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return hydrate_ticket(cur, cur.fetchone())


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
        create_notification(cur, f"Ticket category changed to {payload.category}", ticket_id)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return hydrate_ticket(cur, cur.fetchone())


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
        create_notification(cur, f"Ticket escalated: {detail}", ticket_id)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return hydrate_ticket(cur, cur.fetchone())


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
        comment_id = int(cur.lastrowid or 0)
        create_notification(cur, f"New comment added by {payload.author}", ticket_id)
        cur.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
        return row_to_dict(cur.fetchone())


@router.put("/tickets/{ticket_id}/labels")
def update_labels(ticket_id: int, payload: LabelUpdate) -> dict:
    with db_cursor() as cur:
        cur.execute("SELECT id, key FROM tickets WHERE id = ?", (ticket_id,))
        ticket = cur.fetchone()
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        set_ticket_labels(cur, ticket_id, payload.labels)
        log_activity(cur, ticket_id, "labels_updated", ", ".join(payload.labels) or "labels cleared", actor=payload.actor)
        create_notification(cur, f"Labels updated for {ticket['key']}", ticket_id)
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        return hydrate_ticket(cur, cur.fetchone())


@router.post("/tickets/{ticket_id}/watchers")
def add_watcher(ticket_id: int, payload: WatcherUpdate) -> list[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT key FROM tickets WHERE id = ?", (ticket_id,))
        ticket = cur.fetchone()
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        cur.execute(
            "INSERT OR IGNORE INTO watchers (ticket_id, watcher, created_at) VALUES (?, ?, ?)",
            (ticket_id, payload.watcher.strip(), utc_now_iso()),
        )
        log_activity(cur, ticket_id, "watcher_added", payload.watcher.strip(), actor=payload.actor)
        create_notification(cur, f"{payload.watcher.strip()} is now watching {ticket['key']}", ticket_id)
        return get_ticket_watchers(cur, ticket_id)


@router.delete("/tickets/{ticket_id}/watchers/{watcher}")
def remove_watcher(ticket_id: int, watcher: str) -> list[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        cur.execute("DELETE FROM watchers WHERE ticket_id = ? AND watcher = ?", (ticket_id, watcher))
        log_activity(cur, ticket_id, "watcher_removed", watcher, actor="dashboard")
        return get_ticket_watchers(cur, ticket_id)


@router.post("/tickets/{ticket_id}/attachments")
def add_attachment(ticket_id: int, payload: AttachmentCreate) -> list[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT key FROM tickets WHERE id = ?", (ticket_id,))
        ticket = cur.fetchone()
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        cur.execute(
            """
            INSERT INTO attachments (ticket_id, filename, content_type, content_base64, uploaded_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ticket_id, payload.filename, payload.content_type, payload.content_base64, payload.uploaded_by, utc_now_iso()),
        )
        log_activity(cur, ticket_id, "attachment_added", payload.filename, actor=payload.uploaded_by)
        create_notification(cur, f"Attachment added to {ticket['key']}: {payload.filename}", ticket_id)
        return get_ticket_attachments(cur, ticket_id)


@router.get("/notifications")
def list_notifications(include_read: bool = False) -> list[dict]:
    with db_cursor() as cur:
        sql = "SELECT * FROM notifications"
        params: list[object] = []
        if not include_read:
            sql += " WHERE is_read = 0"
        sql += " ORDER BY id DESC LIMIT 50"
        cur.execute(sql, params)
        return [row_to_dict(row) for row in cur.fetchall()]


@router.patch("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int) -> dict:
    with db_cursor() as cur:
        cur.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
        cur.execute("SELECT * FROM notifications WHERE id = ?", (notification_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Notification not found")
        return row_to_dict(row)


@router.get("/filters")
def list_saved_filters() -> list[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM saved_filters ORDER BY name ASC")
        return [row_to_dict(row) for row in cur.fetchall()]


@router.post("/filters")
def create_saved_filter(payload: SavedFilterCreate) -> dict:
    definition = {
        "status": payload.status,
        "category": payload.category,
        "query": payload.query,
        "labels": payload.labels,
    }
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO saved_filters (name, definition, created_at) VALUES (?, ?, ?)",
            (payload.name, serialize_filter_definition(definition), utc_now_iso()),
        )
        saved_id = int(cur.lastrowid or 0)
        cur.execute("SELECT * FROM saved_filters WHERE id = ?", (saved_id,))
        return row_to_dict(cur.fetchone())


@router.delete("/filters/{filter_id}")
def delete_saved_filter(filter_id: int) -> dict:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM saved_filters WHERE id = ?", (filter_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Saved filter not found")
        saved = row_to_dict(row)
        cur.execute("DELETE FROM saved_filters WHERE id = ?", (filter_id,))
        return saved


@router.patch("/tickets/bulk/status")
def bulk_update_status(payload: BulkStatusUpdate) -> dict:
    updated: list[int] = []
    with db_cursor() as cur:
        for ticket_id in payload.ticket_ids:
            cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
            if cur.fetchone() is None:
                continue
            cur.execute("UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?", (payload.status, utc_now_iso(), ticket_id))
            log_activity(cur, ticket_id, "bulk_status_changed", payload.status, actor=payload.actor)
            updated.append(ticket_id)
        create_notification(cur, f"Bulk status update applied to {len(updated)} ticket(s)")
    return {"updated_ticket_ids": updated, "status": payload.status}


@router.patch("/tickets/bulk/assign")
def bulk_assign(payload: BulkAssignUpdate) -> dict:
    updated: list[int] = []
    with db_cursor() as cur:
        for ticket_id in payload.ticket_ids:
            cur.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
            if cur.fetchone() is None:
                continue
            cur.execute("UPDATE tickets SET assignee = ?, updated_at = ? WHERE id = ?", (payload.assignee, utc_now_iso(), ticket_id))
            log_activity(cur, ticket_id, "bulk_assigned", payload.assignee or "unassigned", actor=payload.actor)
            updated.append(ticket_id)
        create_notification(cur, f"Bulk assignment applied to {len(updated)} ticket(s)")
    return {"updated_ticket_ids": updated, "assignee": payload.assignee}


@router.get("/agent/suggestions/{ticket_id}")
def get_agent_suggestion(ticket_id: int) -> dict:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        ticket = hydrate_ticket(cur, row)
        summary = f"{ticket['title']} ({ticket['category']}, priority {ticket['priority']})"
        suggested_comment = (
            f"Suggested next step: verify {ticket['category']} details, confirm impact with "
            f"{ticket['requester'] or 'the requester'}, and update the ticket after reproduction."
        )
        triage = {
            "suggested_status": "in_progress" if ticket["status"] == "todo" else ticket["status"],
            "suggested_assignee": ticket["assignee"] or "triage-team",
            "suggested_labels": ticket["labels"] or [ticket["category"], ticket["priority"]],
        }
        return {"summary": summary, "suggested_comment": suggested_comment, "triage": triage}


@router.get("/agent/handoff/{ticket_id}")
def get_handoff_summary(ticket_id: int) -> dict:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        ticket = hydrate_ticket(cur, row)
        cur.execute("SELECT author, body, created_at FROM comments WHERE ticket_id = ? ORDER BY id ASC", (ticket_id,))
        comments = [row_to_dict(comment) for comment in cur.fetchall()]
        cur.execute("SELECT event_type, detail, actor, created_at FROM activity_log WHERE ticket_id = ? ORDER BY id ASC", (ticket_id,))
        activity = [row_to_dict(entry) for entry in cur.fetchall()]

        summary_parts = [
            f"Ticket {ticket['key']}: {ticket['title']}",
            f"Status: {ticket['status']}, priority: {ticket['priority']}, category: {ticket['category']}",
            f"Requester: {ticket['requester'] or 'unknown'}, assignee: {ticket['assignee'] or 'unassigned'}",
        ]
        if comments:
            summary_parts.append(f"Latest comment by {comments[-1]['author']}: {comments[-1]['body']}")
        if activity:
            latest = activity[-1]
            summary_parts.append(f"Latest activity: {latest['event_type']} by {latest['actor']} ({latest['detail']})")
        return {"ticket_id": ticket_id, "handoff_summary": " | ".join(summary_parts)}


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
        cur.execute("SELECT COUNT(*) AS count FROM tickets WHERE is_archived = 0")
        total = int(cur.fetchone()["count"])

        cur.execute("SELECT status, COUNT(*) AS count FROM tickets WHERE is_archived = 0 GROUP BY status")
        by_status = {row["status"]: row["count"] for row in cur.fetchall()}

        cur.execute("SELECT category, COUNT(*) AS count FROM tickets WHERE is_archived = 0 GROUP BY category")
        by_category = {row["category"]: row["count"] for row in cur.fetchall()}

        cur.execute(
            """
            SELECT l.name, COUNT(*) AS count
            FROM labels l
            INNER JOIN ticket_labels tl ON tl.label_id = l.id
            INNER JOIN tickets t ON t.id = tl.ticket_id
            WHERE t.is_archived = 0
            GROUP BY l.name
            ORDER BY count DESC, l.name ASC
            """
        )
        by_label = {row["name"]: row["count"] for row in cur.fetchall()}

        cur.execute("SELECT COUNT(*) AS count FROM comments")
        comments = int(cur.fetchone()["count"])

        cur.execute("SELECT COUNT(*) AS count FROM activity_log")
        activity_events = int(cur.fetchone()["count"])

        cur.execute("SELECT COUNT(*) AS count FROM notifications WHERE is_read = 0")
        unread_notifications = int(cur.fetchone()["count"])

        cur.execute("SELECT COUNT(*) AS count FROM watchers")
        watcher_count = int(cur.fetchone()["count"])

        cur.execute("SELECT COUNT(*) AS count FROM attachments")
        attachment_count = int(cur.fetchone()["count"])

        cur.execute("SELECT COUNT(*) AS count FROM saved_filters")
        saved_filter_count = int(cur.fetchone()["count"])

        cur.execute("SELECT * FROM tickets WHERE status != 'done' AND due_at IS NOT NULL AND is_archived = 0")
        open_with_due = [row_to_dict(row) for row in cur.fetchall()]
        overdue = sum(1 for ticket in open_with_due if is_overdue(ticket))

    return {
        "total_tickets": total,
        "total_comments": comments,
        "total_activity_events": activity_events,
        "by_status": by_status,
        "by_category": by_category,
        "by_label": by_label,
        "overdue_count": overdue,
        "unread_notifications": unread_notifications,
        "watcher_count": watcher_count,
        "attachment_count": attachment_count,
        "saved_filter_count": saved_filter_count,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }