from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from datetime import date, datetime, time as dt_time, timedelta, timezone
from functools import wraps
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from starlette.requests import Request

from .config import (
    LOGIN_RATE_MAX,
    LOGIN_RATE_MAX_KEYS,
    LOGIN_RATE_WINDOW,
    PBKDF2_ITERATIONS,
    SESSION_COOKIE,
    SESSION_DAYS,
)
from .db import bind_db, connect_db, get_db, reset_db

MADRID_TZ = ZoneInfo("Europe/Madrid")
LOGIN_ATTEMPTS: dict[str, deque[float]] = defaultdict(deque)
DUMMY_PASSWORD_SALT = "00" * 16
DUMMY_PASSWORD_HASH = "00" * 32
router = APIRouter()

_current_request: ContextVar[Request | None] = ContextVar("bombavtest_request", default=None)
_current_session: ContextVar[sqlite3.Row | None] = ContextVar("bombavtest_session_row", default=None)
_json_body_value: ContextVar[Any] = ContextVar("bombavtest_json_body", default=None)


def password_digest(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    ).hex()


def verify_password(password: str, salt_hex: str, stored_hash: str) -> bool:
    candidate = password_digest(password, salt_hex)
    return hmac.compare_digest(candidate, stored_hash)

class _GProxy:
    @property
    def current_session(self) -> sqlite3.Row:
        value = _current_session.get()
        if value is None:
            raise RuntimeError("No hay una sesión autenticada en este contexto.")
        return value

    @current_session.setter
    def current_session(self, value: sqlite3.Row) -> None:
        _current_session.set(value)


g = _GProxy()

class _RequestProxy:
    def _request(self) -> Request:
        value = _current_request.get()
        if value is None:
            raise RuntimeError("No hay una petición HTTP en este contexto.")
        return value

    @property
    def cookies(self):
        return self._request().cookies

    @property
    def headers(self):
        return self._request().headers

    @property
    def args(self):
        return self._request().query_params

    @property
    def remote_addr(self) -> str | None:
        client = self._request().client
        return client.host if client else None

    @property
    def is_secure(self) -> bool:
        return self._request().url.scheme == "https"

    @property
    def path(self) -> str:
        return self._request().url.path

    def get_json(self, silent: bool = True):
        return _json_body_value.get()


request = _RequestProxy()

def jsonify(payload: Any) -> JSONResponse:
    return JSONResponse(payload)


def make_response(response: Response) -> Response:
    return response


async def bombavtest_request_context(http_request: Request, call_next):
    request_token = _current_request.set(http_request)
    db_token = None
    json_token = _json_body_value.set(None)
    session_token = _current_session.set(None)
    db = None
    try:
        content_type = http_request.headers.get("content-type", "").lower()
        if content_type.startswith("application/json"):
            raw = await http_request.body()
            if raw:
                try:
                    parsed = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    parsed = None
                _json_body_value.set(parsed)

        if http_request.url.path.startswith("/api/") or http_request.url.path == "/health":
            db = connect_db()
            db_token = bind_db(db)

        response = await call_next(http_request)
        return response
    finally:
        if db_token is not None:
            reset_db(db_token)
        if db is not None:
            db.close()
        _current_session.reset(session_token)
        _json_body_value.reset(json_token)
        _current_request.reset(request_token)

def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

def utc_iso(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat()

def madrid_today() -> date:
    return datetime.now(MADRID_TZ).date()

def madrid_day_bounds(day: date) -> tuple[str, str]:
    start = datetime.combine(day, dt_time.min, tzinfo=MADRID_TZ).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), dt_time.min, tzinfo=MADRID_TZ).astimezone(timezone.utc)
    return utc_iso(start), utc_iso(end)

def madrid_month_start_utc(day: date | None = None) -> str:
    current = day or madrid_today()
    first = current.replace(day=1)
    return madrid_day_bounds(first)[0]

def madrid_date_from_utc_iso(value: str) -> date:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(MADRID_TZ).date()

def session_from_request() -> sqlite3.Row | None:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        return None

    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    now = utc_iso()
    row = get_db().execute(
        """
        SELECT s.id AS session_id, s.csrf_token, s.expires_at,
               u.id AS user_id, u.username, u.display_name, u.role, u.is_active
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ? AND s.expires_at > ?
        """,
        (token_hash, now),
    ).fetchone()

    if row and row["is_active"]:
        return row
    return None

def api_ok(data: Any = None, status: int = 200):
    return JSONResponse({"ok": True, "data": data}, status_code=status)

def api_error(message: str, status: int = 400, code: str | None = None):
    payload: dict[str, Any] = {"ok": False, "error": message}
    if code:
        payload["code"] = code
    return JSONResponse(payload, status_code=status)

def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        session = session_from_request()
        if not session:
            return api_error("Sesión no válida o caducada.", 401, "UNAUTHORIZED")
        g.current_session = session
        return view(*args, **kwargs)

    return wrapped

def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        session = session_from_request()
        if not session:
            return api_error("Sesión no válida o caducada.", 401, "UNAUTHORIZED")
        g.current_session = session
        if session["role"] != "admin":
            return api_error("No tienes permisos de administrador.", 403, "FORBIDDEN")
        return view(*args, **kwargs)

    return wrapped

