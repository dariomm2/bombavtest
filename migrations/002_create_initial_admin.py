from __future__ import annotations

import os

from yoyo import step

from backend.auth import hash_password

__depends__ = {"001_create_schema"}



def create_initial_admin(conn) -> None:
    cursor = conn.cursor()
    if int(cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]) != 0:
        return

    username = os.environ.get("BOMBAVTEST_ADMIN_USERNAME", "").strip()
    password = os.environ.get("BOMBAVTEST_ADMIN_PASSWORD", "")
    display_name = os.environ.get("BOMBAVTEST_ADMIN_DISPLAY_NAME", "").strip()

    if not username or not password or not display_name:
        raise RuntimeError(
            "La base está vacía. Configura BOMBAVTEST_ADMIN_USERNAME, "
            "BOMBAVTEST_ADMIN_PASSWORD y BOMBAVTEST_ADMIN_DISPLAY_NAME."
        )
    if len(username) > 80 or len(password) > 256 or len(display_name) > 160:
        raise RuntimeError("Las variables del administrador inicial no son válidas.")

    cursor.execute(
        """
        INSERT INTO users(username, display_name, password_hash, role, is_active, created_at)
        VALUES (?, ?, ?, 'admin', 1, strftime('%Y-%m-%dT%H:%M:%f+00:00','now'))
        """,
        (username, display_name, hash_password(password)),
    )


steps = [step(create_initial_admin)]
