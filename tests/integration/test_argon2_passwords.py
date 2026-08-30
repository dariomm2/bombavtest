from __future__ import annotations

from contextlib import closing
import sqlite3

from backend.auth import hash_password, verify_password


def test_argon2id_parameters_and_round_trip():
    password_hash = hash_password("Clave123")

    assert password_hash.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert verify_password("Clave123", password_hash)
    assert not verify_password("Otra123", password_hash)


def test_new_user_uses_argon2_without_separate_salt(admin, user_factory, app_env):
    client, headers = admin
    user_id = user_factory(
        client,
        headers,
        username="argon-user",
        password="Clave123",
    )

    with closing(sqlite3.connect(app_env)) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()}
        stored_hash = db.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()[0]

    assert "password_salt" not in columns
    assert stored_hash.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert verify_password("Clave123", stored_hash)
