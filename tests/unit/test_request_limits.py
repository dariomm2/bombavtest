from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Coroutine
from typing import Any

from backend.request_limits import RequestBodyLimitMiddleware


def _scope(*, content_type: str, content_length: str | None = None):
    headers = [(b"content-type", content_type.encode("ascii"))]
    if content_length is not None:
        headers.append((b"content-length", content_length.encode("ascii")))
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/test",
        "raw_path": b"/api/test",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    }


def _run_async(coro: Coroutine[Any, Any, None]) -> None:
    """Run a coroutine even if the test runner already owns an event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return

    error: list[BaseException] = []

    def runner() -> None:
        try:
            asyncio.run(coro)
        except BaseException as exc:
            error.append(exc)

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()

    if error:
        raise error[0]


def _run(
    *,
    content_type: str,
    chunks: list[bytes],
    json_limit: int = 8,
    upload_limit: int = 12,
    content_length: str | None = None,
):
    sent = []
    observed = {"bytes": 0, "receive_calls": 0, "completed": False}
    messages = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]
    if not messages:
        messages = [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive():
        observed["receive_calls"] += 1
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    async def inner_app(scope, receive_inner, send_inner):
        while True:
            message = await receive_inner()
            if message["type"] != "http.request":
                break
            observed["bytes"] += len(message.get("body", b""))
            if not message.get("more_body", False):
                break

        observed["completed"] = True
        await send_inner({"type": "http.response.start", "status": 200, "headers": []})
        await send_inner({"type": "http.response.body", "body": b"ok"})

    middleware = RequestBodyLimitMiddleware(
        inner_app,
        json_limit=json_limit,
        upload_limit=upload_limit,
    )

    async def invoke() -> None:
        await middleware(
            _scope(content_type=content_type, content_length=content_length),
            receive,
            send,
        )

    _run_async(invoke())
    return sent, observed


def _status(sent):
    return next(
        message["status"]
        for message in sent
        if message["type"] == "http.response.start"
    )


def _json_body(sent):
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return json.loads(body)


def test_rejects_oversized_declared_json_without_reading_body():
    sent, observed = _run(
        content_type="application/json",
        chunks=[b"ignored"],
        json_limit=8,
        content_length="9",
    )
    assert _status(sent) == 413
    assert observed["receive_calls"] == 0
    assert observed["completed"] is False


def test_stream_limit_cannot_be_bypassed_without_content_length():
    sent, observed = _run(
        content_type="application/json",
        chunks=[b"1234", b"5678", b"9"],
        json_limit=8,
    )
    assert _status(sent) == 413
    assert observed["completed"] is False
    assert _json_body(sent)["ok"] is False


def test_false_small_content_length_cannot_bypass_real_byte_count():
    sent, observed = _run(
        content_type="application/json",
        chunks=[b"1234", b"56789"],
        json_limit=8,
        content_length="1",
    )
    assert _status(sent) == 413
    assert observed["completed"] is False


def test_malformed_content_length_falls_back_to_stream_counting():
    sent, observed = _run(
        content_type="application/json",
        chunks=[b"123456789"],
        json_limit=8,
        content_length="not-a-number",
    )
    assert _status(sent) == 413
    assert observed["completed"] is False


def test_multipart_is_limited_while_streaming():
    sent, observed = _run(
        content_type="multipart/form-data; boundary=test",
        chunks=[b"123456", b"789012", b"3"],
        upload_limit=12,
    )
    assert _status(sent) == 413
    assert observed["completed"] is False


def test_request_at_limit_passes_unchanged():
    sent, observed = _run(
        content_type="application/json; charset=utf-8",
        chunks=[b"1234", b"5678"],
        json_limit=8,
    )
    assert _status(sent) == 200
    assert observed["bytes"] == 8
    assert observed["completed"] is True


def test_unrelated_content_type_is_not_limited_by_this_middleware():
    sent, observed = _run(
        content_type="text/plain",
        chunks=[b"x" * 100],
        json_limit=8,
        upload_limit=12,
    )
    assert _status(sent) == 200
    assert observed["bytes"] == 100