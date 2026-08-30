from __future__ import annotations

from backend.config import (
    MAX_ATTACHMENTS_PER_UPLOAD,
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


def test_attachment_batch_limit_is_enforced_before_storage(admin):
    client, headers = admin
    files = [
        ("files", (f"file-{index}.txt", b"x", "text/plain"))
        for index in range(MAX_ATTACHMENTS_PER_UPLOAD + 1)
    ]
    response = client.post("/api/admin/topics/1/attachments", headers=headers, files=files)
    assert response.status_code == 400
    assert str(MAX_ATTACHMENTS_PER_UPLOAD) in response.json()["error"]
