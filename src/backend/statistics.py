from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from statistics import pstdev
from typing import Any

from fastapi import APIRouter

from .auth import (
    api_error, api_ok, g, madrid_date_from_utc_iso, madrid_day_bounds, madrid_month_start_utc,
    madrid_today, request, require_auth, user_id,
)
from .db import get_db
from .practice import format_day, topic_ids_for_user, topic_payload, topic_sort_key

router = APIRouter()

def stats_user_ids() -> tuple[list[int], dict[str, Any]]:
    """Resolve the requested statistics scope and enforce admin-only scopes."""
    scope = str(request.args.get("scope") or "self").strip().lower()
    db = get_db()
    current_uid = user_id()

    if scope == "self":
        return [current_uid], {
            "scope": "self",
            "user_id": current_uid,
            "is_student": g.current_session["role"] == "user",
        }

    if g.current_session["role"] != "admin":
        raise PermissionError("No tienes permisos para consultar estas estadísticas.")

    if scope == "student":
        try:
            target_uid = int(request.args.get("user_id") or 0)
        except (TypeError, ValueError):
            target_uid = 0
        row = db.execute(
            "SELECT id, username, display_name, role, is_active FROM users WHERE id = ? AND role = 'user'",
            (target_uid,),
        ).fetchone()
        if not row:
            raise LookupError("Alumno no encontrado.")
        return [int(row["id"])], {
            "scope": "student",
            "user_id": int(row["id"]),
            "is_student": True,
            "user": {
                "id": int(row["id"]),
                "username": row["username"],
                "display_name": row["display_name"],
                "is_active": bool(row["is_active"]),
            },
        }

    if scope == "all":
        rows = db.execute("SELECT id FROM users WHERE role = 'user' ORDER BY id").fetchall()
        return [int(row["id"]) for row in rows], {
            "scope": "all",
            "user_id": None,
            "is_student": False,
        }

    raise ValueError("El ámbito de estadísticas no es válido.")

def ids_clause(user_ids: list[int], column: str = "a.user_id") -> tuple[str, list[Any]]:
    if not user_ids:
        return "1 = 0", []
    placeholders = ",".join("?" for _ in user_ids)
    return f"{column} IN ({placeholders})", list(user_ids)

def stats_topics_clause(topic_ids: list[int] | None, column: str = "q.topic_id") -> tuple[str, list[Any]]:
    """Optional topic restriction for statistics. None means unrestricted; [] means no visible topics."""
    if topic_ids is None:
        return "", []
    if not topic_ids:
        return " AND 1 = 0", []
    placeholders = ",".join("?" for _ in topic_ids)
    return f" AND {column} IN ({placeholders})", list(topic_ids)

def answered_rows_for_users(
    user_ids: list[int], topic_id: int | None = None, allowed_topic_ids: list[int] | None = None
) -> list[sqlite3.Row]:
    db = get_db()
    user_clause, params = ids_clause(user_ids)
    allowed_clause, allowed_params = stats_topics_clause(allowed_topic_ids)
    params.extend(allowed_params)
    topic_clause = ""
    if topic_id is not None:
        if allowed_topic_ids is not None and topic_id not in set(allowed_topic_ids):
            return []
        topic_clause = " AND q.topic_id = ?"
        params.append(topic_id)
    return db.execute(
        f"""
        SELECT a.question_id, q.topic_id, a.outcome, a.created_at
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        WHERE {user_clause} AND a.outcome != 'skipped' {allowed_clause} {topic_clause}
        ORDER BY a.created_at, a.id
        """,
        params,
    ).fetchall()

