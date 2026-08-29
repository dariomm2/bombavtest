from __future__ import annotations

import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient


def test_concurrent_practice_writes_do_not_lock_database(admin, app_env: Path, user_factory, question_factory):
    admin_client, headers = admin
    question_id, correct_option_id, _ = question_factory(admin_client, headers, text="Concurrent question")
    usernames = [f"parallel{i}" for i in range(6)]
    for username in usernames:
        user_factory(admin_client, headers, username=username)

    def answer(username: str) -> int:
        with TestClient(admin_client.app) as client:
            login = client.post("/api/login", json={"username": username, "password": "Clave123"})
            assert login.status_code == 200, login.text
            csrf = login.json()["data"]["csrf_token"]
            response = client.post(
                "/api/answers",
                headers={"X-CSRF-Token": csrf},
                json={
                    "question_id": question_id,
                    "selected_option_id": correct_option_id,
                    "submission_key": uuid.uuid4().hex,
                },
            )
            return response.status_code

    with ThreadPoolExecutor(max_workers=len(usernames)) as pool:
        statuses = list(pool.map(answer, usernames))

    assert statuses == [200] * len(usernames)
    with sqlite3.connect(app_env) as db:
        assert db.execute("SELECT COUNT(*) FROM attempts WHERE question_id = ?", (question_id,)).fetchone()[0] == len(usernames)
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
