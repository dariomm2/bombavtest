from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter

from .auth import (
    api_error, api_ok, clean_submission_key, g, json_body, madrid_date_from_utc_iso,
    madrid_day_bounds, madrid_today, request, require_auth, require_csrf, user_id, utc_iso,
)
from .db import get_db

router = APIRouter()

def topic_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "number": str(row["number"]),
        "name": row["name"],
        "color": row["color"],
    }

def topic_sort_key(value: Any) -> tuple[Any, ...]:
    """Natural-ish sort for hierarchical topic codes such as 1, 1.2, 1.3.a, 10."""
    parts = re.split(r"(\d+)", str(value or "").strip().casefold())
    return tuple((0, int(part)) if part.isdigit() else (1, part) for part in parts if part != "")

def topic_ids_for_user(uid: int, role: str | None = None, active_only: bool = True) -> list[int]:
    db = get_db()
    if role is None:
        row = db.execute("SELECT role FROM users WHERE id = ?", (uid,)).fetchone()
        role = str(row["role"]) if row else "user"
    if role == "admin":
        return [int(row["id"]) for row in db.execute("SELECT id FROM topics").fetchall()]
    return [
        int(row["topic_id"])
        for row in db.execute(
            "SELECT topic_id FROM user_topics WHERE user_id = ?", (uid,)
        ).fetchall()
    ]

def current_topic_ids() -> list[int]:
    return topic_ids_for_user(user_id(), str(g.current_session["role"]))

def ensure_topic_access(topic_ids: list[int]) -> bool:
    allowed = set(current_topic_ids())
    return all(int(topic_id) in allowed for topic_id in topic_ids)

def topic_filter_clause(topic_ids: list[int], column: str = "q.topic_id") -> tuple[str, list[Any]]:
    if not topic_ids:
        return "1 = 0", []
    placeholders = ",".join("?" for _ in topic_ids)
    return f"{column} IN ({placeholders})", list(topic_ids)

def attachment_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": row["original_name"],
        "mime_type": row["mime_type"] or "application/octet-stream",
        "size_bytes": int(row["size_bytes"]),
        "download_url": f"/api/topics/{int(row['topic_id'])}/attachments/{int(row['id'])}/download",
    }

