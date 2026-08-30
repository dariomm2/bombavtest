from __future__ import annotations

from contextlib import closing
from datetime import timedelta
import hashlib
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.config import MAX_JSON_BYTES, SESSION_COOKIE


def payload(response):
    assert response.status_code < 400, response.text
    return response.json()["data"]


def error(response, status: int, code: str | None = None):
    assert response.status_code == status, response.text
    body = response.json()
    assert body["ok"] is False
    if code is not None:
        assert body.get("code") == code


def login(client: TestClient, username: str, password: str):
    response = client.post(
        "/api/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["data"]["csrf_token"]}


def test_health_and_frontend_routes(client: TestClient):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert health.json()["status"] == "healthy"

    assert 'window.BOMBAVTEST_VERSION' in client.get("/version.js").text
    assert 'window.BOMBAVTEST_REVISION' in client.get("/version.js").text

    for route in (
        "/",
        "/login",
        "/statistics",
        "/questions",
        "/admin",
        "/aviso-legal",
        "/politica-privacidad",
    ):
        assert client.get(route).status_code == 200

    assert client.get("/styles.css").status_code == 200
    assert client.get("/script.js").status_code == 200


def test_docs_are_disabled_and_spa_fallback_is_enabled(client: TestClient):
    for route in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(route).status_code == 404

    response = client.get("/ruta-frontend-inventada")
    assert response.status_code == 200
    assert "<!doctype html>" in response.text.lower()

    error(client.get("/api/no-existe"), 404)


def test_me_requires_authentication(client: TestClient):
    error(client.get("/api/me"), 401, "UNAUTHORIZED")


def test_login_and_me(client: TestClient):
    headers = login(client, "ADMIN", "admin")
    data = payload(client.get("/api/me"))

    assert data["user"]["username"] == "admin"
    assert data["user"]["role"] == "admin"
    assert headers["X-CSRF-Token"] == data["csrf_token"]


def test_login_sets_security_cookie_attributes_over_https(client: TestClient):
    response = client.post(
        "/api/login",
        headers={"X-Forwarded-Proto": "https"},
        json={"username": "admin", "password": "admin"},
    )

    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" in cookie


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"username": "", "password": "admin"},
        {"username": "admin", "password": ""},
        {"username": "admin", "password": "incorrecta"},
        {"username": "x" * 81, "password": "admin"},
    ],
)
def test_login_rejects_invalid_credentials(client: TestClient, body):
    error(client.post("/api/login", json=body), 401 if body else 400)


def test_inactive_user_cannot_login(admin, user_factory, app_env):
    client, headers = admin
    user_factory(
        client,
        headers,
        username="inactivo",
        password="Clave123",
    )

    with closing(sqlite3.connect(app_env)) as db:
        db.execute(
            "UPDATE users SET is_active = 0 WHERE username = ?",
            ("inactivo",),
        )
        db.commit()

    with TestClient(client.app, raise_server_exceptions=False) as separate:
        error(
            separate.post(
                "/api/login",
                json={"username": "inactivo", "password": "Clave123"},
            ),
            401,
            "INVALID_CREDENTIALS",
        )


def test_logout_requires_csrf_and_invalidates_session(client: TestClient):
    headers = login(client, "admin", "admin")

    error(client.post("/api/logout"), 403, "CSRF")
    assert client.post("/api/logout", headers=headers).status_code == 200
    error(client.get("/api/me"), 401, "UNAUTHORIZED")


def test_state_changing_admin_endpoint_requires_csrf(admin):
    client, _ = admin

    error(
        client.post(
            "/api/admin/topics",
            json={"number": "X", "name": "X", "color": "#000000"},
        ),
        403,
        "CSRF",
    )
    error(
        client.post(
            "/api/admin/topics",
            headers={"X-CSRF-Token": "incorrecto"},
            json={"number": "X", "name": "X", "color": "#000000"},
        ),
        403,
        "CSRF",
    )


def test_non_admin_cannot_use_admin_api(admin, user_factory, login_user):
    admin_client, headers = admin
    user_factory(
        admin_client,
        headers,
        username="alumno",
        password="Clave123",
    )

    user_client, _ = login_user(admin_client.app, "alumno", "Clave123")
    error(user_client.get("/api/admin/users"), 403, "FORBIDDEN")


def test_expired_session_is_rejected(client: TestClient, app_env):
    login(client, "admin", "admin")

    token = client.cookies.get(SESSION_COOKIE)
    assert token is not None
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    with closing(sqlite3.connect(app_env)) as db:
        db.execute(
            "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
            (
                auth.utc_iso(auth.utc_now() - timedelta(days=1)),
                token_hash,
            ),
        )
        db.commit()

    error(client.get("/api/me"), 401, "UNAUTHORIZED")


def test_login_rate_limit_and_success_clears_counters(client: TestClient):
    for _ in range(10):
        assert client.post(
            "/api/login",
            json={"username": "admin", "password": "mal"},
        ).status_code == 401

    error(
        client.post(
            "/api/login",
            json={"username": "admin", "password": "admin"},
        ),
        429,
        "RATE_LIMIT",
    )

    auth.LOGIN_ATTEMPTS.clear()
    assert client.post(
        "/api/login",
        json={"username": "admin", "password": "admin"},
    ).status_code == 200
    assert not auth.LOGIN_ATTEMPTS


def test_malformed_json_returns_application_error(client: TestClient):
    response = client.post(
        "/api/login",
        content=b"{",
        headers={"Content-Type": "application/json"},
    )
    error(response, 400)


def test_json_larger_than_limit_is_not_parsed(client: TestClient):
    response = client.post(
        "/api/login",
        content=b'{"username":"' + b"x" * MAX_JSON_BYTES + b'"}',
        headers={"Content-Type": "application/json"},
    )
    error(response, 413)


def test_security_headers_are_applied_consistently(client: TestClient):
    for route in ("/", "/api/no-existe", "/styles.css"):
        response = client.get(route)

        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert (
            response.headers["referrer-policy"]
            == "strict-origin-when-cross-origin"
        )
        assert (
            response.headers["permissions-policy"]
            == "camera=(), microphone=(), geolocation=()"
        )
        assert (
            response.headers["strict-transport-security"]
            == "max-age=31536000"
        )


def test_csp_is_active_and_static_html_has_no_inline_styles(client: TestClient):
    response = client.get("/")
    csp = response.headers["content-security-policy"]

    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'none'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert " style=" not in response.text.lower()
