from __future__ import annotations

from fastapi.responses import Response

from backend import admin as admin_module


def fake_storage(monkeypatch):
    stored: dict[str, bytes] = {}

    def upload(upload, key: str, mime_type: str):
        upload.file.seek(0)
        stored[key] = upload.file.read()

    def delete(key: str):
        stored.pop(key, None)

    def download(key: str, filename: str, mime_type: str):
        return Response(stored[key], media_type=mime_type)

    monkeypatch.setattr(admin_module, "s3_upload_file", upload)
    monkeypatch.setattr(admin_module, "s3_delete_file", delete)
    monkeypatch.setattr(admin_module, "s3_download_response", download)
    return stored


def test_attachment_upload_download_and_delete(admin, monkeypatch):
    client, headers = admin
    stored = fake_storage(monkeypatch)
    upload = client.post(
        "/api/admin/topics/1/attachments",
        headers=headers,
        files=[("files", ("manual.pdf", b"contenido", "application/pdf"))],
    )
    assert upload.status_code == 201
    attachment = upload.json()["data"][0]
    assert len(stored) == 1
    download = client.get(attachment["download_url"])
    assert download.status_code == 200 and download.content == b"contenido"
    assert client.delete(f"/api/admin/topics/1/attachments/{attachment['id']}", headers=headers).status_code == 200
    assert stored == {}


def test_attachment_rejects_empty_file(admin, monkeypatch):
    client, headers = admin
    stored = fake_storage(monkeypatch)
    response = client.post(
        "/api/admin/topics/1/attachments",
        headers=headers,
        files=[("files", ("empty.txt", b"", "text/plain"))],
    )
    assert response.status_code == 400
    assert stored == {}


def test_attachment_upload_rolls_back_storage_when_second_file_fails(admin, monkeypatch):
    client, headers = admin
    stored: dict[str, bytes] = {}
    calls = 0

    def upload(file, key: str, mime_type: str):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("storage failure")
        file.file.seek(0)
        stored[key] = file.file.read()

    def delete(key: str):
        stored.pop(key, None)

    monkeypatch.setattr(admin_module, "s3_upload_file", upload)
    monkeypatch.setattr(admin_module, "s3_delete_file", delete)
    response = client.post(
        "/api/admin/topics/1/attachments",
        headers=headers,
        files=[
            ("files", ("one.txt", b"one", "text/plain")),
            ("files", ("two.txt", b"two", "text/plain")),
        ],
    )
    assert response.status_code == 503
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


def test_storage_upload_and_delete_forward_to_s3(monkeypatch):
    from io import BytesIO
    from starlette.datastructures import Headers
    from fastapi import UploadFile
    from backend import storage

    calls = []

    class FakeS3:
        def upload_fileobj(self, file, bucket, key, **kwargs):
            calls.append(("upload", file.read(), bucket, key, kwargs))

        def delete_object(self, **kwargs):
            calls.append(("delete", kwargs))

    monkeypatch.setenv("S3_BUCKET", "bucket")
    monkeypatch.setattr(storage, "s3_client", lambda: FakeS3())
    upload = UploadFile(BytesIO(b"abc"), filename="a.txt", headers=Headers({"content-type": "text/plain"}))
    storage.upload_file(upload, "topics/a.txt", "text/plain")
    storage.delete_file("topics/a.txt")

    assert calls[0] == ("upload", b"abc", "bucket", "topics/a.txt", {"ExtraArgs": {"ContentType": "text/plain"}})
    assert calls[1] == ("delete", {"Bucket": "bucket", "Key": "topics/a.txt"})


def test_storage_configuration_rejects_missing_or_partial_credentials(monkeypatch):
    from backend import storage

    monkeypatch.delenv("S3_BUCKET", raising=False)
    try:
        storage.bucket_name()
    except RuntimeError as exc:
        assert "S3_BUCKET" in str(exc)
    else:
        raise AssertionError("Missing S3_BUCKET must fail")

    monkeypatch.setenv("S3_ACCESS_KEY_ID", "key")
    monkeypatch.delenv("S3_SECRET_ACCESS_KEY", raising=False)
    try:
        storage.s3_client()
    except RuntimeError as exc:
        assert "deben configurarse juntos" in str(exc)
    else:
        raise AssertionError("Partial S3 credentials must fail")


def test_storage_download_maps_missing_objects(monkeypatch):
    from botocore.exceptions import ClientError
    from backend import storage

    class FakeS3:
        def get_object(self, **kwargs):
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")

    monkeypatch.setenv("S3_BUCKET", "bucket")
    monkeypatch.setattr(storage, "s3_client", lambda: FakeS3())
    try:
        storage.download_response("missing", "missing.pdf", "application/pdf")
    except FileNotFoundError as exc:
        assert exc.args[0] == "missing"
    else:
        raise AssertionError("NoSuchKey must become FileNotFoundError")
