from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from backend import auth, statistics
from tests.conftest import response_data


def test_madrid_day_bounds_handle_dst_days():
    spring_start, spring_end = auth.madrid_day_bounds(date(2026, 3, 29))
    autumn_start, autumn_end = auth.madrid_day_bounds(date(2026, 10, 25))
    spring_hours = (datetime.fromisoformat(spring_end) - datetime.fromisoformat(spring_start)).total_seconds() / 3600
    autumn_hours = (datetime.fromisoformat(autumn_end) - datetime.fromisoformat(autumn_start)).total_seconds() / 3600
    assert spring_hours == 23
    assert autumn_hours == 25


def test_moving_accuracy_uses_sliding_window():
    rows = [
        {"outcome": "correct" if i < 3 else "incorrect", "created_at": f"2026-08-{i + 1:02d}T12:00:00+00:00"}
        for i in range(5)
    ]
    assert statistics.moving_accuracy(rows, window=3) == [
        {"label": "3 ago", "value": 100.0},
        {"label": "4 ago", "value": 66.7},
        {"label": "5 ago", "value": 33.3},
    ]


def test_statistics_self_kpis_are_exact(admin, user_factory, question_factory, login_user):
    client, headers = admin
    q1, correct1, _ = question_factory(client, headers, text="Q1")
    q2, _, wrong2 = question_factory(client, headers, text="Q2")
    user_factory(client, headers, username="alumno")
    user, user_headers = login_user(client.app, "alumno")
    response_data(user.post("/api/answers", headers=user_headers, json={
        "question_id": q1, "selected_option_id": correct1, "submission_key": uuid.uuid4().hex,
    }))
    response_data(user.post("/api/answers", headers=user_headers, json={
        "question_id": q2, "selected_option_id": wrong2, "submission_key": uuid.uuid4().hex,
    }))

    stats = response_data(user.get("/api/statistics"))
    assert stats["subject"]["scope"] == "self"
    assert stats["kpis"]["total_answered"] == 2
    assert stats["kpis"]["correct_attempts"] == 1
    assert stats["kpis"]["accuracy"] == 50.0
    topic = next(item for item in stats["bar"] if item["id"] == 1)
    assert topic["answered"] == 2 and topic["correct_attempts"] == 1 and topic["accuracy"] == 50.0


def test_statistics_permissions_and_admin_scopes(admin, user_factory):
    client, headers = admin
    uid = user_factory(client, headers, username="alumno")
    user = client.__class__(client.app)
    login = user.post("/api/login", json={"username": "alumno", "password": "Clave123"})
    assert login.status_code == 200
    assert user.get("/api/statistics?scope=all").status_code == 403
    assert user.get(f"/api/statistics?scope=student&user_id={uid}").status_code == 403

    student = response_data(client.get(f"/api/statistics?scope=student&user_id={uid}"))
    assert student["subject"]["scope"] == "student" and student["subject"]["user_id"] == uid
    all_stats = response_data(client.get("/api/statistics?scope=all"))
    assert all_stats["subject"]["scope"] == "all"
    assert all_stats["cohort"]["total_students"] == 1
    assert all_stats["winrate_window"] == 120
    assert client.get("/api/statistics?scope=student&user_id=999999").status_code == 404
    assert client.get("/api/statistics?scope=invalid").status_code == 400


def test_revoked_topic_disappears_from_student_statistics(admin, app_env: Path, user_factory, question_factory, login_user):
    client, headers = admin
    topic2 = response_data(client.post("/api/admin/topics", headers=headers, json={
        "number": "99", "name": "Segundo", "color": "#123456", "attachment_draft_ids": [],
    }))["id"]
    q1, correct1, _ = question_factory(client, headers, topic_id=1, text="Q1")
    q2, correct2, _ = question_factory(client, headers, topic_id=topic2, text="Q2")
    uid = user_factory(client, headers, username="alumno", topic_ids=[1, topic2])
    user, user_headers = login_user(client.app, "alumno")
    for qid, option_id in [(q1, correct1), (q2, correct2)]:
        response_data(user.post("/api/answers", headers=user_headers, json={
            "question_id": qid, "selected_option_id": option_id, "submission_key": uuid.uuid4().hex,
        }))
    assert response_data(user.get("/api/statistics"))["kpis"]["total_answered"] == 2

    assert client.put(f"/api/admin/users/{uid}", headers=headers, json={
        "username": "alumno", "display_name": "Alumno", "role": "user", "topic_ids": [1], "password": "",
    }).status_code == 200
    stats = response_data(user.get("/api/statistics"))
    assert stats["kpis"]["total_answered"] == 1
    assert [topic["id"] for topic in stats["topics"]] == [1]
    with sqlite3.connect(app_env) as db:
        assert db.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?", (uid,)).fetchone()[0] == 2


def test_statistics_streak_uses_calendar_days(admin, app_env: Path, user_factory, question_factory, login_user, monkeypatch):
    client, headers = admin
    qid, _, _ = question_factory(client, headers)
    uid = user_factory(client, headers, username="alumno")
    monkeypatch.setattr(statistics, "madrid_today", lambda: date(2026, 8, 29))

    with sqlite3.connect(app_env) as db:
        for offset in [2, 1, 0]:
            day = date(2026, 8, 29) - timedelta(days=offset)
            created = datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc).isoformat()
            db.execute(
                "INSERT INTO attempts(user_id, question_id, outcome, source, submission_key, created_at) VALUES (?, ?, 'correct', 'practice', ?, ?)",
                (uid, qid, f"manual:{offset}", created),
            )
        db.commit()

    user, _ = login_user(client.app, "alumno")
    stats = response_data(user.get("/api/statistics"))
    assert stats["kpis"]["current_streak"] == 3
    assert stats["kpis"]["best_streak"] == 3