def attachments_by_topic(topic_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    if not topic_ids:
        return result
    placeholders = ",".join("?" for _ in topic_ids)
    rows = get_db().execute(
        f"""SELECT id, topic_id, original_name, mime_type, size_bytes
             FROM topic_attachments WHERE topic_id IN ({placeholders})
             ORDER BY id""",
        topic_ids,
    ).fetchall()
    for row in rows:
        result[int(row["topic_id"])].append(attachment_payload(row))
    return result

def format_day(value: date) -> str:
    months = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return f"{value.day} {months[value.month - 1]}"

def get_question_payload(question_id: int, include_local_feedback: bool = False) -> dict[str, Any] | None:
    db = get_db()
    question = db.execute(
        """
        SELECT q.id, q.text, q.explanation, t.id AS topic_id, t.number AS topic_number,
               t.name AS topic_name, t.color AS topic_color
        FROM questions q
        JOIN topics t ON t.id = q.topic_id
        WHERE q.id = ?
        """,
        (question_id,),
    ).fetchone()
    if not question:
        return None

    options = db.execute(
        "SELECT id, text, position, is_correct FROM options WHERE question_id = ? ORDER BY RANDOM()",
        (question_id,),
    ).fetchall()
    if not options or not any(bool(option["is_correct"]) for option in options):
        return None

    payload: dict[str, Any] = {
        "id": int(question["id"]),
        "text": question["text"],
        "topic": {
            "id": int(question["topic_id"]),
            "number": str(question["topic_number"]),
            "name": question["topic_name"],
            "color": question["topic_color"],
        },
        "options": [
            {"id": int(option["id"]), "text": option["text"], "position": int(option["position"])}
            for option in options
        ],
    }
    if include_local_feedback:
        correct = next(option for option in options if bool(option["is_correct"]))
        payload["correct_option_id"] = int(correct["id"])
        payload["explanation"] = question["explanation"] or None
    return payload

def parse_optional_topic(raw: Any) -> int | None:
    if raw in (None, "", "all"):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError("Tema no válido.")
    if value <= 0:
        raise ValueError("Tema no válido.")
    return value

@router.get("/api/home")
@require_auth
def home_data():
    db = get_db()
    uid = user_id()
    allowed_topics = current_topic_ids()
    question_access, access_params = topic_filter_clause(allowed_topics, "q.topic_id")

    total_answered = db.execute(
        f"""SELECT COUNT(*) FROM attempts a
            JOIN questions q ON q.id = a.question_id
            WHERE a.user_id = ? AND a.outcome != 'skipped' AND {question_access}""",
        [uid, *access_params],
    ).fetchone()[0]
    unique_correct = db.execute(
        f"""SELECT COUNT(DISTINCT a.question_id) FROM attempts a
            JOIN questions q ON q.id = a.question_id
            WHERE a.user_id = ? AND a.outcome = 'correct' AND {question_access}""",
        [uid, *access_params],
    ).fetchone()[0]

    topic_access, topic_access_params = topic_filter_clause(allowed_topics, "t.id")
    topic_rows = db.execute(
        f"""
        SELECT t.id, t.number, t.name, t.color,
               COUNT(DISTINCT q.id) AS total,
               COUNT(DISTINCT CASE WHEN a.outcome != 'skipped' THEN q.id END) AS answered,
               COUNT(DISTINCT CASE WHEN a.outcome = 'correct' THEN q.id END) AS correct
        FROM topics t
        LEFT JOIN questions q ON q.topic_id = t.id
        LEFT JOIN attempts a ON a.question_id = q.id AND a.user_id = ?
        WHERE {topic_access}
        GROUP BY t.id
        """,
        [uid, *topic_access_params],
    ).fetchall()
    topic_rows = sorted(topic_rows, key=lambda row: (topic_sort_key(row["number"]), int(row["id"])))
    attachment_map = attachments_by_topic([int(row["id"]) for row in topic_rows])

    topics = []
    for row in topic_rows:
        total = int(row["total"])
        correct = int(row["correct"])
        topic_id = int(row["id"])
        topics.append(
            {
                **topic_payload(row),
                "total": total,
                "answered": int(row["answered"]),
                "correct": correct,
                "completion": round((correct / total * 100) if total else 0, 1),
                "attachments": attachment_map.get(topic_id, []),
            }
        )

    today = madrid_today()
    current_monday = today - timedelta(days=today.weekday())
    start = current_monday - timedelta(days=21)
    end = start + timedelta(days=27)
    start_utc = madrid_day_bounds(start)[0]
    end_utc = madrid_day_bounds(end)[1]

    counts: dict[str, int] = defaultdict(int)
    activity_rows = db.execute(
        f"""
        SELECT a.created_at
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND a.outcome != 'skipped' AND {question_access}
          AND a.created_at >= ? AND a.created_at < ?
        """,
        [uid, *access_params, start_utc, end_utc],
    ).fetchall()
    for row in activity_rows:
        key = madrid_date_from_utc_iso(row["created_at"]).isoformat()
        counts[key] += 1


    activity = []
    for offset in range(28):
        day = start + timedelta(days=offset)
        activity.append(
            {
                "date": day.isoformat(),
                "label": format_day(day),
                "count": 0 if day > today else counts.get(day.isoformat(), 0),
                "future": day > today,
            }
        )

    return api_ok(
        {
            "user": {
                "display_name": g.current_session["display_name"],
                "username": g.current_session["username"],
            },
            "total_answered": int(total_answered),
            "unique_correct": int(unique_correct),
            "activity": activity,
            "topics": topics,
        }
    )

@router.get("/api/practice/question")
@require_auth
def practice_question():
    raw_topic_ids = str(request.args.get("topic_ids") or "").strip()
    topic_ids: list[int] = []
    if raw_topic_ids:
        try:
            topic_ids = list(dict.fromkeys(int(value) for value in raw_topic_ids.split(",") if value.strip()))
        except (TypeError, ValueError):
            return api_error("La selección de temas no es válida.")
        if not topic_ids or any(value <= 0 for value in topic_ids):
            return api_error("La selección de temas no es válida.")
    else:
        try:
            topic_id = parse_optional_topic(request.args.get("topic_id"))
        except ValueError as exc:
            return api_error(str(exc))
        if topic_id is not None:
            topic_ids = [topic_id]

    mode = request.args.get("mode", "pending")
    if mode not in {"pending", "all"}:
        return api_error("Filtro de preguntas no válido.")

    raw_exclude_ids = str(request.args.get("exclude_ids") or request.args.get("exclude_id") or "").strip()
    exclude_ids: list[int] = []
    if raw_exclude_ids:
        try:
            exclude_ids = list(dict.fromkeys(int(value) for value in raw_exclude_ids.split(",") if value.strip()))
        except (TypeError, ValueError):
            exclude_ids = []

    try:
        count = max(1, min(3, int(request.args.get("count", "1"))))
    except (TypeError, ValueError):
        count = 1

    db = get_db()
    allowed_topics = current_topic_ids()
    if topic_ids:
        if not ensure_topic_access(topic_ids):
            return api_error("Alguno de los temas seleccionados no está disponible.", 404)
        placeholders = ",".join("?" for _ in topic_ids)
        valid_topics = db.execute(
            f"SELECT id FROM topics WHERE id IN ({placeholders})",
            topic_ids,
        ).fetchall()
        if len(valid_topics) != len(topic_ids):
            return api_error("Alguno de los temas seleccionados no está disponible.", 404)
    else:
        topic_ids = allowed_topics

    questions = practice_questions_for_topics(topic_ids, mode, exclude_ids, count)
    if not questions:
        return api_error("No quedan preguntas disponibles con este filtro.", 404, "NO_QUESTIONS")
    if count == 1:
        return api_ok(questions[0])
    return api_ok({"questions": questions})


@router.get("/api/practice/preload")
@require_auth
def practice_preload():
    mode = request.args.get("mode", "pending")
    if mode not in {"pending", "all"}:
        return api_error("Filtro de preguntas no válido.")

    previews = []
    for topic_id in current_topic_ids():
        questions = practice_questions_for_topics([topic_id], mode, [], 1)
        if questions:
            previews.append(questions[0])

    return api_ok({"questions": previews})


def practice_questions_for_topics(
    topic_ids: list[int],
    mode: str,
    exclude_ids: list[int] | None = None,
    count: int = 1,
) -> list[dict[str, Any]]:
    db = get_db()
    params: list[Any] = []
    where = []

    if topic_ids:
        placeholders = ",".join("?" for _ in topic_ids)
        where.append(f"q.topic_id IN ({placeholders})")
        params.extend(topic_ids)

    clean_excludes = [int(value) for value in (exclude_ids or []) if int(value) > 0]
    if clean_excludes:
        placeholders = ",".join("?" for _ in clean_excludes)
        where.append(f"q.id NOT IN ({placeholders})")
        params.extend(clean_excludes)

    if mode == "pending":
        where.append(
            "NOT EXISTS (SELECT 1 FROM attempts a WHERE a.user_id = ? AND a.question_id = q.id AND a.outcome = 'correct')"
        )
        params.append(user_id())

    limit = max(1, min(3, int(count)))
    rows = db.execute(
        f"SELECT q.id FROM questions q JOIN topics t ON t.id = q.topic_id WHERE {' AND '.join(where)} ORDER BY RANDOM() LIMIT ?",
        [*params, limit],
    ).fetchall()

    # If exclusions leave no candidates, allow repetition rather than ending an otherwise valid practice session.
    if not rows and clean_excludes:
        return practice_questions_for_topics(topic_ids, mode, [], limit)

    return [
        payload
        for row in rows
        if (payload := get_question_payload(int(row["id"]), include_local_feedback=True)) is not None
    ]

@router.post("/api/answers")
@require_auth
def submit_practice_answer():
    valid, error = require_csrf()
    if not valid:
        return error
    data = json_body()
    if not data:
        return api_error("Respuesta no válida.")

    try:
        question_id = int(data.get("question_id"))
        option_id = int(data.get("selected_option_id"))
        submission_key = clean_submission_key(data.get("submission_key"), "practice")
    except (TypeError, ValueError) as exc:
        return api_error(str(exc) or "Respuesta no válida.")

    db = get_db()
    allowed_topics = current_topic_ids()
    access_clause, access_params = topic_filter_clause(allowed_topics, "q.topic_id")
    row = db.execute(
        f"""
        SELECT o.id, o.is_correct, q.explanation,
               (SELECT id FROM options WHERE question_id = q.id AND is_correct = 1) AS correct_option_id
        FROM questions q
        JOIN options o ON o.question_id = q.id AND o.id = ?
        WHERE q.id = ? AND {access_clause}
        """,
        [option_id, question_id, *access_params],
    ).fetchone()
    if not row or row["correct_option_id"] is None:
        return api_error("La pregunta o la respuesta ya no están disponibles.", 409)

    correct = bool(row["is_correct"])
    try:
        db.execute(
            """
            INSERT INTO attempts(user_id, question_id, outcome, source, submission_key, created_at)
            VALUES (?, ?, ?, 'practice', ?, ?)
            """,
            (user_id(), question_id, "correct" if correct else "incorrect", submission_key, utc_iso()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        # A technical retry/double click with the same appearance key is harmless.
        existing = db.execute(
            "SELECT question_id, outcome FROM attempts WHERE user_id = ? AND submission_key = ?",
            (user_id(), submission_key),
        ).fetchone()
        if not existing or int(existing["question_id"]) != question_id:
            return api_error("No se ha podido guardar la respuesta.", 409)
        correct = existing["outcome"] == "correct"

    return api_ok({
        "correct": correct,
        "correct_option_id": int(row["correct_option_id"]),
        "explanation": row["explanation"] or None,
    })

