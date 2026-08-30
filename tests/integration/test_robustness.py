from __future__ import annotations

import sqlite3

from backend.config import (
    MAX_ATTACHMENTS_PER_TOPIC,
    MAX_JSON_BYTES,
    MAX_UPLOAD_REQUEST_BYTES,
)


def test_login_rejects_malformed_and_non_object_json(client):
    malformed = client.post(
        "/api/login",
        content=b'{"username":',
        headers={"Content-Type": "application/json"},
    )
    assert malformed.status_code == 400

    non_object = client.post("/api/login", json=["admin", "admin"])
    assert non_object.status_code == 400


def test_oversized_json_is_rejected_before_application_processing(client):
    body = b'{"username":"' + (b"a" * (MAX_JSON_BYTES + 1)) + b'","password":"x"}'
    response = client.post(
        "/api/login",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["ok"] is False


def test_oversized_multipart_request_is_rejected_by_middleware(admin):
    client, headers = admin

    response = client.post(
        "/api/admin/topic-attachment-drafts",
        content=b"--test--\r\n",
        headers={
            **headers,
            "Content-Type": "multipart/form-data; boundary=test",
            "Content-Length": str(MAX_UPLOAD_REQUEST_BYTES + 1),
        },
    )
    assert response.status_code == 413
    assert response.json()["ok"] is False


def test_attachment_count_limit_is_enforced_before_storage(admin):
    client, headers = admin
    files = [
        ("files", (f"file-{index}.txt", b"x", "text/plain"))
        for index in range(MAX_ATTACHMENTS_PER_TOPIC + 1)
    ]
    response = client.post("/api/admin/topics/1/attachments", headers=headers, files=files)
    assert response.status_code == 400
    assert str(MAX_ATTACHMENTS_PER_TOPIC) in response.json()["error"]


def test_attachment_total_size_limit_is_enforced_before_storage(admin, monkeypatch):
    from backend import admin as admin_module

    client, headers = admin
    monkeypatch.setattr(admin_module, "MAX_TOPIC_ATTACHMENTS_BYTES", 3)
    files = [
        ("files", ("one.txt", b"xx", "text/plain")),
        ("files", ("two.txt", b"xx", "text/plain")),
    ]
    response = client.post("/api/admin/topics/1/attachments", headers=headers, files=files)
    assert response.status_code == 400
    assert "200 MB" in response.json()["error"]


def test_attachment_draft_total_limit_is_enforced_when_saving_topic(admin, app_env, monkeypatch):
    from backend import admin as admin_module

    client, headers = admin
    monkeypatch.setattr(admin_module, "MAX_TOPIC_ATTACHMENTS_BYTES", 3)
    with sqlite3.connect(app_env) as db:
        admin_id = db.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
        draft_ids = []
        for index in range(2):
            cursor = db.execute(
                """
                INSERT INTO topic_attachment_drafts(
                    created_by, original_name, storage_key, mime_type, size_bytes, created_at
                ) VALUES (?, ?, ?, 'text/plain', 2, '2026-01-01T00:00:00+00:00')
                """,
                (admin_id, f"draft-{index}.txt", f"draft-{index}"),
            )
            draft_ids.append(cursor.lastrowid)
        db.commit()

    response = client.post(
        "/api/admin/topics",
        headers=headers,
        json={
            "number": "LIMIT",
            "name": "Limit test",
            "color": "#123456",
            "attachment_draft_ids": draft_ids,
        },
    )
    assert response.status_code == 409
    assert "200 MB" in response.json()["error"]
