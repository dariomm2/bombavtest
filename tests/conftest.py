from __future__ import annotations

import secrets
import sqlite3
from pathlib import Path
from typing import Callable

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


def response_data(response):
    assert response.status_code < 400, response.text
    return response.json()["data"]


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
    login = client.post("/api/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    return client, {"X-CSRF-Token": login.json()["data"]["csrf_token"]}


@pytest.fixture()
def question_factory() -> Callable:
    def create(client: TestClient, headers: dict[str, str], *, topic_id: int = 1, text: str = "[TEST] Pregunta"):
        created = response_data(
            client.post(
                "/api/admin/questions",
                headers=headers,
                json={
                    "topic_id": topic_id,
                    "text": text,
                    "explanation": "Explicación",
                    "options": [{"text": "Correcta"}, {"text": "Incorrecta"}],
                },
            )
        )
        question_id = created["id"]
        questions = response_data(client.get("/api/admin/questions"))
        question = next(item for item in questions if item["id"] == question_id)
        return question_id, question["options"][0]["id"], question["options"][1]["id"]

    return create


@pytest.fixture()
def user_factory() -> Callable:
    counter = 0

    def create(
        client: TestClient,
        headers: dict[str, str],
        *,
        username: str | None = None,
        display_name: str = "Alumno",
        role: str = "user",
        topic_ids: list[int] | None = None,
        password: str = "Clave123",
    ) -> int:
        nonlocal counter
        counter += 1
        username = username or f"alumno{counter}"
        payload = {
            "username": username,
            "display_name": display_name,
            "role": role,
            "topic_ids": [1] if topic_ids is None else topic_ids,
            "password": password,
        }
        return response_data(client.post("/api/admin/users", headers=headers, json=payload))["id"]

    return create


@pytest.fixture()
def login_user(request: pytest.FixtureRequest) -> Callable:
    clients: list[TestClient] = []

    def login(app, username: str, password: str = "Clave123"):
        user = TestClient(app)
        clients.append(user)
        response = user.post("/api/login", json={"username": username, "password": password})
        assert response.status_code == 200, response.text
        return user, {"X-CSRF-Token": response.json()["data"]["csrf_token"]}

    request.addfinalizer(lambda: [user.close() for user in clients])
    return login
