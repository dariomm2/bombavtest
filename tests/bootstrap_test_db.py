from __future__ import annotations

import os
import secrets
import sqlite3
from pathlib import Path

from backend.auth import password_digest

DB_PATH = Path(os.environ.get("BOMBAVTEST_DB_PATH", "/data/app.db"))
SCHEMA_PATH = Path("/app/migrations/001_create_schema.sql")

username = os.environ.get("BOMBAVTEST_ADMIN_USERNAME", "test-admin")
password = os.environ.get("BOMBAVTEST_ADMIN_PASSWORD", "TestAdmin123")
display_name = os.environ.get("BOMBAVTEST_ADMIN_DISPLAY_NAME", "Test Admin")

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

with sqlite3.connect(DB_PATH) as db:
    db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    # System/E2E data belongs to the test environment, not to migrations.
    salt = secrets.token_hex(16)
    db.execute(
        """
        INSERT INTO users(
            username, display_name, password_salt, password_hash,
            role, is_active, created_at
        )
        VALUES (?, ?, ?, ?, 'admin', 1, strftime('%Y-%m-%dT%H:%M:%f+00:00','now'))
        """,
        (username, display_name, salt, password_digest(password, salt)),
    )
    db.execute(
        """
        INSERT INTO topics(id, number, name, color, created_at)
        VALUES (1, 'TEST-1', 'Test topic', '#2563eb',
                strftime('%Y-%m-%dT%H:%M:%f+00:00','now'))
        """
    )
