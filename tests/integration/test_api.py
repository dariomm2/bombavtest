from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import response_data


def test_health_frontend_and_auth(client: TestClient):
    assert client.get("/health").json() == {"ok": True, "status": "healthy", "version": "dev", "revision": "unknown"}
    assert 'window.BOMBAVTEST_VERSION = "dev";' in client.get("/version.js").text
    for path in ["/", "/login", "/statistics", "/questions", "/admin", "/styles.css", "/script.js"]:
        assert client.get(path).status_code == 200
    for path in ["/docs", "/redoc", "/openapi.json"]:
        assert client.get(path).status_code == 404
    assert client.get("/api/me").status_code == 401


def test_login_me_logout_and_cookie(client: TestClient):
    login = client.post("/api/login", json={"username": "ADMIN", "password": "admin"})
    assert login.status_code == 200
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    csrf = login.json()["data"]["csrf_token"]
    assert client.get("/api/me").json()["data"]["user"]["role"] == "admin"
    assert client.post("/api/logout").status_code == 403
    assert client.post("/api/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize(
    "payload,status",
    [
        ({}, 400),
        ({"username": "admin", "password": "bad"}, 401),
        ({"username": "missing", "password": "whatever"}, 401),
        ({"username": "x" * 81, "password": "admin"}, 401),
    ],
)
def test_login_rejects_invalid_credentials(client: TestClient, payload, status):
    assert client.post("/api/login", json=payload).status_code == status


def test_secure_cookie_when_request_is_https(client: TestClient):
    response = client.post(
        "/api/login",
        headers={"X-Forwarded-Proto": "https"},
        json={"username": "admin", "password": "admin"},
    )
    cookie = response.headers["set-cookie"].lower()
    assert response.status_code == 200
    assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_login_rate_limit(client: TestClient):
    for _ in range(10):
        assert client.post("/api/login", json={"username": "no-existe", "password": "incorrecta"}).status_code == 401
    limited = client.post("/api/login", json={"username": "no-existe", "password": "incorrecta"})
    assert limited.status_code == 429
    assert limited.json()["code"] == "RATE_LIMIT"


def test_csrf_and_admin_permissions(admin, user_factory, login_user):
    client, headers = admin
    assert client.post("/api/admin/topics", json={}).status_code == 403
    user_factory(client, headers, username="alumno")
    user, _ = login_user(client.app, "alumno")
    assert user.get("/api/admin/users").status_code == 403


def test_practice_pending_all_and_home(admin, user_factory, question_factory, login_user):
    client, headers = admin
    qid, correct_id, _ = question_factory(client, headers)
    user_factory(client, headers, username="alumno")
    user, user_headers = login_user(client.app, "alumno")

    question = response_data(user.get("/api/practice/question?topic_id=1&mode=pending"))
    assert question["id"] == qid
    assert question["correct_option_id"] == correct_id

    response_data(
        user.post(
            "/api/answers",
            headers=user_headers,
            json={"question_id": qid, "selected_option_id": correct_id, "submission_key": uuid.uuid4().hex},
        )
    )
    no_pending = user.get("/api/practice/question?topic_id=1&mode=pending")
    assert no_pending.status_code == 404 and no_pending.json()["code"] == "NO_QUESTIONS"
    assert response_data(user.get("/api/practice/question?topic_id=1&mode=all"))["id"] == qid

    home = response_data(user.get("/api/home"))
    assert home["total_answered"] == 1
    assert home["unique_correct"] == 1
    topic = next(item for item in home["topics"] if item["id"] == 1)
    assert topic["total"] == 1 and topic["correct"] == 1 and topic["completion"] == 100.0
    assert len(home["activity"]) == 28


@pytest.mark.parametrize(
    "query,status",
    [
        ("topic_id=nope", 400),
        ("topic_id=-1", 400),
        ("topic_ids=1,nope", 400),
        ("mode=invalid", 400),
        ("topic_id=2", 404),
    ],
)
def test_practice_rejects_bad_filters(admin, user_factory, login_user, query, status):
    client, headers = admin
    user_factory(client, headers, username="alumno", topic_ids=[1])
    user, _ = login_user(client.app, "alumno")
    assert user.get(f"/api/practice/question?{query}").status_code == status


def test_answer_is_idempotent_and_key_cannot_be_reused_for_other_question(
    admin, app_env: Path, user_factory, question_factory, login_user
):
    client, headers = admin
    q1, correct1, wrong1 = question_factory(client, headers, text="Q1")
    q2, correct2, _ = question_factory(client, headers, text="Q2")
    uid = user_factory(client, headers, username="alumno")
    user, user_headers = login_user(client.app, "alumno")
    key = uuid.uuid4().hex

    first = response_data(user.post("/api/answers", headers=user_headers, json={
        "question_id": q1, "selected_option_id": correct1, "submission_key": key,
    }))
    retry = response_data(user.post("/api/answers", headers=user_headers, json={
        "question_id": q1, "selected_option_id": wrong1, "submission_key": key,
    }))
    conflict = user.post("/api/answers", headers=user_headers, json={
        "question_id": q2, "selected_option_id": correct2, "submission_key": key,
    })
    assert first["correct"] is True and retry["correct"] is True
    assert conflict.status_code == 409

    with sqlite3.connect(app_env) as db:
        assert db.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?", (uid,)).fetchone()[0] == 1


def test_answer_rejects_option_from_another_question(admin, user_factory, question_factory, login_user):
    client, headers = admin
    q1, _, _ = question_factory(client, headers, text="Q1")
    _, option2, _ = question_factory(client, headers, text="Q2")
    user_factory(client, headers, username="alumno")
    user, user_headers = login_user(client.app, "alumno")
    response = user.post("/api/answers", headers=user_headers, json={
        "question_id": q1, "selected_option_id": option2, "submission_key": uuid.uuid4().hex,
    })
    assert response.status_code == 409


def test_simulation_finish_is_idempotent(admin, app_env: Path, user_factory, question_factory, login_user):
    client, headers = admin
    qid, _, wrong_id = question_factory(client, headers)
    uid = user_factory(client, headers, username="alumno")
    user, user_headers = login_user(client.app, "alumno")

    simulation = response_data(user.post("/api/simulations", headers=user_headers, json={"question_count": 1, "topic_ids": [1]}))
    with sqlite3.connect(app_env) as db:
        assert db.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?", (uid,)).fetchone()[0] == 0

    payload = {"submission_id": simulation["submission_id"], "answers": [{"question_id": qid, "selected_option_id": wrong_id}]}
    first = response_data(user.post("/api/simulations/finish", headers=user_headers, json=payload))
    retry = response_data(user.post("/api/simulations/finish", headers=user_headers, json=payload))
    assert first["incorrect"] == 1 and retry == first
    with sqlite3.connect(app_env) as db:
        assert db.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ? AND source = 'simulation'", (uid,)).fetchone()[0] == 1


@pytest.mark.parametrize(
    "payload,status",
    [
        ({"question_count": 0, "topic_ids": [1]}, 400),
        ({"question_count": 1001, "topic_ids": [1]}, 400),
        ({"question_count": "x", "topic_ids": [1]}, 400),
        ({"question_count": 1, "topic_ids": "1"}, 400),
        ({"question_count": 1, "topic_ids": [2]}, 404),
    ],
)
def test_simulation_rejects_invalid_configuration(admin, user_factory, login_user, payload, status):
    client, headers = admin
    user_factory(client, headers, username="alumno", topic_ids=[1])
    user, user_headers = login_user(client.app, "alumno")
    assert user.post("/api/simulations", headers=user_headers, json=payload).status_code == status
