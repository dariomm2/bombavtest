from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.db import connect_db


def test_initial_schema_and_sqlite_pragmas(app_env: Path):
    db = connect_db(app_env)
    try:
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000

        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "users",
            "topics",
            "questions",
            "options",
            "attempts",
            "sessions",
            "user_topics",
            "topic_attachments",
            "topic_attachment_drafts",
        } <= tables
    finally:
        db.close()


def test_database_integrity(app_env: Path):
    with sqlite3.connect(app_env) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
