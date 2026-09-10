from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from backend import practice, simulations
from tests.conftest import response_data


def create_question_bank(client, headers, question_factory, count: int = 10):
    return [
        question_factory(client, headers, text=f"Pregunta diaria {index}")
        for index in range(1, count + 1)
    ]


def test_daily_test_completion_updates_home_and_cannot_be_repeated(
    admin, app_env: Path, user_factory, question_factory, login_user
):
    client, headers = admin
    questions = create_question_bank(client, headers, question_factory)
    uid = user_factory(client, headers, username="alumno")
    user, user_headers = login_user(client.app, "alumno")

    initial = response_data(user.get("/api/home"))["daily_test"]
    assert initial == {"status": "inactive", "streak": 0, "available": True}

    started = user.post("/api/daily-test", headers=user_headers)
    assert started.status_code == 201
    daily_test = response_data(started)
    restarted = response_data(user.post("/api/daily-test", headers=user_headers))
    assert restarted["submission_id"] != daily_test["submission_id"]

    with sqlite3.connect(app_env) as db:
        assert db.execute("SELECT COUNT(*) FROM daily_tests WHERE user_id = ?", (uid,)).fetchone()[0] == 0

    correct_by_question = {question_id: correct_id for question_id, correct_id, _ in questions}
    answers = [
        {"question_id": item["id"], "selected_option_id": correct_by_question[item["id"]]}
        for item in daily_test["questions"]
    ]
    payload = {"submission_id": daily_test["submission_id"], "daily_test": True, "answers": answers}
    result = response_data(user.post("/api/simulations/finish", headers=user_headers, json=payload))
    retry = response_data(user.post("/api/simulations/finish", headers=user_headers, json=payload))

    assert result["daily_test"] is True
    assert result["correct"] == result["total"] == 10
    assert retry == result
    assert response_data(user.get("/api/home"))["daily_test"] == {
        "status": "completed", "streak": 1, "available": True,
    }
    repeated = user.post("/api/daily-test", headers=user_headers)
    assert repeated.status_code == 409
    assert repeated.json()["code"] == "DAILY_TEST_COMPLETED"

    with sqlite3.connect(app_env) as db:
        daily_row = db.execute(
            "SELECT completed_on FROM daily_tests WHERE user_id = ?", (uid,)
        ).fetchone()
        assert daily_row and daily_row[0] == practice.madrid_today().isoformat()
        assert db.execute(
            "SELECT COUNT(*) FROM attempts WHERE user_id = ? AND source = 'simulation'", (uid,)
        ).fetchone()[0] == 10

    repeated_finish = user.post(
        "/api/simulations/finish",
        headers=user_headers,
        json={"submission_id": restarted["submission_id"], "daily_test": True, "answers": answers},
    )
    assert repeated_finish.status_code == 409
    assert repeated_finish.json()["code"] == "DAILY_TEST_COMPLETED"


def test_daily_test_requires_ten_questions(admin, user_factory, question_factory, login_user):
    client, headers = admin
    questions = create_question_bank(client, headers, question_factory, count=9)
    user_factory(client, headers, username="alumno")
    user, user_headers = login_user(client.app, "alumno")

    home = response_data(user.get("/api/home"))
    assert home["daily_test"]["available"] is False
    response = user.post("/api/daily-test", headers=user_headers)
    assert response.status_code == 409
    assert response.json()["code"] == "NOT_ENOUGH_QUESTIONS"

    short_finish = user.post(
        "/api/simulations/finish",
        headers=user_headers,
        json={
            "submission_id": "short-daily-test",
            "daily_test": True,
            "answers": [
                {"question_id": question_id, "selected_option_id": None}
                for question_id, _, _ in questions
            ],
        },
    )
    assert short_finish.status_code == 400


def test_daily_streak_states_use_madrid_calendar(
    admin, app_env: Path, user_factory, login_user, monkeypatch
):
    client, headers = admin
    uid = user_factory(client, headers, username="alumno")
    user, _ = login_user(client.app, "alumno")
    today = date(2026, 9, 10)
    monkeypatch.setattr(practice, "madrid_today", lambda: today)

    with sqlite3.connect(app_env) as db:
        db.executemany(
            "INSERT INTO daily_tests(user_id, completed_on) VALUES (?, ?)",
            [(uid, "2026-09-08"), (uid, "2026-09-09")],
        )
        db.commit()

    pending = response_data(user.get("/api/home"))["daily_test"]
    assert pending["status"] == "pending" and pending["streak"] == 2

    with sqlite3.connect(app_env) as db:
        db.execute(
            "INSERT INTO daily_tests(user_id, completed_on) VALUES (?, '2026-09-10')",
            (uid,),
        )
        db.commit()

    completed = response_data(user.get("/api/home"))["daily_test"]
    assert completed["status"] == "completed" and completed["streak"] == 3

    with sqlite3.connect(app_env) as db:
        db.execute("DELETE FROM daily_tests WHERE user_id = ? AND completed_on >= '2026-09-09'", (uid,))
        db.commit()

    assert response_data(user.get("/api/home"))["daily_test"]["status"] == "inactive"


def test_daily_test_uses_the_madrid_completion_date(
    admin, app_env: Path, user_factory, question_factory, login_user, monkeypatch
):
    client, headers = admin
    create_question_bank(client, headers, question_factory)
    user_factory(client, headers, username="alumno")
    user, user_headers = login_user(client.app, "alumno")
    monkeypatch.setattr(practice, "madrid_today", lambda: date(2026, 9, 9))
    daily_test = response_data(user.post("/api/daily-test", headers=user_headers))

    with sqlite3.connect(app_env) as db:
        assert db.execute("SELECT COUNT(*) FROM daily_tests").fetchone()[0] == 0

    monkeypatch.setattr(simulations, "madrid_today", lambda: date(2026, 9, 10))
    result = response_data(user.post(
        "/api/simulations/finish",
        headers=user_headers,
        json={
            "submission_id": daily_test["submission_id"],
            "daily_test": True,
            "answers": [
                {"question_id": item["id"], "selected_option_id": None}
                for item in daily_test["questions"]
            ],
        },
    ))
    assert result["daily_test"] is True

    with sqlite3.connect(app_env) as db:
        assert db.execute("SELECT completed_on FROM daily_tests").fetchone()[0] == "2026-09-10"

    monkeypatch.setattr(practice, "madrid_today", lambda: date(2026, 9, 10))
    assert response_data(user.get("/api/home"))["daily_test"]["status"] == "completed"
