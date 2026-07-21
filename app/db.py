from __future__ import annotations

import sqlite3
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