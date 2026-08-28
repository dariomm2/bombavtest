from __future__ import annotations

import os
from typing import Iterator
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import UploadFile
from fastapi.responses import StreamingResponse


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Falta la variable de entorno {name} para el almacenamiento S3.")
    return value


def bucket_name() -> str:
    return _required("S3_BUCKET")


def s3_client():
    endpoint = os.environ.get("S3_ENDPOINT_URL", "").strip() or None
    region = os.environ.get("S3_REGION", "").strip() or None
    access_key = os.environ.get("S3_ACCESS_KEY_ID", "").strip() or None
    secret_key = os.environ.get("S3_SECRET_ACCESS_KEY", "").strip() or None
    addressing_style = os.environ.get("S3_ADDRESSING_STYLE", "auto").strip().lower() or "auto"

    kwargs = {
        "endpoint_url": endpoint,
        "region_name": region,
        "config": Config(s3={"addressing_style": addressing_style}),
    }
    if access_key or secret_key:
        if not access_key or not secret_key:
            raise RuntimeError("S3_ACCESS_KEY_ID y S3_SECRET_ACCESS_KEY deben configurarse juntos.")
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    return boto3.client("s3", **kwargs)


def upload_file(upload: UploadFile, key: str, mime_type: str) -> None:
    upload.file.seek(0)
    extra = {"ContentType": mime_type} if mime_type else None
    kwargs = {"ExtraArgs": extra} if extra else {}
    s3_client().upload_fileobj(upload.file, bucket_name(), key, **kwargs)


def delete_file(key: str) -> None:
    s3_client().delete_object(Bucket=bucket_name(), Key=key)


def download_response(key: str, filename: str, mime_type: str) -> StreamingResponse:
    try:
        result = s3_client().get_object(Bucket=bucket_name(), Key=key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"NoSuchKey", "NoSuchBucket", "404", "NotFound"}:
            raise FileNotFoundError(key) from exc
        raise RuntimeError("No se ha podido acceder al almacenamiento de archivos.") from exc

    body = result["Body"]

    def chunks() -> Iterator[bytes]:
        try:
            while True:
                chunk = body.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            body.close()

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "X-Content-Type-Options": "nosniff",
    }
    if result.get("ContentLength") is not None:
        headers["Content-Length"] = str(result["ContentLength"])
    return StreamingResponse(chunks(), media_type=mime_type, headers=headers)
