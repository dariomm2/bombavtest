from __future__ import annotations

import os
import secrets
import sqlite3
import subprocess
import uuid
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
        # Test data is owned by the test suite, never by data migrations.
        db.execute(
            """
            INSERT INTO topics(id, number, name, color, created_at)
            VALUES (1, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%f+00:00','now'))
            """,
            ("TEST-1", "Test topic", "#2563eb"),
        )
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


@pytest.fixture()
def live_admin():
    import httpx2

    base_url = os.environ.get("BOMBAVTEST_TEST_URL", "http://127.0.0.1:18000")
    with httpx2.Client(base_url=base_url, timeout=10.0, follow_redirects=True) as live_client:
        login = live_client.post(
            "/api/login",
            json={"username": "test-admin", "password": "TestAdmin123"},
        )
        assert login.status_code == 200, login.text
        yield live_client, {"X-CSRF-Token": login.json()["data"]["csrf_token"]}


@pytest.fixture()
def live_topic_factory():
    def create(client, headers):
        marker = uuid.uuid4().hex[:10]
        return response_data(
            client.post(
                "/api/admin/topics",
                headers=headers,
                json={
                    "number": f"E2E-{marker}",
                    "name": f"Tema E2E {marker}",
                    "color": "#2563eb",
                    "attachment_draft_ids": [],
                },
            )
        )

    return create


@pytest.fixture()
def live_question_factory():
    def create(client, headers, *, topic_id: int = 1, text: str | None = None):
        marker = uuid.uuid4().hex[:10]
        correct_text = f"Correcta {marker}"
        wrong_text = f"Incorrecta {marker}"
        payload = response_data(
            client.post(
                "/api/admin/questions",
                headers=headers,
                json={
                    "topic_id": topic_id,
                    "text": text or f"Pregunta E2E {marker}",
                    "explanation": f"Explicación {marker}",
                    "options": [{"text": correct_text}, {"text": wrong_text}],
                },
            )
        )
        questions = response_data(client.get("/api/admin/questions"))
        question = next(item for item in questions if item["id"] == payload["id"])
        correct = next(option for option in question["options"] if option["is_correct"])
        wrong = next(option for option in question["options"] if not option["is_correct"])
        return {
            "id": question["id"],
            "text": question["text"],
            "correct_id": correct["id"],
            "correct_text": correct["text"],
            "wrong_id": wrong["id"],
            "wrong_text": wrong["text"],
        }

    return create


@pytest.fixture()
def live_user_factory():
    def create(client, headers, *, topic_ids: list[int] | None = None):
        marker = uuid.uuid4().hex[:10]
        username = f"e2e.{marker}"
        password = "Clave123"
        user_id = response_data(
            client.post(
                "/api/admin/users",
                headers=headers,
                json={
                    "username": username,
                    "display_name": f"Alumno E2E {marker}",
                    "role": "user",
                    "topic_ids": [1] if topic_ids is None else topic_ids,
                    "password": password,
                },
            )
        )["id"]
        return {"id": user_id, "username": username, "password": password}

    return create

COMPOSE_FILE = ROOT / "tests" / "docker-compose.test.yml"


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    if check and result.returncode != 0:
        raise RuntimeError(
            f"docker compose {' '.join(args)} failed\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )

    return result


def uses_docker_environment(items) -> bool:
    docker_test_dirs = (
        (ROOT / "tests" / "system").resolve(),
        (ROOT / "tests" / "e2e").resolve(),
    )

    for item in items:
        path = Path(item.path).resolve()
        for directory in docker_test_dirs:
            try:
                path.relative_to(directory)
                return True
            except ValueError:
                pass

    return False


@pytest.fixture(scope="session", autouse=True)
def docker_environment(request: pytest.FixtureRequest):
    if not uses_docker_environment(request.session.items):
        yield
        return

    compose("down", "--remove-orphans", check=False)
    compose(
        "up",
        "--build",
        "--force-recreate",
        "-d",
        "--wait",
        "--wait-timeout",
        "120",
    )

    try:
        yield
    finally:
        if request.session.testsfailed:
            logs = compose("logs", "--no-color", check=False)
            print("\n--- Docker logs ---")
            print(logs.stdout)
            if logs.stderr:
                print(logs.stderr)

        compose("down", "--remove-orphans", check=False)

