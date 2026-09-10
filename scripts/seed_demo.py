from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from backend.auth import MADRID_TZ, hash_password
from backend.storage import bucket_name, s3_client


DB_PATH = Path(os.environ.get("BOMBAVTEST_DB_PATH", "/data/app.db"))
DEMO_PASSWORD = "Demo1234"
DEMO_TOPICS = (
    ("1", "Prevención y extinción", "#ef4444", "la intervención segura ante un incendio"),
    ("2", "Primeros auxilios", "#22c55e", "la primera atención a una víctima"),
    ("3", "Mercancías peligrosas", "#f59e0b", "la identificación de un riesgo químico"),
    ("4", "Vehículos y equipos", "#3b82f6", "la comprobación del material operativo"),
    ("5", "Comunicaciones", "#8b5cf6", "la transmisión de información durante una emergencia"),
)
DEMO_USERS = (
    ("demo", "Alumno Demo · racha pendiente", True, 4),
    ("demo-completed", "Alumno Demo · completado hoy", True, 5),
    ("demo-new", "Alumno Demo · sin racha", True, 2),
    ("demo-disabled", "Alumno Demo · desactivado", False, 3),
)


def utc_iso_for_day(day: date, hour: int, minute: int = 0) -> str:
    local = datetime.combine(day, time(hour, minute), tzinfo=MADRID_TZ)
    return local.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def migrate_legacy_demo_topics(db: sqlite3.Connection) -> None:
    db.execute("DELETE FROM questions WHERE text LIKE '[DEMO DEMO-%'")
    for number, *_ in DEMO_TOPICS:
        legacy = db.execute(
            "SELECT id FROM topics WHERE number = ? COLLATE NOCASE",
            (f"DEMO-{number}",),
        ).fetchone()
        if not legacy:
            continue
        current = db.execute("SELECT id FROM topics WHERE number = ? COLLATE NOCASE", (number,)).fetchone()
        if current and int(current[0]) != int(legacy[0]):
            db.execute("DELETE FROM topics WHERE id = ?", (int(legacy[0]),))
        else:
            db.execute("UPDATE topics SET number = ? WHERE id = ?", (number, int(legacy[0])))


def upsert_topic(db: sqlite3.Connection, number: str, name: str, color: str, now: str) -> int:
    row = db.execute("SELECT id FROM topics WHERE number = ? COLLATE NOCASE", (number,)).fetchone()
    if row:
        topic_id = int(row[0])
        db.execute("UPDATE topics SET name = ?, color = ? WHERE id = ?", (name, color, topic_id))
        return topic_id
    cursor = db.execute(
        "INSERT INTO topics(number, name, color, created_at) VALUES (?, ?, ?, ?)",
        (number, name, color, now),
    )
    return int(cursor.lastrowid)


