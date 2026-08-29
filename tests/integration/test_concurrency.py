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


def test_concurrent_duplicate_submission_is_still_idempotent(
    admin, app_env: Path, user_factory, question_factory
):
    admin_client, headers = admin
    question_id, correct_option_id, _ = question_factory(admin_client, headers)
    user_id = user_factory(admin_client, headers, username="same-submission")
    submission_key = "concurrent-submission-123"

    clients: list[TestClient] = []
    request_headers: list[dict[str, str]] = []
    for _ in range(2):
        client = TestClient(admin_client.app)
        clients.append(client)
        login = client.post(
            "/api/login",
            json={"username": "same-submission", "password": "Clave123"},
        )
        assert login.status_code == 200
        request_headers.append({"X-CSRF-Token": login.json()["data"]["csrf_token"]})

    payload = {
        "question_id": question_id,
        "selected_option_id": correct_option_id,
        "submission_key": submission_key,
    }
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(client.post, "/api/answers", headers=headers, json=payload)
                for client, headers in zip(clients, request_headers, strict=True)
            ]
            responses = [future.result() for future in futures]
    finally:
        for client in clients:
            client.close()

    assert [response.status_code for response in responses] == [200, 200]
    assert all(response.json()["data"]["correct"] is True for response in responses)
    with sqlite3.connect(app_env) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM attempts WHERE user_id = ? AND question_id = ?",
            (user_id, question_id),
        ).fetchone()[0] == 1


def test_concurrent_admin_deactivation_never_removes_every_active_admin(
    admin, app_env: Path
):
    import threading

    admin_one, headers_one = admin
    created = admin_one.post(
        "/api/admin/users",
        headers=headers_one,
        json={
            "username": "second.admin",
            "display_name": "Second Admin",
            "role": "admin",
            "topic_ids": [],
            "password": "Clave123",
        },
    )
    assert created.status_code == 201
    admin_two_id = created.json()["data"]["id"]
    admin_one_id = admin_one.get("/api/me").json()["data"]["user"]["id"]

    admin_two = TestClient(admin_one.app)
    login = admin_two.post(
        "/api/login",
        json={"username": "second.admin", "password": "Clave123"},
    )
    assert login.status_code == 200
    headers_two = {"X-CSRF-Token": login.json()["data"]["csrf_token"]}
    barrier = threading.Barrier(2)

    def deactivate(client: TestClient, target_id: int, headers: dict[str, str]):
        barrier.wait(timeout=5)
        return client.post(
            f"/api/admin/users/{target_id}/deactivate",
            headers=headers,
            json={},
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(deactivate, admin_one, admin_two_id, headers_one)
            second = pool.submit(deactivate, admin_two, admin_one_id, headers_two)
            responses = [first.result(), second.result()]
    finally:
        admin_two.close()

    statuses = sorted(response.status_code for response in responses)
    assert statuses[0] == 200
    assert statuses[1] in {401, 409}
    with sqlite3.connect(app_env) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
        ).fetchone()[0] == 1
