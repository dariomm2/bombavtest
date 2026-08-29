from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

from backend.db import connect_db
from tests.conftest import ROOT


def test_schema_topics_and_sqlite_pragmas(app_env: Path):
    db = connect_db(app_env)
    try:
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert db.execute("SELECT COUNT(*) FROM topics").fetchone()[0] == 38
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        assert {"users", "topics", "questions", "options", "attempts", "sessions", "user_topics"} <= tables
    finally:
        db.close()


def test_foreign_key_integrity(app_env: Path):
    with sqlite3.connect(app_env) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_real_yoyo_migrations_build_a_valid_database(tmp_path: Path):
    if shutil.which("yoyo") is None:
        import pytest
        pytest.skip("yoyo CLI is installed with requirements.txt")
    db_path = tmp_path / "migrated.db"
    env = os.environ | {
        "BOMBAVTEST_ADMIN_USERNAME": "migration-admin",
        "BOMBAVTEST_ADMIN_PASSWORD": "Migration123",
        "BOMBAVTEST_ADMIN_DISPLAY_NAME": "Migration Admin",
    }
    command = [
        "yoyo", "apply", "--batch", "--no-config-file",
        "--database", f"sqlite:///{db_path}", str(ROOT / "migrations"),
    ]
    subprocess.run(command, check=True, cwd=ROOT, env=env, capture_output=True, text=True)
    subprocess.run(command, check=True, cwd=ROOT, env=env, capture_output=True, text=True)

    with sqlite3.connect(db_path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT COUNT(*) FROM topics").fetchone()[0] == 38
        assert db.execute("SELECT username FROM users WHERE role = 'admin'").fetchone()[0] == "migration-admin"