def upsert_question(
    db: sqlite3.Connection,
    topic_id: int,
    topic_number: str,
    scenario: str,
    index: int,
    now: str,
) -> int:
    marker = f"[DEMO {topic_number}-{index:02d}]"
    text = f"{marker} ¿Cuál sería la actuación prioritaria en el caso {index} relacionado con {scenario}?"
    explanation = (
        "Pregunta generada para visualizar la aplicación en local. "
        "La respuesta correcta prioriza siempre la evaluación del riesgo y el procedimiento seguro."
    )
    row = db.execute("SELECT id FROM questions WHERE text LIKE ? LIMIT 1", (f"{marker}%",)).fetchone()
    if row:
        question_id = int(row[0])
        db.execute(
            "UPDATE questions SET topic_id = ?, text = ?, explanation = ?, updated_at = ? WHERE id = ?",
            (topic_id, text, explanation, now, question_id),
        )
        db.execute("DELETE FROM options WHERE question_id = ?", (question_id,))
    else:
        cursor = db.execute(
            """INSERT INTO questions(topic_id, text, explanation, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (topic_id, text, explanation, now, now),
        )
        question_id = int(cursor.lastrowid)

    options = (
        "Evaluar los riesgos, comunicar la situación y aplicar el procedimiento seguro",
        "Actuar inmediatamente sin valorar el entorno",
        "Esperar sin informar al resto del equipo",
        "Prescindir de los equipos de protección para ganar tiempo",
    )
    db.executemany(
        "INSERT INTO options(question_id, text, position, is_correct) VALUES (?, ?, ?, ?)",
        [(question_id, option, position, position == 0) for position, option in enumerate(options)],
    )
    return question_id


def upsert_user(
    db: sqlite3.Connection,
    username: str,
    display_name: str,
    active: bool,
    now: str,
) -> int:
    password_hash = hash_password(DEMO_PASSWORD)
    row = db.execute("SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
    if row:
        user_id = int(row[0])
        db.execute(
            """UPDATE users
               SET display_name = ?, password_hash = ?, role = 'user', is_active = ?, deactivated_at = ?
               WHERE id = ?""",
            (display_name, password_hash, int(active), None if active else now, user_id),
        )
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        return user_id
    cursor = db.execute(
        """INSERT INTO users(
               username, display_name, password_hash, role, is_active, created_at, deactivated_at
           ) VALUES (?, ?, ?, 'user', ?, ?, ?)""",
        (username, display_name, password_hash, int(active), now, None if active else now),
    )
    return int(cursor.lastrowid)


def seed_attempts(
    db: sqlite3.Connection,
    user_id: int,
    username: str,
    question_ids: list[int],
    today: date,
    count: int,
    correct_question_count: int,
    salt: int,
) -> None:
    rows = []
    for index in range(count):
        question_position = (index * 7 + salt) % len(question_ids)
        question_id = question_ids[question_position]
        day = today - timedelta(days=(index * 11 + salt) % 28)
        if index % 17 == 0:
            outcome = "skipped"
        elif question_position < correct_question_count and (index + salt) % 4 != 0:
            outcome = "correct"
        else:
            outcome = "incorrect"
        rows.append(
            (
                user_id,
                question_id,
                outcome,
                "simulation" if index % 3 == 0 else "practice",
                f"demo-seed:{username}:{index:04d}",
                utc_iso_for_day(day, 8 + index % 12, (index * 7) % 60),
            )
        )
    db.executemany(
        """INSERT INTO attempts(user_id, question_id, outcome, source, submission_key, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        rows,
    )


def seed_attachments(db: sqlite3.Connection, topic_ids: list[int], now: str) -> None:
    if not os.environ.get("S3_BUCKET"):
        return
    attachments = (
        (
            topic_ids[0],
            "guia-seguridad-demo.txt",
            "demo-seed/guia-seguridad-demo.txt",
            "text/plain",
            "Guía de demostración\n\nEvalúa los riesgos antes de intervenir.\n".encode(),
        ),
        (
            topic_ids[1],
            "comprobaciones-demo.csv",
            "demo-seed/comprobaciones-demo.csv",
            "text/csv",
            "elemento,estado\nBotiquín,Revisado\nOxígeno,Disponible\n".encode(),
        ),
    )
    client = s3_client()
    bucket = bucket_name()
    for topic_id, filename, storage_key, mime_type, content in attachments:
        client.put_object(Bucket=bucket, Key=storage_key, Body=content, ContentType=mime_type)
        db.execute(
            """INSERT INTO topic_attachments(
                   topic_id, original_name, storage_key, mime_type, size_bytes, created_at
               ) VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(storage_key) DO UPDATE SET
                   topic_id = excluded.topic_id,
                   original_name = excluded.original_name,
                   mime_type = excluded.mime_type,
                   size_bytes = excluded.size_bytes""",
            (topic_id, filename, storage_key, mime_type, len(content), now),
        )


def seed_demo_data(db_path: Path = DB_PATH, today: date | None = None) -> None:
    current_day = today or datetime.now(MADRID_TZ).date()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        migrate_legacy_demo_topics(db)
        topic_ids: list[int] = []
        question_ids_by_topic: list[list[int]] = []
        for number, name, color, scenario in DEMO_TOPICS:
            topic_id = upsert_topic(db, number, name, color, now)
            topic_ids.append(topic_id)
            question_ids_by_topic.append(
                [upsert_question(db, topic_id, number, scenario, index, now) for index in range(1, 13)]
            )

        users: dict[str, int] = {}
        for username, display_name, active, topic_count in DEMO_USERS:
            uid = upsert_user(db, username, display_name, active, now)
            users[username] = uid
            db.execute("DELETE FROM user_topics WHERE user_id = ?", (uid,))
            db.executemany(
                "INSERT INTO user_topics(user_id, topic_id) VALUES (?, ?)",
                [(uid, topic_id) for topic_id in topic_ids[:topic_count]],
            )

        db.execute("DELETE FROM attempts WHERE submission_key LIKE 'demo-seed:%'")
        demo_questions = [question_id for group in question_ids_by_topic[:4] for question_id in group]
        seed_attempts(db, users["demo"], "demo", demo_questions[:30], current_day, 90, 18, 1)
        seed_attempts(db, users["demo-completed"], "demo-completed", demo_questions, current_day, 72, 38, 2)
        seed_attempts(db, users["demo-new"], "demo-new", question_ids_by_topic[0], current_day, 8, 3, 3)
        seed_attempts(db, users["demo-disabled"], "demo-disabled", demo_questions[:24], current_day, 36, 10, 4)

        demo_user_ids = list(users.values())
        placeholders = ",".join("?" for _ in demo_user_ids)
        db.execute(f"DELETE FROM daily_tests WHERE user_id IN ({placeholders})", demo_user_ids)
        db.executemany(
            "INSERT INTO daily_tests(user_id, completed_on) VALUES (?, ?)",
            [
                *[(users["demo"], (current_day - timedelta(days=offset)).isoformat()) for offset in range(1, 6)],
                *[
                    (users["demo-completed"], (current_day - timedelta(days=offset)).isoformat())
                    for offset in range(0, 7)
                ],
                (users["demo-new"], (current_day - timedelta(days=4)).isoformat()),
            ],
        )
        seed_attachments(db, topic_ids, now)
        db.commit()

    print(f"Demo data ready for {current_day.isoformat()}.")
    print(f"Login: demo / {DEMO_PASSWORD} (daily test pending)")
    print(f"Login: demo-completed / {DEMO_PASSWORD} (daily test completed)")
    print(f"Login: demo-new / {DEMO_PASSWORD} (no active streak)")


if __name__ == "__main__":
    seed_demo_data()
