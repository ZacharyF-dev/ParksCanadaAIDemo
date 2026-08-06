from __future__ import annotations

import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime, UTC
from pathlib import Path
from typing import Iterator, Any

from app.config import settings


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_cursor() -> Iterator[sqlite3.Cursor]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()


def _existing_columns(cur: sqlite3.Cursor, table: str) -> set[str]:
    cur.execute(f"PRAGMA table_info({table})")
    return {row["name"] for row in cur.fetchall()}


def _migrate_tickets_table(cur: sqlite3.Cursor) -> None:
    """Add newer columns to an existing tickets table without losing data."""
    columns = _existing_columns(cur, "tickets")

    if "category" not in columns:
        cur.execute("ALTER TABLE tickets ADD COLUMN category TEXT NOT NULL DEFAULT 'other'")
    if "requester" not in columns:
        cur.execute("ALTER TABLE tickets ADD COLUMN requester TEXT NULL")
    if "due_at" not in columns:
        cur.execute("ALTER TABLE tickets ADD COLUMN due_at TEXT NULL")
    if "is_archived" not in columns:
        cur.execute("ALTER TABLE tickets ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0")


def init_db() -> None:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    with db_cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                priority TEXT NOT NULL,
                assignee TEXT NULL,
                requester TEXT NULL,
                category TEXT NOT NULL DEFAULT 'other',
                due_at TEXT NULL,
                is_archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                author TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS labels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_labels (
                ticket_id INTEGER NOT NULL,
                label_id INTEGER NOT NULL,
                PRIMARY KEY (ticket_id, label_id),
                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
                FOREIGN KEY (label_id) REFERENCES labels(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS watchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                watcher TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(ticket_id, watcher),
                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                content_base64 TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE SET NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                definition TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                actor TEXT NOT NULL DEFAULT 'system',
                event_type TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
            )
            """
        )

        # Backfill columns for DBs created before this schema existed.
        _migrate_tickets_table(cur)


def next_ticket_key(cur: sqlite3.Cursor) -> str:
    cur.execute("SELECT id FROM tickets ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    next_id = 1 if row is None else int(row["id"]) + 1
    return f"TKT-{next_id}"


def log_activity(
    cur: sqlite3.Cursor,
    ticket_id: int,
    event_type: str,
    detail: str = "",
    actor: str = "system",
) -> None:
    """Record a system-generated audit entry for a ticket (status/assignee/category
    changes, escalations, creation), distinct from human/agent comments."""
    cur.execute(
        """
        INSERT INTO activity_log (ticket_id, actor, event_type, detail, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (ticket_id, actor, event_type, detail, utc_now_iso()),
    )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def get_ticket_labels(cur: sqlite3.Cursor, ticket_id: int) -> list[str]:
    cur.execute(
        """
        SELECT l.name
        FROM labels l
        INNER JOIN ticket_labels tl ON tl.label_id = l.id
        WHERE tl.ticket_id = ?
        ORDER BY l.name ASC
        """,
        (ticket_id,),
    )
    return [row["name"] for row in cur.fetchall()]


def set_ticket_labels(cur: sqlite3.Cursor, ticket_id: int, labels: list[str]) -> None:
    normalized = sorted({label.strip().lower() for label in labels if label and label.strip()})
    cur.execute("DELETE FROM ticket_labels WHERE ticket_id = ?", (ticket_id,))
    for label in normalized:
        cur.execute("INSERT OR IGNORE INTO labels (name) VALUES (?)", (label,))
        cur.execute("SELECT id FROM labels WHERE name = ?", (label,))
        label_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT OR IGNORE INTO ticket_labels (ticket_id, label_id) VALUES (?, ?)",
            (ticket_id, label_id),
        )


def get_ticket_watchers(cur: sqlite3.Cursor, ticket_id: int) -> list[dict[str, Any]]:
    cur.execute(
        "SELECT id, watcher, created_at FROM watchers WHERE ticket_id = ? ORDER BY watcher ASC",
        (ticket_id,),
    )
    return [row_to_dict(row) for row in cur.fetchall()]


def get_ticket_attachments(cur: sqlite3.Cursor, ticket_id: int) -> list[dict[str, Any]]:
    cur.execute(
        "SELECT id, filename, content_type, uploaded_by, created_at FROM attachments WHERE ticket_id = ? ORDER BY id ASC",
        (ticket_id,),
    )
    return [row_to_dict(row) for row in cur.fetchall()]


def create_notification(cur: sqlite3.Cursor, message: str, ticket_id: int | None = None) -> None:
    cur.execute(
        "INSERT INTO notifications (ticket_id, message, created_at, is_read) VALUES (?, ?, ?, 0)",
        (ticket_id, message, utc_now_iso()),
    )


def serialize_filter_definition(definition: dict[str, Any]) -> str:
    return json.dumps(definition, sort_keys=True)


def hydrate_ticket(cur: sqlite3.Cursor, row: sqlite3.Row) -> dict[str, Any]:
    ticket = row_to_dict(row)
    ticket["labels"] = get_ticket_labels(cur, ticket["id"])
    ticket["watchers"] = get_ticket_watchers(cur, ticket["id"])
    ticket["attachments"] = get_ticket_attachments(cur, ticket["id"])
    ticket["is_overdue"] = is_overdue(ticket)
    return ticket


def is_overdue(ticket_row: dict[str, Any]) -> bool:
    due_at = ticket_row.get("due_at")
    if not due_at or ticket_row.get("status") == "done":
        return False
    try:
        due = datetime.fromisoformat(due_at)
    except ValueError:
        return False
    if due.tzinfo is None:
        due = due.replace(tzinfo=UTC)
    return due < datetime.now(UTC)