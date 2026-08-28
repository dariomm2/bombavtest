from __future__ import annotations

import secrets
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend import main as app_module

ROOT = Path(__file__).resolve().parent.parent


def apply_schema(db_path: Path) -> None:
    db = sqlite3.connect(db_path)
    try:
        db.executescript((ROOT / "migrations" / "001_create_schema.sql").read_text(encoding="utf-8"))
        db.executescript((ROOT / "migrations" / "003_insert_official_topics.sql").read_text(encoding="utf-8"))
        salt = secrets.token_hex(16)
        db.execute(
            """
            INSERT INTO users(username, display_name, password_salt, password_hash, role, is_active, created_at)
            VALUES (?, ?, ?, ?, 'admin', 1, strftime('%Y-%m-%dT%H:%M:%f+00:00','now'))
            """,
            ("admin", "Admin", salt, auth.password_digest("admin", salt)),
        )
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def app_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "app.db"
    apply_schema(db_path)
    monkeypatch.setenv("BOMBAVTEST_DB_PATH", str(db_path))
    auth.LOGIN_ATTEMPTS.clear()
    yield db_path
    auth.LOGIN_ATTEMPTS.clear()


@pytest.fixture()
def client(app_env: Path):
    with TestClient(app_module.app) as test_client:
        yield test_client


@pytest.fixture()
def admin(client: TestClient):
    response = client.post("/api/login", json={"username": "admin", "password": "admin"})
    assert response.status_code == 200
    data = response.json()["data"]
    return client, {"X-CSRF-Token": data["csrf_token"]}
