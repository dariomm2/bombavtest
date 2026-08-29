from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from tests.conftest import response_data


def test_topic_crud_and_validation(admin):
    client, headers = admin
    created = client.post("/api/admin/topics", headers=headers, json={
        "number": "99.1", "name": "Tema de prueba", "color": "#ABCDEF", "attachment_draft_ids": [],
    })
    assert created.status_code == 201
    topic_id = created.json()["data"]["id"]
    topic = next(item for item in response_data(client.get("/api/admin/topics")) if item["id"] == topic_id)
    assert topic["number"] == "99.1" and topic["color"] == "#abcdef"

    assert client.put(f"/api/admin/topics/{topic_id}", headers=headers, json={
        "number": "99.2", "name": "Editado", "color": "#123456", "attachment_draft_ids": [],
    }).status_code == 200
    assert client.delete(f"/api/admin/topics/{topic_id}", headers=headers).status_code == 200
    assert client.put(f"/api/admin/topics/{topic_id}", headers=headers, json={
        "number": "99", "name": "X", "color": "#123456", "attachment_draft_ids": [],
    }).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"number": "", "name": "Tema", "color": "#123456"},
        {"number": "99", "name": "", "color": "#123456"},
        {"number": "99", "name": "Tema", "color": "red"},
        {"number": "x" * 33, "name": "Tema", "color": "#123456"},
    ],
)
def test_topic_validation(admin, payload):
    client, headers = admin
    assert client.post("/api/admin/topics", headers=headers, json=payload).status_code == 400


def test_topic_number_is_unique_case_insensitive(admin):
    client, headers = admin
    payload = {"number": "TEST-A", "name": "Tema", "color": "#123456", "attachment_draft_ids": []}
    assert client.post("/api/admin/topics", headers=headers, json=payload).status_code == 201
    payload["number"] = "test-a"
    assert client.post("/api/admin/topics", headers=headers, json=payload).status_code == 409


def test_question_crud_first_option_is_correct(admin, question_factory):
    client, headers = admin
    qid, correct_id, wrong_id = question_factory(client, headers)
    question = next(item for item in response_data(client.get("/api/admin/questions")) if item["id"] == qid)
    assert [option["is_correct"] for option in question["options"]] == [True, False]

    update = client.put(f"/api/admin/questions/{qid}", headers=headers, json={
        "topic_id": 1,
        "text": "Editada",
        "explanation": "Nueva",
        "options": [{"id": wrong_id, "text": "Ahora correcta"}, {"id": correct_id, "text": "Ahora incorrecta"}],
    })
    assert update.status_code == 200
    question = next(item for item in response_data(client.get("/api/admin/questions")) if item["id"] == qid)
    correct = next(option for option in question["options"] if option["is_correct"])
    assert correct["id"] == wrong_id
    assert client.delete(f"/api/admin/questions/{qid}", headers=headers).status_code == 200
    assert client.delete(f"/api/admin/questions/{qid}", headers=headers).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"topic_id": 999, "text": "P", "options": [{"text": "A"}, {"text": "B"}]},
        {"topic_id": 1, "text": "", "options": [{"text": "A"}, {"text": "B"}]},
        {"topic_id": 1, "text": "P", "options": [{"text": "A"}]},
        {"topic_id": 1, "text": "P", "options": [{"text": str(i)} for i in range(11)]},
        {"topic_id": 1, "text": "P", "explanation": "x" * 4001, "options": [{"text": "A"}, {"text": "B"}]},
        {"topic_id": 1, "text": "P", "options": [{"text": ""}, {"text": "B"}]},
    ],
)
def test_question_validation(admin, payload):
    client, headers = admin
    assert client.post("/api/admin/questions", headers=headers, json=payload).status_code == 400


def test_question_edit_preserves_historical_outcome(admin, app_env: Path, user_factory, question_factory, login_user):
    client, headers = admin
    qid, correct_id, wrong_id = question_factory(client, headers)
    uid = user_factory(client, headers, username="alumno")
    user, user_headers = login_user(client.app, "alumno")
    response_data(user.post("/api/answers", headers=user_headers, json={
        "question_id": qid, "selected_option_id": correct_id, "submission_key": uuid.uuid4().hex,
    }))

    with sqlite3.connect(app_env) as db:
        before = db.execute("SELECT outcome FROM attempts WHERE user_id = ?", (uid,)).fetchall()

    assert client.put(f"/api/admin/questions/{qid}", headers=headers, json={
        "topic_id": 1,
        "text": "Editada",
        "explanation": "Nueva",
        "options": [{"id": wrong_id, "text": "Correcta nueva"}, {"id": correct_id, "text": "Incorrecta nueva"}],
    }).status_code == 200

    with sqlite3.connect(app_env) as db:
        assert db.execute("SELECT outcome FROM attempts WHERE user_id = ?", (uid,)).fetchall() == before