def require_csrf() -> tuple[bool, Any | None]:
    expected = g.current_session["csrf_token"]
    received = request.headers.get("X-CSRF-Token", "")
    if not received or not hmac.compare_digest(expected, received):
        return False, api_error("Solicitud no válida.", 403, "CSRF")
    return True, None

def json_body() -> dict[str, Any] | None:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None

def user_id() -> int:
    return int(g.current_session["user_id"])

def login_rate_keys(username: str) -> tuple[str, str]:
    ip = request.remote_addr or "unknown"
    return f"ip:{ip}", f"user:{username.casefold()}"

def trim_login_attempts(key: str, now: float) -> deque[float]:
    attempts = LOGIN_ATTEMPTS[key]
    cutoff = now - LOGIN_RATE_WINDOW
    while attempts and attempts[0] <= cutoff:
        attempts.popleft()
    if not attempts:
        LOGIN_ATTEMPTS.pop(key, None)
        return deque()
    return attempts

def prune_login_attempts(now: float) -> None:
    if len(LOGIN_ATTEMPTS) < LOGIN_RATE_MAX_KEYS:
        return
    for key in list(LOGIN_ATTEMPTS):
        trim_login_attempts(key, now)
    while len(LOGIN_ATTEMPTS) >= LOGIN_RATE_MAX_KEYS:
        LOGIN_ATTEMPTS.pop(next(iter(LOGIN_ATTEMPTS)), None)

def login_is_limited(keys: tuple[str, str]) -> bool:
    now = time.monotonic()
    prune_login_attempts(now)
    return any(len(trim_login_attempts(key, now)) >= LOGIN_RATE_MAX for key in keys)

def record_failed_login(keys: tuple[str, str]) -> None:
    now = time.monotonic()
    for key in keys:
        attempts = trim_login_attempts(key, now)
        if key not in LOGIN_ATTEMPTS:
            LOGIN_ATTEMPTS[key] = attempts
        LOGIN_ATTEMPTS[key].append(now)

def clear_login_attempts(keys: tuple[str, str]) -> None:
    for key in keys:
        LOGIN_ATTEMPTS.pop(key, None)

def secure_cookie_request() -> bool:
    forwarded_proto = (request.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
    return request.is_secure or forwarded_proto == "https" or os.environ.get("COOKIE_SECURE") == "1"

def clean_submission_key(value: Any, prefix: str) -> str:
    key = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9:_-]{8,160}", key):
        raise ValueError("Identificador de envío no válido.")
    return f"{prefix}:{key}"

@router.post("/api/login")
def login():
    data = json_body()
    if not data:
        return api_error("Introduce usuario y contraseña.")

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not username or not password or len(username) > 80 or len(password) > 256:
        return api_error("Usuario o contraseña incorrectos.", 401, "INVALID_CREDENTIALS")

    rate_keys = login_rate_keys(username)
    if login_is_limited(rate_keys):
        return api_error("Demasiados intentos de acceso. Espera un minuto y vuelve a intentarlo.", 429, "RATE_LIMIT")

    db = get_db()
    account = db.execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
    ).fetchone()

    if account and account["is_active"]:
        password_salt = account["password_salt"]
        password_hash = account["password_hash"]
    else:
        password_salt = DUMMY_PASSWORD_SALT
        password_hash = DUMMY_PASSWORD_HASH

    password_valid = verify_password(password, password_salt, password_hash)
    if not account or not account["is_active"] or not password_valid:
        record_failed_login(rate_keys)
        return api_error("Usuario o contraseña incorrectos.", 401, "INVALID_CREDENTIALS")
    clear_login_attempts(rate_keys)

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    csrf_token = secrets.token_urlsafe(24)
    created = utc_now()
    expires = created + timedelta(days=SESSION_DAYS)

    db.execute("DELETE FROM sessions WHERE expires_at <= ?", (utc_iso(created),))
    db.execute(
        "INSERT INTO sessions(user_id, token_hash, csrf_token, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
        (account["id"], token_hash, csrf_token, utc_iso(expires), utc_iso(created)),
    )
    db.commit()

    response = make_response(jsonify({
        "ok": True,
        "data": {
            "user": {
                "id": int(account["id"]), "username": account["username"],
                "display_name": account["display_name"], "role": account["role"],
            },
            "csrf_token": csrf_token,
        },
    }))
    response.set_cookie(
        SESSION_COOKIE, raw_token, max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True, samesite="Lax", secure=secure_cookie_request(), path="/",
    )
    return response

@router.post("/api/logout")
@require_auth
def logout():
    valid, error = require_csrf()
    if not valid:
        return error

    raw_token = request.cookies.get(SESSION_COOKIE, "")
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    db = get_db()
    db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
    db.commit()

    response = make_response(jsonify({"ok": True, "data": None}))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response

@router.get("/api/me")
@require_auth
def me():
    session = g.current_session
    return api_ok(
        {
            "user": {
                "id": int(session["user_id"]),
                "username": session["username"],
                "display_name": session["display_name"],
                "role": session["role"],
            },
            "csrf_token": session["csrf_token"],
        }
    )

