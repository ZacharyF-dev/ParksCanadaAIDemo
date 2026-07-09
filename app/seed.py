from __future__ import annotations

from app.db import db_cursor, init_db, next_ticket_key, utc_now_iso


def seed_if_empty() -> None:
    init_db()
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM tickets")
        count = int(cur.fetchone()["count"])
        if count > 0:
            return

        now = utc_now_iso()

        sample_tickets = [
            {
                "title": "Login page throws error on empty password",
                "description": "Repro: open login page, leave password blank, submit form.",
                "status": "todo",
                "priority": "high",
                "assignee": "alex",
            },
            {
                "title": "Add dark mode toggle",
                "description": "Users requested a basic dark theme in settings.",
                "status": "in_progress",
                "priority": "medium",
                "assignee": "sam",
            },
            {
                "title": "Update onboarding copy",
                "description": "Marketing needs revised intro text for the first-run experience.",
                "status": "done",
                "priority": "low",
                "assignee": None,
            },
        ]

        ticket_ids: list[int] = []

        for item in sample_tickets:
            key = next_ticket_key(cur)
            cur.execute(
                """
                INSERT INTO tickets (key, title, description, status, priority, assignee, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    item["title"],
                    item["description"],
                    item["status"],
                    item["priority"],
                    item["assignee"],
                    now,
                    now,
                ),
            )
            ticket_ids.append(int(cur.lastrowid))

        sample_comments = [
            (ticket_ids[0], "alex", "I can reproduce this locally."),
            (ticket_ids[0], "jordan", "Please prioritize for this sprint."),
            (ticket_ids[1], "sam", "Initial settings toggle is in progress."),
            (ticket_ids[2], "taylor", "Copy updated and reviewed."),
        ]

        for ticket_id, author, body in sample_comments:
            cur.execute(
                """
                INSERT INTO comments (ticket_id, author, body, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (ticket_id, author, body, now),
            )