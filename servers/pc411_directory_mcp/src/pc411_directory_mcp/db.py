from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator

from pc411_directory_mcp.settings import settings


@contextmanager
def db_cursor() -> Iterator[sqlite3.Cursor]:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        yield cursor
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with db_cursor() as cursor:
        cursor.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS organizations (
                id INTEGER PRIMARY KEY,
                source_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                parent_id INTEGER NULL REFERENCES organizations(id) ON DELETE CASCADE,
                depth INTEGER NOT NULL,
                path TEXT NOT NULL UNIQUE
            );
            CREATE INDEX IF NOT EXISTS idx_organizations_parent ON organizations(parent_id);

            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                title TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                manager_id INTEGER NULL REFERENCES people(id) ON DELETE SET NULL,
                is_manager INTEGER NOT NULL DEFAULT 0,
                is_synthetic INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_people_organization ON people(organization_id);
            CREATE INDEX IF NOT EXISTS idx_people_manager ON people(manager_id);
            """
        )
