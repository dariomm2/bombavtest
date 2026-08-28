from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from fastapi.testclient import TestClient


def data(response):
    assert response.status_code < 400, response.text
    return response.json()["data"]


def create_question(client: TestClient, headers: dict[str, str]) -> tuple[int, int, int]:
    created = data(
        client.post(
            "/api/admin/questions",
            headers=headers,
            json={
                "topic_id": 1,
                "text": "[TEST] Pregunta",
                "explanation": "Explicación",
                "options": [{"text": "Correcta"}, {"text": "Incorrecta"}],
            },
        )
    )
    qid = created["id"]
    questions = data(client.get("/api/admin/questions"))
    question = next(item for item in questions if item["id"] == qid)
    return qid, question["options"][0]["id"], question["options"][1]["id"]


def create_user(client: TestClient, headers: dict[str, str]) -> int:
    return data(
        client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "alumno",
                "display_name": "Alumno",
                "role": "user",
                "topic_ids": [1],
                "password": "Clave123",
            },
        )
    )["id"]


def test_health_frontend_and_auth(client: TestClient):
    assert client.get("/health").json() == {"ok": True, "status": "healthy", "version": "dev", "revision": "unknown"}
    assert 'window.BOMBAVTEST_VERSION = "dev";' in client.get("/version.js").text
    assert client.get("/").status_code == 200
    assert client.get("/styles.css").status_code == 200
    assert client.get("/script.js").status_code == 200
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/api/me").status_code == 401

    login = client.post("/api/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert client.get("/api/me").status_code == 200


def test_csrf_and_admin_permissions(admin, app_env: Path):
    client, headers = admin
    assert client.post("/api/admin/topics", json={}).status_code == 403
    uid = create_user(client, headers)

    user = TestClient(client.app)
    login = user.post("/api/login", json={"username": "alumno", "password": "Clave123"})
    assert login.status_code == 200
    assert user.get("/api/admin/users").status_code == 403

    db = sqlite3.connect(app_env)
    try:
        assert db.execute("SELECT COUNT(*) FROM users WHERE id = ?", (uid,)).fetchone()[0] == 1
    finally:
        db.close()


def test_practice_simulation_history_and_session_revocation(admin, app_env: Path):
    client, headers = admin
    qid, correct_id, wrong_id = create_question(client, headers)
    uid = create_user(client, headers)

    user = TestClient(client.app)
    login = user.post("/api/login", json={"username": "alumno", "password": "Clave123"})
    user_headers = {"X-CSRF-Token": login.json()["data"]["csrf_token"]}

    question = data(user.get("/api/practice/question?topic_id=1&mode=all"))
    assert question["id"] == qid
    assert question["correct_option_id"] == correct_id

    submission_key = "appearance_" + uuid.uuid4().hex
    first = data(
        user.post(
            "/api/answers",
            headers=user_headers,
            json={
                "question_id": qid,
                "selected_option_id": correct_id,
                "submission_key": submission_key,
            },
        )
    )
    assert first["correct"] is True
    retry = data(
        user.post(
            "/api/answers",
            headers=user_headers,
            json={
                "question_id": qid,
                "selected_option_id": wrong_id,
                "submission_key": submission_key,
            },
        )
    )
    assert retry["correct"] is True

    db = sqlite3.connect(app_env)
    try:
        assert db.execute(
            "SELECT COUNT(*) FROM attempts WHERE user_id = ? AND source = 'practice'",
            (uid,),
        ).fetchone()[0] == 1
    finally:
        db.close()

    simulation = data(
        user.post(
            "/api/simulations",
            headers=user_headers,
            json={"question_count": 1, "topic_ids": [1]},
        )
    )
    db = sqlite3.connect(app_env)
    try:
        assert db.execute(
            "SELECT COUNT(*) FROM attempts WHERE user_id = ? AND source = 'simulation'",
            (uid,),
        ).fetchone()[0] == 0
    finally:
        db.close()

    finish_payload = {
        "submission_id": simulation["submission_id"],
        "answers": [{"question_id": qid, "selected_option_id": wrong_id}],
    }
    assert data(user.post("/api/simulations/finish", headers=user_headers, json=finish_payload))["incorrect"] == 1
    assert data(user.post("/api/simulations/finish", headers=user_headers, json=finish_payload))["incorrect"] == 1

    db = sqlite3.connect(app_env)
    try:
        old_outcomes = db.execute(
            "SELECT outcome FROM attempts WHERE user_id = ? ORDER BY id", (uid,)
        ).fetchall()
        assert db.execute(
            "SELECT COUNT(*) FROM attempts WHERE user_id = ? AND source = 'simulation'",
            (uid,),
        ).fetchone()[0] == 1
    finally:
        db.close()

    edit_payload = {
        "topic_id": 1,
        "text": "[TEST] Pregunta editada",
        "explanation": "Nueva explicación",
        "options": [
            {"id": wrong_id, "text": "Ahora correcta"},
            {"id": correct_id, "text": "Ahora incorrecta"},
        ],
    }
    assert client.put(f"/api/admin/questions/{qid}", headers=headers, json=edit_payload).status_code == 200
    db = sqlite3.connect(app_env)
    try:
        assert db.execute(
            "SELECT outcome FROM attempts WHERE user_id = ? ORDER BY id", (uid,)
        ).fetchall() == old_outcomes
    finally:
        db.close()

    assert client.put(
        f"/api/admin/users/{uid}",
        headers=headers,
        json={
            "username": "alumno",
            "display_name": "Alumno",
            "role": "user",
            "topic_ids": [1],
            "password": "Nueva123",
        },
    ).status_code == 200
    assert user.get("/api/me").status_code == 401

    assert client.delete(f"/api/admin/questions/{qid}", headers=headers).status_code == 200
    db = sqlite3.connect(app_env)
    try:
        assert db.execute("SELECT COUNT(*) FROM options WHERE question_id = ?", (qid,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM attempts WHERE question_id = ?", (qid,)).fetchone()[0] == 0
    finally:
        db.close()


def test_user_deactivate_preserves_data_and_delete_removes_it(admin, app_env: Path):
    client, headers = admin
    qid, correct_id, _ = create_question(client, headers)
    uid = create_user(client, headers)
    user = TestClient(client.app)
    login = user.post("/api/login", json={"username": "alumno", "password": "Clave123"})
    user_headers = {"X-CSRF-Token": login.json()["data"]["csrf_token"]}
    data(
        user.post(
            "/api/answers",
            headers=user_headers,
            json={
                "question_id": qid,
                "selected_option_id": correct_id,
                "submission_key": "appearance_" + uuid.uuid4().hex,
            },
        )
    )

    assert client.post(f"/api/admin/users/{uid}/deactivate", headers=headers, json={}).status_code == 200
    db = sqlite3.connect(app_env)
    try:
        assert db.execute("SELECT is_active FROM users WHERE id = ?", (uid,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?", (uid,)).fetchone()[0] == 1
    finally:
        db.close()

    assert client.delete(f"/api/admin/users/{uid}", headers=headers).status_code == 200
    db = sqlite3.connect(app_env)
    try:
        assert db.execute("SELECT COUNT(*) FROM users WHERE id = ?", (uid,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?", (uid,)).fetchone()[0] == 0
    finally:
        db.close()


def test_secure_cookie_when_request_is_https(client: TestClient):
    response = client.post(
        "/api/login",
        headers={"X-Forwarded-Proto": "https"},
        json={"username": "admin", "password": "admin"},
    )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_login_rate_limit(client: TestClient):
    for _ in range(10):
        response = client.post(
            "/api/login", json={"username": "no-existe", "password": "incorrecta"}
        )
        assert response.status_code == 401
    limited = client.post(
        "/api/login", json={"username": "no-existe", "password": "incorrecta"}
    )
    assert limited.status_code == 429
    assert limited.json()["code"] == "RATE_LIMIT"


def test_topic_delete_cascades_questions_and_history(admin, app_env: Path):
    client, headers = admin
    qid, correct_id, _ = create_question(client, headers)
    uid = create_user(client, headers)
    user = TestClient(client.app)
    login = user.post("/api/login", json={"username": "alumno", "password": "Clave123"})
    user_headers = {"X-CSRF-Token": login.json()["data"]["csrf_token"]}
    data(
        user.post(
            "/api/answers",
            headers=user_headers,
            json={
                "question_id": qid,
                "selected_option_id": correct_id,
                "submission_key": "appearance_" + uuid.uuid4().hex,
            },
        )
    )

    response = client.delete("/api/admin/topics/1", headers=headers)
    assert response.status_code == 200, response.text

    db = sqlite3.connect(app_env)
    try:
        assert db.execute("SELECT COUNT(*) FROM topics WHERE id = 1").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM questions WHERE id = ?", (qid,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM attempts WHERE question_id = ?", (qid,)).fetchone()[0] == 0
        assert db.execute(
            "SELECT COUNT(*) FROM user_topics WHERE user_id = ? AND topic_id = 1", (uid,)
        ).fetchone()[0] == 0
    finally:
        db.close()
