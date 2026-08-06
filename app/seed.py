from __future__ import annotations

from datetime import timedelta, datetime, UTC

from app.db import db_cursor, init_db, next_ticket_key, utc_now_iso, log_activity, set_ticket_labels, create_notification


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
                "category": "software",
                "assignee": "alex",
                "requester": "priya",
                "due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            },
            {
                "title": "Add dark mode toggle",
                "description": "Users requested a basic dark theme in settings.",
                "status": "in_progress",
                "priority": "medium",
                "category": "software",
                "assignee": "sam",
                "requester": "jordan",
                "due_at": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
            },
            {
                "title": "Update onboarding copy",
                "description": "Marketing needs revised intro text for the first-run experience.",
                "status": "done",
                "priority": "low",
                "category": "other",
                "assignee": None,
                "requester": "taylor",
                "due_at": None,
            },
            {
                "title": "New laptop won't connect to VPN",
                "description": "Employee's new laptop fails to establish VPN connection from home network.",
                "status": "todo",
                "priority": "high",
                "category": "network",
                "assignee": None,
                "requester": "morgan",
                "due_at": (datetime.now(UTC) + timedelta(hours=4)).isoformat(),
            },
            {
                "title": "Locked out of shared drive",
                "description": "User lost access to the finance shared drive after a role change.",
                "status": "blocked",
                "priority": "medium",
                "category": "access",
                "assignee": "sam",
                "requester": "casey",
                "due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            },
        ]

        ticket_ids: list[int] = []

        for item in sample_tickets:
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
                    item["title"],
                    item["description"],
                    item["status"],
                    item["priority"],
                    item["category"],
                    item["assignee"],
                    item["requester"],
                    item["due_at"],
                    now,
                    now,
                ),
            )
            ticket_id = int(cur.lastrowid)
            log_activity(cur, ticket_id, "created", f"Ticket {key} created", actor="system")
            ticket_ids.append(ticket_id)

        set_ticket_labels(cur, ticket_ids[0], ["bug", "login", "urgent"])
        set_ticket_labels(cur, ticket_ids[1], ["feature", "ux"])
        set_ticket_labels(cur, ticket_ids[3], ["vpn", "remote"])

        cur.execute(
            "INSERT OR IGNORE INTO watchers (ticket_id, watcher, created_at) VALUES (?, ?, ?)",
            (ticket_ids[0], "alex", now),
        )
        cur.execute(
            "INSERT OR IGNORE INTO watchers (ticket_id, watcher, created_at) VALUES (?, ?, ?)",
            (ticket_ids[0], "priya", now),
        )
        cur.execute(
            "INSERT OR IGNORE INTO watchers (ticket_id, watcher, created_at) VALUES (?, ?, ?)",
            (ticket_ids[3], "morgan", now),
        )

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

            create_notification(cur, "Seed data loaded for Mini Jira MCP")
            create_notification(cur, "Ticket TKT-1 is overdue and needs attention", ticket_ids[0])