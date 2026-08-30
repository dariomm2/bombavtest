from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import MAX_JSON_BYTES, MAX_UPLOAD_REQUEST_BYTES


class RequestBodyTooLarge(Exception):
    """Internal control-flow exception raised while consuming an oversized body."""


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def _media_type(scope: Scope) -> str:
    raw = _header(scope, b"content-type") or ""
    return raw.split(";", 1)[0].strip().lower()


def _content_length(scope: Scope) -> int | None:
    raw = _header(scope, b"content-length")
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


class RequestBodyLimitMiddleware:
    """Bound selected request bodies while they are being received.

    Content-Length is used only as an early rejection optimization. The real
    enforcement counts ASGI body bytes, so missing, false or chunked lengths
    cannot bypass the limit.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        json_limit: int = MAX_JSON_BYTES,
        upload_limit: int = MAX_UPLOAD_REQUEST_BYTES,
    ) -> None:
        self.app = app
        self.json_limit = int(json_limit)
        self.upload_limit = int(upload_limit)

    def _limit_for(self, scope: Scope) -> tuple[int | None, str]:
        media_type = _media_type(scope)
        if media_type == "application/json" or media_type.endswith("+json"):
            return self.json_limit, "La petición supera el tamaño máximo permitido."
        if media_type == "multipart/form-data":
            return self.upload_limit, "La subida supera el tamaño máximo permitido."
        return None, ""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit, error_message = self._limit_for(scope)
        if limit is None:
            await self.app(scope, receive, send)
            return

        declared_length = _content_length(scope)
        if declared_length is not None and declared_length > limit:
            response = JSONResponse(
                {"ok": False, "error": error_message},
                status_code=413,
            )
            await response(scope, receive, send)
            return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestBodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except RequestBodyTooLarge:
            # Request bodies used by BombAvTest are consumed before an endpoint
            # starts its response. Guard this anyway to avoid a second response
            # if that invariant changes in the future.
            if response_started:
                raise
            response = JSONResponse(
                {"ok": False, "error": error_message},
                status_code=413,
            )
            await response(scope, receive, send)
