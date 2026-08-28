from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.db import connect_db


def test_schema_topics_and_sqlite_pragmas(app_env: Path):
    db = connect_db(app_env)
    try:
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert db.execute("SELECT COUNT(*) FROM topics").fetchone()[0] == 38
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "simulations" not in tables
        assert "simulation_questions" not in tables
    finally:
        db.close()


def test_foreign_key_integrity(app_env: Path):
    db = sqlite3.connect(app_env)
    try:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        db.close()