def test_question_delete_cascades_options_and_attempts(admin, app_env: Path, user_factory, question_factory, login_user):
    client, headers = admin
    qid, correct_id, _ = question_factory(client, headers)
    uid = user_factory(client, headers, username="alumno")
    user, user_headers = login_user(client.app, "alumno")
    response_data(user.post("/api/answers", headers=user_headers, json={
        "question_id": qid, "selected_option_id": correct_id, "submission_key": uuid.uuid4().hex,
    }))
    assert client.delete(f"/api/admin/questions/{qid}", headers=headers).status_code == 200
    with sqlite3.connect(app_env) as db:
        assert db.execute("SELECT COUNT(*) FROM options WHERE question_id = ?", (qid,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?", (uid,)).fetchone()[0] == 0


def test_user_create_list_update_and_session_revocation(admin, user_factory, login_user):
    client, headers = admin
    uid = user_factory(client, headers, username="alumno", display_name="Álvaro Pérez")
    users = response_data(client.get("/api/admin/users"))
    assert next(item for item in users if item["id"] == uid)["topic_ids"] == [1]

    user, _ = login_user(client.app, "alumno")
    update = client.put(f"/api/admin/users/{uid}", headers=headers, json={
        "username": "alumno", "display_name": "Alumno Editado", "role": "user", "topic_ids": [1], "password": "Nueva123",
    })
    assert update.status_code == 200
    assert user.get("/api/me").status_code == 401
    assert client.post("/api/login", json={"username": "alumno", "password": "Clave123"}).status_code == 401
    assert client.post("/api/login", json={"username": "alumno", "password": "Nueva123"}).status_code == 200


def test_username_suggestion_and_availability(admin, user_factory):
    client, headers = admin
    suggestion = response_data(client.get("/api/admin/users/username-suggestion?display_name=Álvaro%20Pérez"))["username"]
    assert suggestion.startswith("alvaro.perez")
    user_factory(client, headers, username=suggestion)
    assert response_data(client.get(f"/api/admin/users/username-check?username={suggestion}"))["available"] is False
    next_suggestion = response_data(client.get("/api/admin/users/username-suggestion?display_name=Álvaro%20Pérez"))["username"]
    assert next_suggestion != suggestion


@pytest.mark.parametrize(
    "password",
    ["Corta1", "sinmayuscula1", "SINNUMERO", "A" + "1" * 256],
)
def test_user_password_validation(admin, password):
    client, headers = admin
    response = client.post("/api/admin/users", headers=headers, json={
        "username": "alumno", "display_name": "Alumno", "role": "user", "topic_ids": [1], "password": password,
    })
    assert response.status_code == 400


def test_user_deactivate_activate_and_delete_preserve_then_remove_data(
    admin, app_env: Path, user_factory, question_factory, login_user
):
    client, headers = admin
    qid, correct_id, _ = question_factory(client, headers)
    uid = user_factory(client, headers, username="alumno")
    user, user_headers = login_user(client.app, "alumno")
    response_data(user.post("/api/answers", headers=user_headers, json={
        "question_id": qid, "selected_option_id": correct_id, "submission_key": uuid.uuid4().hex,
    }))

    assert client.post(f"/api/admin/users/{uid}/deactivate", headers=headers, json={}).status_code == 200
    assert user.get("/api/me").status_code == 401
    with sqlite3.connect(app_env) as db:
        assert db.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?", (uid,)).fetchone()[0] == 1

    assert client.post(f"/api/admin/users/{uid}/activate", headers=headers, json={}).status_code == 200
    assert client.delete(f"/api/admin/users/{uid}", headers=headers).status_code == 200
    with sqlite3.connect(app_env) as db:
        assert db.execute("SELECT COUNT(*) FROM users WHERE id = ?", (uid,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?", (uid,)).fetchone()[0] == 0


def test_admin_cannot_remove_or_demote_last_active_admin(admin):
    client, headers = admin
    me = response_data(client.get("/api/me"))["user"]["id"]
    assert client.post(f"/api/admin/users/{me}/deactivate", headers=headers, json={}).status_code == 409
    assert client.delete(f"/api/admin/users/{me}", headers=headers).status_code == 409
    response = client.put(f"/api/admin/users/{me}", headers=headers, json={
        "username": "admin", "display_name": "Admin", "role": "user", "topic_ids": [1], "password": "",
    })
    assert response.status_code == 409


def test_topic_delete_cascades_questions_user_assignments_and_history(
    admin, app_env: Path, user_factory, question_factory, login_user
):
    client, headers = admin
    qid, correct_id, _ = question_factory(client, headers)
    uid = user_factory(client, headers, username="alumno")
    user, user_headers = login_user(client.app, "alumno")
    response_data(user.post("/api/answers", headers=user_headers, json={
        "question_id": qid, "selected_option_id": correct_id, "submission_key": uuid.uuid4().hex,
    }))
    assert client.delete("/api/admin/topics/1", headers=headers).status_code == 200
    with sqlite3.connect(app_env) as db:
        assert db.execute("SELECT COUNT(*) FROM topics WHERE id = 1").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM questions WHERE id = ?", (qid,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?", (uid,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM user_topics WHERE user_id = ?", (uid,)).fetchone()[0] == 0
