from __future__ import annotations

from fastapi.responses import Response

from backend import admin as admin_module


def test_attachment_upload_uses_s3_compatible_backend(admin, monkeypatch):
    client, headers = admin
    stored: dict[str, bytes] = {}

    def fake_upload(upload, key: str, mime_type: str):
        upload.file.seek(0)
        stored[key] = upload.file.read()

    def fake_delete(key: str):
        stored.pop(key, None)

    def fake_download(key: str, filename: str, mime_type: str):
        return Response(stored[key], media_type=mime_type)

    monkeypatch.setattr(admin_module, "s3_upload_file", fake_upload)
    monkeypatch.setattr(admin_module, "s3_delete_file", fake_delete)
    monkeypatch.setattr(admin_module, "s3_download_response", fake_download)

    upload = client.post(
        "/api/admin/topics/1/attachments",
        headers=headers,
        files=[("files", ("manual.pdf", b"contenido", "application/pdf"))],
    )
    assert upload.status_code == 201, upload.text
    attachment = upload.json()["data"][0]
    assert len(stored) == 1

    download = client.get(attachment["download_url"])
    assert download.status_code == 200
    assert download.content == b"contenido"

    delete = client.delete(
        f"/api/admin/topics/1/attachments/{attachment['id']}", headers=headers
    )
    assert delete.status_code == 200
    assert stored == {}


def test_s3_client_is_provider_agnostic(monkeypatch):
    from backend import storage

    captured = {}

    def fake_client(service_name, **kwargs):
        captured["service_name"] = service_name
        captured.update(kwargs)
        return object()

    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_BUCKET", "bombavtest")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("S3_REGION", "us-east-1")
    monkeypatch.setenv("S3_ADDRESSING_STYLE", "path")
    monkeypatch.setattr(storage.boto3, "client", fake_client)

    storage.s3_client()
    assert captured["service_name"] == "s3"
    assert captured["endpoint_url"] == "http://minio:9000"
    assert captured["region_name"] == "us-east-1"
    assert captured["aws_access_key_id"] == "key"
    assert captured["aws_secret_access_key"] == "secret"
