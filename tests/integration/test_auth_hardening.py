from __future__ import annotations

from backend import auth


def test_unknown_user_still_runs_password_verification(client, monkeypatch):
    calls = []

    def fake_verify(password: str, stored_hash: str) -> bool:
        calls.append((password, stored_hash))
        return False

    monkeypatch.setattr(auth, "verify_password", fake_verify)

    response = client.post(
        "/api/login",
        json={"username": "usuario.que.no.existe", "password": "Clave123"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"
    assert calls == [("Clave123", auth.DUMMY_PASSWORD_HASH)]
