from __future__ import annotations

import secrets
import sqlite3
from collections import defaultdict
from typing import Any

from fastapi import APIRouter

from .auth import api_error, api_ok, clean_submission_key, json_body, require_auth, require_csrf, user_id, utc_iso
from .db import get_db
from .practice import current_topic_ids, ensure_topic_access, get_question_payload, topic_filter_clause

router = APIRouter()

@router.post("/api/simulations")
@require_auth
def create_simulation():
    valid, error = require_csrf()
    if not valid:
        return error
    data = json_body() or {}

    try:
        question_count = int(data.get("question_count", 30))
    except (TypeError, ValueError):
        return api_error("El número de preguntas no es válido.")
    if not 1 <= question_count <= 1000:
        return api_error("El número de preguntas del simulacro no es válido.")

    raw_topic_ids = data.get("topic_ids")
    topic_ids: list[int] = []
    if raw_topic_ids is None and data.get("topic_id") is not None:
        raw_topic_ids = [data.get("topic_id")]
    if raw_topic_ids is not None:
        if not isinstance(raw_topic_ids, list):
            return api_error("La selección de temas no es válida.")
        try:
            topic_ids = list(dict.fromkeys(int(value) for value in raw_topic_ids))
        except (TypeError, ValueError):
            return api_error("La selección de temas no es válida.")
        if any(value <= 0 for value in topic_ids):
            return api_error("La selección de temas no es válida.")

    db = get_db()
    allowed_topics = current_topic_ids()
    if topic_ids:
        if not ensure_topic_access(topic_ids):
            return api_error("Alguno de los temas seleccionados no está disponible.", 404)
        placeholders = ",".join("?" for _ in topic_ids)
        valid_topics = db.execute(
            f"SELECT id FROM topics WHERE id IN ({placeholders})", topic_ids
        ).fetchall()
        if len(valid_topics) != len(topic_ids):
            return api_error("Alguno de los temas seleccionados no está disponible.", 404)
    else:
        topic_ids = allowed_topics

    if not topic_ids:
        return api_error("No hay temas disponibles para el simulacro.", 409, "NOT_ENOUGH_QUESTIONS")
    placeholders = ",".join("?" for _ in topic_ids)
    rows = db.execute(
        f"""
        SELECT q.id FROM questions q
        WHERE q.topic_id IN ({placeholders})
        ORDER BY RANDOM() LIMIT ?
        """,
        [*topic_ids, question_count],
    ).fetchall()
    if len(rows) < question_count:
        return api_error(
            f"Solo hay {len(rows)} preguntas disponibles en los temas seleccionados.",
            409, "NOT_ENOUGH_QUESTIONS",
        )

    questions = [get_question_payload(int(row["id"])) for row in rows]
    if any(question is None for question in questions):
        return api_error("Alguna pregunta no está correctamente configurada.", 409)
    return api_ok({
        "submission_id": secrets.token_urlsafe(18),
        "topic_ids": topic_ids,
        "questions": questions,
    }, 201)

@router.post("/api/simulations/finish")
@require_auth
def finish_simulation():
    valid, error = require_csrf()
    if not valid:
        return error
    data = json_body() or {}
    raw_answers = data.get("answers")
    try:
        submission_id = clean_submission_key(data.get("submission_id"), "simulation")
    except ValueError as exc:
        return api_error(str(exc))
    if not isinstance(raw_answers, list) or not 1 <= len(raw_answers) <= 1000:
        return api_error("Las respuestas del simulacro no son válidas.")

    parsed: list[tuple[int, int | None]] = []
    seen_questions: set[int] = set()
    try:
        for item in raw_answers:
            if not isinstance(item, dict):
                raise ValueError
            question_id = int(item.get("question_id"))
            selected_raw = item.get("selected_option_id")
            selected = int(selected_raw) if selected_raw is not None else None
            if question_id <= 0 or question_id in seen_questions or (selected is not None and selected <= 0):
                raise ValueError
            seen_questions.add(question_id)
            parsed.append((question_id, selected))
    except (TypeError, ValueError):
        return api_error("Las respuestas del simulacro no son válidas.")

    db = get_db()
    allowed_topics = current_topic_ids()
    access_clause, access_params = topic_filter_clause(allowed_topics, "q.topic_id")
    question_ids = [question_id for question_id, _ in parsed]
    placeholders = ",".join("?" for _ in question_ids)
    rows = db.execute(
        f"""
        SELECT q.id AS question_id, q.text, q.explanation, q.topic_id,
               t.number AS topic_number, t.name AS topic_name, t.color AS topic_color,
               co.id AS correct_option_id
        FROM questions q
        JOIN topics t ON t.id = q.topic_id
        JOIN options co ON co.question_id = q.id AND co.is_correct = 1
        WHERE q.id IN ({placeholders}) AND {access_clause}
        """,
        [*question_ids, *access_params],
    ).fetchall()
    by_question = {int(row["question_id"]): row for row in rows}
    if len(by_question) != len(question_ids):
        return api_error("Alguna pregunta del simulacro ya no está disponible.", 409)

    option_rows = db.execute(
        f"SELECT id, question_id, text, position FROM options WHERE question_id IN ({placeholders}) ORDER BY question_id, position",
        question_ids,
    ).fetchall()
    options_by_question: dict[int, list[dict[str, Any]]] = defaultdict(list)
    valid_option_ids: dict[int, set[int]] = defaultdict(set)
    for option in option_rows:
        qid = int(option["question_id"])
        oid = int(option["id"])
        valid_option_ids[qid].add(oid)
        options_by_question[qid].append({"id": oid, "text": option["text"], "position": int(option["position"])})

    correct = incorrect = skipped = 0
    attempts: list[tuple[int, int, str, str, str, str]] = []
    review: list[dict[str, Any]] = []
    now = utc_iso()
    for position, (question_id, selected) in enumerate(parsed, start=1):
        row = by_question[question_id]
        if selected is not None and selected not in valid_option_ids[question_id]:
            return api_error("Una respuesta no pertenece a su pregunta.", 400)
        correct_option_id = int(row["correct_option_id"])
        if selected is None:
            outcome = "skipped"
            skipped += 1
        elif selected == correct_option_id:
            outcome = "correct"
            correct += 1
        else:
            outcome = "incorrect"
            incorrect += 1
        attempts.append((user_id(), question_id, outcome, "simulation", f"{submission_id}:{position}", now))
        review.append({
            "position": position,
            "id": question_id,
            "text": row["text"],
            "explanation": row["explanation"] or None,
            "selected_option_id": selected,
            "correct_option_id": correct_option_id,
            "outcome": outcome,
            "topic": {
                "id": int(row["topic_id"]), "number": str(row["topic_number"]),
                "name": row["topic_name"], "color": row["topic_color"],
            },
            "options": options_by_question[question_id],
        })

    try:
        db.execute("BEGIN IMMEDIATE")
        db.executemany(
            """INSERT INTO attempts(user_id, question_id, outcome, source, submission_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            attempts,
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        # Same finish request retried: do not duplicate the history.
        existing = int(db.execute(
            "SELECT COUNT(*) FROM attempts WHERE user_id = ? AND submission_key LIKE ?",
            (user_id(), f"{submission_id}:%"),
        ).fetchone()[0])
        if existing != len(parsed):
            return api_error("No se ha podido guardar el simulacro.", 409)

    return api_ok({
        "correct": correct, "incorrect": incorrect, "skipped": skipped,
        "total": len(parsed), "review": review,
    })