def moving_accuracy(rows: list[sqlite3.Row], window: int = 30) -> list[dict[str, Any]]:
    if len(rows) < window:
        return []
    binary = [1 if row["outcome"] == "correct" else 0 for row in rows]
    series: list[dict[str, Any]] = []
    running = sum(binary[:window])
    for index in range(window - 1, len(rows)):
        if index >= window:
            running += binary[index] - binary[index - window]
        dt = madrid_date_from_utc_iso(rows[index]["created_at"])
        series.append({"label": format_day(dt), "value": round(running / window * 100, 1)})

    if len(series) <= 120:
        return series
    step = max(1, len(series) // 119)
    sampled = series[::step]
    if sampled[-1] != series[-1]:
        sampled.append(series[-1])
    return sampled[-120:]

def progress_series_from_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    correct_rows = [row for row in rows if row["outcome"] == "correct"]
    if not correct_rows:
        return []
    counts: dict[date, int] = defaultdict(int)
    for row in correct_rows:
        counts[madrid_date_from_utc_iso(row["created_at"])] += 1
    first = min(counts)
    today = madrid_today()
    start_day = max(first, today - timedelta(days=119))
    cumulative = sum(count for day, count in counts.items() if day < start_day)
    result: list[dict[str, Any]] = []
    cursor = start_day
    while cursor <= today:
        cumulative += counts.get(cursor, 0)
        result.append({"label": format_day(cursor), "value": cumulative})
        cursor += timedelta(days=1)
    return result

def progress_series_for_users(
    user_ids: list[int], topic_id: int | None = None, allowed_topic_ids: list[int] | None = None
) -> list[dict[str, Any]]:
    """Cumulative correct attempts over time, grouped by Europe/Madrid calendar day."""
    db = get_db()
    user_clause, params = ids_clause(user_ids)
    allowed_clause, allowed_params = stats_topics_clause(allowed_topic_ids)
    params.extend(allowed_params)
    topic_clause = ""
    if topic_id is not None:
        if allowed_topic_ids is not None and topic_id not in set(allowed_topic_ids):
            return []
        topic_clause = " AND q.topic_id = ?"
        params.append(topic_id)
    rows = db.execute(
        f"""
        SELECT a.created_at
        FROM attempts a JOIN questions q ON q.id = a.question_id
        WHERE {user_clause} AND a.outcome = 'correct' {allowed_clause} {topic_clause}
        ORDER BY a.created_at, a.id
        """,
        params,
    ).fetchall()
    if not rows:
        return []

    counts: dict[date, int] = defaultdict(int)
    for row in rows:
        counts[madrid_date_from_utc_iso(row["created_at"])] += 1
    first = min(counts)
    today = madrid_today()
    start_day = max(first, today - timedelta(days=119))
    cumulative = sum(count for day, count in counts.items() if day < start_day)
    series: list[dict[str, Any]] = []
    cursor = start_day
    while cursor <= today:
        cumulative += counts.get(cursor, 0)
        series.append({"label": format_day(cursor), "value": cumulative})
        cursor += timedelta(days=1)
    return series

def recent_accuracy_for_user(uid: int, window: int = 30, allowed_topic_ids: list[int] | None = None) -> float | None:
    topic_clause, topic_params = stats_topics_clause(allowed_topic_ids)
    rows = get_db().execute(
        f"""
        SELECT a.outcome
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND a.outcome != 'skipped' {topic_clause}
        ORDER BY a.created_at DESC, a.id DESC
        LIMIT ?
        """,
        [uid, *topic_params, window],
    ).fetchall()
    if not rows:
        return None
    correct = sum(1 for row in rows if row["outcome"] == "correct")
    return correct / len(rows) * 100

def student_topic_distributions(topic_ids: list[int], student_ids: list[int]) -> dict[int, dict[str, Any]]:
    empty = {
        "average_answered": 0, "answered_std": 0,
        "average_accuracy": 0, "accuracy_std": 0,
        "average_unique_answered": 0, "average_unique_correct": 0,
        "students_with_activity": 0,
    }
    result = {int(topic_id): dict(empty) for topic_id in topic_ids}
    if not topic_ids or not student_ids:
        return result

    topic_ph = ",".join("?" for _ in topic_ids)
    user_ph = ",".join("?" for _ in student_ids)
    assigned_rows = get_db().execute(
        f"SELECT topic_id, user_id FROM user_topics WHERE topic_id IN ({topic_ph}) AND user_id IN ({user_ph})",
        [*topic_ids, *student_ids],
    ).fetchall()
    assigned: dict[int, list[int]] = defaultdict(list)
    for row in assigned_rows:
        assigned[int(row["topic_id"])].append(int(row["user_id"]))

    metric_rows = get_db().execute(
        f"""
        SELECT q.topic_id, a.user_id,
               COUNT(*) AS answered,
               SUM(CASE WHEN a.outcome = 'correct' THEN 1 ELSE 0 END) AS correct,
               COUNT(DISTINCT a.question_id) AS unique_answered,
               COUNT(DISTINCT CASE WHEN a.outcome = 'correct' THEN a.question_id END) AS unique_correct
        FROM attempts a JOIN questions q ON q.id = a.question_id
        WHERE q.topic_id IN ({topic_ph}) AND a.user_id IN ({user_ph}) AND a.outcome != 'skipped'
        GROUP BY q.topic_id, a.user_id
        """,
        [*topic_ids, *student_ids],
    ).fetchall()
    metrics = {(int(row["topic_id"]), int(row["user_id"])): row for row in metric_rows}

    for topic_id in topic_ids:
        users = assigned.get(int(topic_id), [])
        if not users:
            continue
        answered_values: list[int] = []
        unique_answered_values: list[int] = []
        unique_correct_values: list[int] = []
        accuracies: list[float] = []
        for uid in users:
            row = metrics.get((int(topic_id), uid))
            answered = int(row["answered"] or 0) if row else 0
            correct = int(row["correct"] or 0) if row else 0
            answered_values.append(answered)
            unique_answered_values.append(int(row["unique_answered"] or 0) if row else 0)
            unique_correct_values.append(int(row["unique_correct"] or 0) if row else 0)
            if answered:
                accuracies.append(correct / answered * 100)
        result[int(topic_id)] = {
            "average_answered": round(sum(answered_values) / len(users), 1),
            "answered_std": round(pstdev(answered_values), 1) if len(answered_values) > 1 else 0,
            "average_accuracy": round(sum(accuracies) / len(accuracies), 1) if accuracies else 0,
            "accuracy_std": round(pstdev(accuracies), 1) if len(accuracies) > 1 else 0,
            "average_unique_answered": round(sum(unique_answered_values) / len(users), 1),
            "average_unique_correct": round(sum(unique_correct_values) / len(users), 1),
            "students_with_activity": len(accuracies),
        }
    return result

def activity_for_users(user_ids: list[int], allowed_topic_ids: list[int] | None = None) -> list[dict[str, Any]]:
    """Four complete Monday-Sunday weeks in the Europe/Madrid calendar."""
    today = madrid_today()
    current_monday = today - timedelta(days=today.weekday())
    start = current_monday - timedelta(days=21)
    end = start + timedelta(days=27)
    start_utc = madrid_day_bounds(start)[0]
    end_utc = madrid_day_bounds(end)[1]
    user_clause, params = ids_clause(user_ids, "a.user_id")
    topic_clause, topic_params = stats_topics_clause(allowed_topic_ids)
    rows = get_db().execute(
        f"""
        SELECT a.created_at
        FROM attempts a JOIN questions q ON q.id = a.question_id
        WHERE {user_clause} AND a.outcome != 'skipped' {topic_clause}
          AND a.created_at >= ? AND a.created_at < ?
        """,
        [*params, *topic_params, start_utc, end_utc],
    ).fetchall()
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[madrid_date_from_utc_iso(row["created_at"]).isoformat()] += 1
    return [
        {
            "date": (start + timedelta(days=offset)).isoformat(),
            "label": format_day(start + timedelta(days=offset)),
            "count": 0 if start + timedelta(days=offset) > today else counts.get((start + timedelta(days=offset)).isoformat(), 0),
            "future": start + timedelta(days=offset) > today,
        }
        for offset in range(28)
    ]

def cohort_summary(user_ids: list[int]) -> dict[str, Any]:
    db = get_db()
    if not user_ids:
        return {
            "total_students": 0, "active_students": 0, "students_with_activity": 0,
            "bank_questions": 0, "unique_questions_correct": 0, "coverage": 0,
            "avg_answered_per_student": 0, "avg_correct_per_student": 0,
            "avg_accuracy_per_student": 0, "avg_recent_accuracy_30": 0,
        }

    user_placeholders = ",".join("?" for _ in user_ids)
    total_students = len(user_ids)
    active_students = int(db.execute(
        f"SELECT COUNT(*) FROM users WHERE id IN ({user_placeholders}) AND is_active = 1",
        user_ids,
    ).fetchone()[0])
    bank_questions = int(db.execute("SELECT COUNT(*) FROM questions").fetchone()[0])
    unique_questions_correct = int(db.execute(
        f"SELECT COUNT(DISTINCT question_id) FROM attempts WHERE user_id IN ({user_placeholders}) AND outcome = 'correct'",
        user_ids,
    ).fetchone()[0])

    rows = db.execute(
        f"""
        SELECT u.id,
               SUM(CASE WHEN a.outcome != 'skipped' THEN 1 ELSE 0 END) AS answered,
               SUM(CASE WHEN a.outcome = 'correct' THEN 1 ELSE 0 END) AS correct
        FROM users u
        LEFT JOIN attempts a ON a.user_id = u.id
        WHERE u.id IN ({user_placeholders})
        GROUP BY u.id
        """,
        user_ids,
    ).fetchall()

    answered_values = [int(row["answered"] or 0) for row in rows]
    correct_values = [int(row["correct"] or 0) for row in rows]
    active_accuracy_values = [
        correct / answered * 100
        for answered, correct in zip(answered_values, correct_values)
        if answered > 0
    ]
    recent_rows = db.execute(
        f"""
        WITH ranked AS (
            SELECT user_id, outcome,
                   ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC, id DESC) AS rn
            FROM attempts
            WHERE user_id IN ({user_placeholders}) AND outcome != 'skipped'
        )
        SELECT user_id, COUNT(*) AS answered,
               SUM(CASE WHEN outcome = 'correct' THEN 1 ELSE 0 END) AS correct
        FROM ranked
        WHERE rn <= 30
        GROUP BY user_id
        """,
        user_ids,
    ).fetchall()
    recent_values = [
        int(row["correct"] or 0) / int(row["answered"]) * 100
        for row in recent_rows
        if int(row["answered"] or 0) > 0
    ]
    students_with_activity = sum(1 for value in answered_values if value > 0)

    return {
        "total_students": total_students,
        "active_students": active_students,
        "students_with_activity": students_with_activity,
        "bank_questions": bank_questions,
        "unique_questions_correct": unique_questions_correct,
        "coverage": round((unique_questions_correct / bank_questions * 100) if bank_questions else 0, 1),
        "avg_answered_per_student": round(sum(answered_values) / total_students, 1),
        "avg_correct_per_student": round(sum(correct_values) / total_students, 1),
        "avg_accuracy_per_student": round(sum(active_accuracy_values) / len(active_accuracy_values), 1) if active_accuracy_values else 0,
        "avg_recent_accuracy_30": round(sum(recent_values) / len(recent_values), 1) if recent_values else 0,
    }

def streaks_for_users(user_ids: list[int], allowed_topic_ids: list[int] | None = None) -> tuple[int, int]:
    user_clause, params = ids_clause(user_ids, "a.user_id")
    topic_clause, topic_params = stats_topics_clause(allowed_topic_ids)
    rows = get_db().execute(
        f"""
        SELECT a.created_at
        FROM attempts a JOIN questions q ON q.id = a.question_id
        WHERE {user_clause} AND a.outcome != 'skipped' {topic_clause}
        ORDER BY a.created_at, a.id
        """,
        [*params, *topic_params],
    ).fetchall()
    days = sorted({madrid_date_from_utc_iso(row["created_at"]) for row in rows})
    if not days:
        return 0, 0
    best = run = 1
    for previous, current in zip(days, days[1:]):
        if current == previous + timedelta(days=1):
            run += 1
            best = max(best, run)
        else:
            run = 1
    today = madrid_today()
    if days[-1] != today:
        return 0, best
    current = 1
    for index in range(len(days) - 1, 0, -1):
        if days[index - 1] == days[index] - timedelta(days=1):
            current += 1
        else:
            break
    return current, best

@router.get("/api/statistics")
@require_auth
def statistics_data():
    db = get_db()
    try:
        user_ids, subject = stats_user_ids()
    except PermissionError as exc:
        return api_error(str(exc), 403, "FORBIDDEN")
    except LookupError as exc:
        return api_error(str(exc), 404)
    except ValueError as exc:
        return api_error(str(exc))

    # When the subject is one student, revoked topics disappear from every statistic,
    # including historical attempts. Administrators keep an unrestricted cohort view.
    visible_topic_ids: list[int] | None = None
    if len(user_ids) == 1 and subject.get("is_student"):
        visible_topic_ids = topic_ids_for_user(user_ids[0], "user")

    all_student_ids = [int(row["id"]) for row in db.execute("SELECT id FROM users WHERE role = 'user' ORDER BY id").fetchall()]
    user_clause, user_params = ids_clause(user_ids)
    visible_clause, visible_params = stats_topics_clause(visible_topic_ids)
    total_answered = int(db.execute(
        f"""SELECT COUNT(*) FROM attempts a JOIN questions q ON q.id = a.question_id
             WHERE {user_clause} AND a.outcome != 'skipped' {visible_clause}""",
        [*user_params, *visible_params],
    ).fetchone()[0])
    correct_attempts = int(db.execute(
        f"""SELECT COUNT(*) FROM attempts a JOIN questions q ON q.id = a.question_id
             WHERE {user_clause} AND a.outcome = 'correct' {visible_clause}""",
        [*user_params, *visible_params],
    ).fetchone()[0])
    accuracy = round((correct_attempts / total_answered * 100) if total_answered else 0, 1)
    current_month = madrid_month_start_utc()
    answered_this_month = int(db.execute(
        f"""SELECT COUNT(*) FROM attempts a JOIN questions q ON q.id = a.question_id
            WHERE {user_clause} AND a.outcome != 'skipped' {visible_clause}
              AND a.created_at >= ?""",
        [*user_params, *visible_params, current_month],
    ).fetchone()[0])
    current_streak, best_streak = streaks_for_users(user_ids, visible_topic_ids)

    if visible_topic_ids is None:
        topics_rows = db.execute("SELECT id, number, name, color FROM topics").fetchall()
    elif visible_topic_ids:
        placeholders = ",".join("?" for _ in visible_topic_ids)
        topics_rows = db.execute(
            f"SELECT id, number, name, color FROM topics WHERE id IN ({placeholders})",
            visible_topic_ids,
        ).fetchall()
    else:
        topics_rows = []
    topics_rows = sorted(topics_rows, key=lambda row: (topic_sort_key(row["number"]), int(row["id"])))
    topics = [topic_payload(row) for row in topics_rows]

    topic_ids = [int(topic["id"]) for topic in topics]
    distributions = student_topic_distributions(topic_ids, all_student_ids)
    metric_map: dict[int, sqlite3.Row] = {}
    if topic_ids:
        topic_ph = ",".join("?" for _ in topic_ids)
        user_ph = ",".join("?" for _ in user_ids)
        metric_rows = db.execute(
            f"""
            SELECT t.id AS topic_id,
                   COUNT(DISTINCT q.id) AS total,
                   COUNT(DISTINCT CASE WHEN a.outcome = 'correct' THEN a.question_id END) AS unique_correct,
                   COUNT(DISTINCT CASE WHEN a.outcome != 'skipped' THEN a.question_id END) AS unique_answered,
                   SUM(CASE WHEN a.outcome != 'skipped' THEN 1 ELSE 0 END) AS answered,
                   SUM(CASE WHEN a.outcome = 'correct' THEN 1 ELSE 0 END) AS correct
            FROM topics t
            LEFT JOIN questions q ON q.topic_id = t.id
            LEFT JOIN attempts a ON a.question_id = q.id AND a.user_id IN ({user_ph})
            WHERE t.id IN ({topic_ph})
            GROUP BY t.id
            """,
            [*user_ids, *topic_ids],
        ).fetchall()
        metric_map = {int(row["topic_id"]): row for row in metric_rows}

    bar = []
    for topic in topics:
        metrics = metric_map.get(int(topic["id"]))
        total = int(metrics["total"] or 0) if metrics else 0
        unique_correct = int(metrics["unique_correct"] or 0) if metrics else 0
        unique_answered = int(metrics["unique_answered"] or 0) if metrics else 0
        topic_answered = int(metrics["answered"] or 0) if metrics else 0
        topic_correct = int(metrics["correct"] or 0) if metrics else 0
        # Current-bank coverage can never exceed the current number of questions.
        unique_correct = min(unique_correct, total)
        unique_answered = min(unique_answered, total)
        topic_accuracy = round((topic_correct / topic_answered * 100) if topic_answered else 0, 1)
        distribution = distributions.get(int(topic["id"]), {})
        bar.append({
            **topic,
            "value": unique_correct,
            "unique_answered": unique_answered,
            "total": total,
            "accuracy": topic_accuracy,
            "correct_attempts": topic_correct,
            "answered": topic_answered,
            "average_answered": distribution.get("average_answered", 0),
            "answered_std": distribution.get("answered_std", 0),
            "average_accuracy": distribution.get("average_accuracy", 0),
            "accuracy_std": distribution.get("accuracy_std", 0),
            "reference_avg_unique_answered": distribution.get("average_unique_answered", 0),
            "reference_avg_unique_correct": distribution.get("average_unique_correct", 0),
            "reference_avg_accuracy": distribution.get("average_accuracy", 0),
            "students_with_activity": distribution.get("students_with_activity", 0),
        })

    is_all = subject.get("scope") == "all"
    winrate_window = 120 if is_all else 30
    all_rows = answered_rows_for_users(user_ids, allowed_topic_ids=visible_topic_ids)
    all_winrate = moving_accuracy(all_rows, winrate_window)
    recent_accuracy = all_winrate[-1]["value"] if all_winrate else accuracy

    rows_by_topic: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in all_rows:
        rows_by_topic[int(row["topic_id"])].append(row)

    progress: dict[str, list[dict[str, Any]]] = {}
    if not is_all:
        progress["all"] = progress_series_from_rows(all_rows)
    winrate: dict[str, list[dict[str, Any]]] = {"all": all_winrate}
    for topic in topics:
        key = str(topic["id"])
        topic_rows = rows_by_topic.get(int(topic["id"]), [])
        if not is_all:
            progress[key] = progress_series_from_rows(topic_rows)
        winrate[key] = moving_accuracy(topic_rows, winrate_window)

    return api_ok({
        "subject": subject,
        "topics": topics,
        "kpis": {
            "total_answered": total_answered,
            "answered_this_month": answered_this_month,
            "correct_attempts": correct_attempts,
            "accuracy": accuracy,
            "current_streak": current_streak,
            "best_streak": best_streak,
            "recent_accuracy": recent_accuracy,
        },
        "cohort": cohort_summary(user_ids) if is_all else None,
        "bar": bar,
        "progress": progress,
        "winrate": winrate,
        "winrate_window": winrate_window,
        "activity": activity_for_users(user_ids, visible_topic_ids) if is_all else [],
    })

