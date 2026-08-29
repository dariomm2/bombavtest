from __future__ import annotations

import mimetypes
import os
import re
import secrets
import sqlite3
import unicodedata
import uuid
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, UploadFile

from .auth import (
    api_error, api_ok, json_body, password_digest, request, require_admin, require_auth,
    require_csrf, user_id, utc_iso, utc_now,
)
from .config import MAX_ATTACHMENT_BYTES, MAX_ATTACHMENTS_PER_UPLOAD
from .db import get_db
from .practice import attachment_payload, attachments_by_topic, current_topic_ids, topic_sort_key
from .storage import delete_file as s3_delete_file
from .storage import download_response as s3_download_response
from .storage import upload_file as s3_upload_file

router = APIRouter()


def storage_put(file_storage: UploadFile, key: str, mime_type: str) -> None:
    try:
        s3_upload_file(file_storage, key, mime_type)
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError("No se ha podido guardar el archivo.") from exc


def storage_delete(key: str) -> None:
    try:
        s3_delete_file(key)
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError("No se ha podido eliminar el archivo.") from exc


def storage_response(key: str, filename: str, mime_type: str):
    try:
        return s3_download_response(key, filename, mime_type)
    except FileNotFoundError:
        return api_error("El archivo ya no está disponible.", 404)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("No se ha podido descargar el archivo.") from exc


def attachment_draft_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": row["original_name"],
        "mime_type": row["mime_type"] or "application/octet-stream",
        "size_bytes": int(row["size_bytes"]),
        "download_url": f"/api/admin/topic-attachment-drafts/{int(row['id'])}/download",
        "is_draft": True,
    }

def clean_attachment_draft_ids(raw: Any) -> list[int]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise ValueError("Los adjuntos temporales no son válidos.")
    result: list[int] = []
    for value in raw:
        try:
            item = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Los adjuntos temporales no son válidos.") from exc
        if item <= 0 or item in result:
            continue
        result.append(item)
        if len(result) > 50:
            raise ValueError("Hay demasiados adjuntos pendientes.")
    return result

def claim_attachment_drafts(db: sqlite3.Connection, topic_id: int, draft_ids: list[int], owner_id: int) -> None:
    if not draft_ids:
        return
    placeholders = ",".join("?" for _ in draft_ids)
    rows = db.execute(
        f"""SELECT id, original_name, storage_key, mime_type, size_bytes, created_at
               FROM topic_attachment_drafts
              WHERE created_by = ? AND id IN ({placeholders})
              ORDER BY id""",
        [owner_id, *draft_ids],
    ).fetchall()
    if len(rows) != len(draft_ids):
        raise ValueError("Algún adjunto temporal ya no está disponible.")
    for row in rows:
        db.execute(
            """INSERT INTO topic_attachments(topic_id, original_name, storage_key, mime_type, size_bytes, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (topic_id, row["original_name"], row["storage_key"], row["mime_type"], row["size_bytes"], row["created_at"]),
        )
    db.execute(
        f"DELETE FROM topic_attachment_drafts WHERE created_by = ? AND id IN ({placeholders})",
        [owner_id, *draft_ids],
    )

def cleanup_stale_attachment_drafts() -> None:
    db = get_db()
    cutoff = utc_iso(utc_now() - timedelta(hours=24))
    rows = db.execute(
        "SELECT id, storage_key FROM topic_attachment_drafts WHERE created_at < ?",
        (cutoff,),
    ).fetchall()
    if not rows:
        return
    ids = [int(row["id"]) for row in rows]
    placeholders = ",".join("?" for _ in ids)
    db.execute(f"DELETE FROM topic_attachment_drafts WHERE id IN ({placeholders})", ids)
    db.commit()
    for row in rows:
        try:
            storage_delete(str(row["storage_key"]))
        except Exception:
            pass

def clean_topic_number(value: Any) -> str:
    number = str(value or "").strip()
    if not number:
        raise ValueError("El número del tema es obligatorio.")
    if len(number) > 32:
        raise ValueError("El número del tema no puede superar 32 caracteres.")
    if any(ord(char) < 32 for char in number):
        raise ValueError("El número del tema no es válido.")
    return number

def clean_attachment_name(value: str) -> str:
    normalized = str(value or "").replace("\\", "/")
    name = Path(normalized).name.strip()
    name = "".join(char for char in name if ord(char) >= 32 and char not in {"\x7f"})
    if not name:
        raise ValueError("El archivo no tiene un nombre válido.")
    return name[:180]

def attachment_size(file_storage: Any) -> int:
    stream = file_storage.file
    current = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = int(stream.tell())
    stream.seek(current)
    return size

def storage_key_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower()[:16]
    return f"topics/{uuid.uuid4().hex}{suffix}"

def admin_csrf_error():
    valid, error = require_csrf()
    return None if valid else error

def clean_required_text(value: Any, label: str, max_length: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} es obligatorio.")
    if len(text) > max_length:
        raise ValueError(f"{label} es demasiado largo.")
    return text

def clean_topic_color(value: Any) -> str:
    color = str(value or "").strip()
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        raise ValueError("El color del tema no es válido.")
    return color.lower()

def clean_user_topic_ids(raw: Any, role: str) -> list[int]:
    if role == "admin":
        return []
    if not isinstance(raw, list):
        raise ValueError("Selecciona los temas disponibles para el usuario.")
    try:
        topic_ids = list(dict.fromkeys(int(value) for value in raw))
    except (TypeError, ValueError):
        raise ValueError("La selección de temas no es válida.")
    if not topic_ids or any(value <= 0 for value in topic_ids):
        raise ValueError("Selecciona al menos un tema para el usuario.")
    placeholders = ",".join("?" for _ in topic_ids)
    valid = get_db().execute(
        f"SELECT id FROM topics WHERE id IN ({placeholders})",
        topic_ids,
    ).fetchall()
    if len(valid) != len(topic_ids):
        raise ValueError("Alguno de los temas seleccionados no está disponible.")
    return topic_ids

def clean_username(value: Any) -> str:
    username = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,50}", username):
        raise ValueError("El usuario debe tener entre 3 y 50 caracteres y usar solo letras, números, punto, guion o guion bajo.")
    return username

def new_password_values(password: str) -> tuple[str, str]:
    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    if len(password) > 256:
        raise ValueError("La contraseña no puede superar 256 caracteres.")
    if not any(char.isupper() for char in password):
        raise ValueError("La contraseña debe incluir al menos una mayúscula.")
    if not any(char.isdigit() for char in password):
        raise ValueError("La contraseña debe incluir al menos un número.")
    salt = secrets.token_bytes(16).hex()
    return salt, password_digest(password, salt)

def username_base_from_name(display_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", display_name)
    ascii_name = "".join(char for char in normalized if not unicodedata.combining(char))
    words = re.findall(r"[A-Za-z0-9]+", ascii_name.lower())
    base = ".".join(words) or "usuario"
    base = base[:50].strip(".")
    if len(base) < 3:
        base = (base + ".usuario")[:50].strip(".")
    return base

def username_is_available(username: str, exclude_id: int | None = None) -> bool:
    params: list[Any] = [username]
    clause = ""
    if exclude_id is not None:
        clause = " AND id != ?"
        params.append(exclude_id)
    row = get_db().execute(
        f"SELECT 1 FROM users WHERE username = ? COLLATE NOCASE{clause} LIMIT 1", params
    ).fetchone()
    return row is None

def suggest_username(display_name: str, exclude_id: int | None = None) -> str:
    base = username_base_from_name(display_name)
    stem = base[:48].rstrip("._-") or "usuario"
    for suffix in range(1, 100):
        candidate = f"{stem}{suffix:02d}"
        if username_is_available(candidate, exclude_id):
            return candidate
    raise ValueError("No se ha podido generar un nombre de usuario disponible.")

def active_admins_excluding(uid: int) -> int:
    return int(
        get_db().execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1 AND id != ?",
            (uid,),
        ).fetchone()[0]
    )

def validate_question_input(data: dict[str, Any]) -> tuple[int, str, str | None, list[dict[str, Any]]]:
    try:
        topic_id = int(data.get("topic_id"))
    except (TypeError, ValueError):
        raise ValueError("Selecciona un tema válido.")

    topic = get_db().execute(
        "SELECT id FROM topics WHERE id = ?", (topic_id,)
    ).fetchone()
    if not topic:
        raise ValueError("El tema seleccionado no existe.")

    text = clean_required_text(data.get("text"), "La pregunta", 2000)
    explanation_raw = str(data.get("explanation") or "").strip()
    if len(explanation_raw) > 4000:
        raise ValueError("La explicación no puede superar 4000 caracteres.")
    explanation = explanation_raw or None
    raw_options = data.get("options")
    if not isinstance(raw_options, list) or not 2 <= len(raw_options) <= 10:
        raise ValueError("La pregunta debe tener entre 2 y 10 respuestas.")

    options: list[dict[str, Any]] = []
    seen_option_ids: set[int] = set()
    for index, item in enumerate(raw_options):
        if not isinstance(item, dict):
            raise ValueError("Las respuestas no son válidas.")
        option_text = clean_required_text(item.get("text"), "Cada respuesta", 1000)
        option_id = None
        if item.get("id") not in (None, ""):
            try:
                option_id = int(item.get("id"))
            except (TypeError, ValueError):
                raise ValueError("Las respuestas no son válidas.")
            if option_id <= 0 or option_id in seen_option_ids:
                raise ValueError("Las respuestas no son válidas.")
            seen_option_ids.add(option_id)
        options.append({"id": option_id, "text": option_text, "is_correct": index == 0})

    # The editor contract is intentionally simple: first answer correct, all the rest incorrect.
    if len(options) < 2:
        raise ValueError("La pregunta debe tener al menos una respuesta incorrecta.")
    return topic_id, text, explanation, options

@router.get("/api/admin/topics")
@require_admin
def admin_topics_list():
    rows = get_db().execute(
        """
        SELECT t.id, t.number, t.name, t.color, t.created_at,
               COUNT(q.id) AS question_count
        FROM topics t
        LEFT JOIN questions q ON q.topic_id = t.id
        GROUP BY t.id
        """
    ).fetchall()
    rows = sorted(rows, key=lambda row: (topic_sort_key(row["number"]), int(row["id"])))
    attachment_map = attachments_by_topic([int(row["id"]) for row in rows])
    return api_ok([
        {
            "id": int(row["id"]),
            "number": str(row["number"]),
            "name": row["name"],
            "color": row["color"],
            "created_at": row["created_at"],
            "question_count": int(row["question_count"]),
            "attachments": attachment_map.get(int(row["id"]), []),
        }
        for row in rows
    ])

@router.post("/api/admin/topics")
@require_admin
def admin_topic_create():
    error = admin_csrf_error()
    if error:
        return error
    data = json_body() or {}
    try:
        number = clean_topic_number(data.get("number"))
        name = clean_required_text(data.get("name"), "El nombre", 160)
        color = clean_topic_color(data.get("color"))
        draft_ids = clean_attachment_draft_ids(data.get("attachment_draft_ids"))
    except ValueError as exc:
        return api_error(str(exc))

    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO topics(number, name, color, created_at) VALUES (?, ?, ?, ?)",
            (number, name, color, utc_iso()),
        )
        topic_id = int(cursor.lastrowid)
        claim_attachment_drafts(db, topic_id, draft_ids, user_id())
        db.commit()
    except ValueError as exc:
        db.rollback()
        return api_error(str(exc), 409)
    except sqlite3.IntegrityError:
        db.rollback()
        return api_error("Ya existe un tema con ese número.", 409)
    return api_ok({"id": topic_id}, 201)

@router.put("/api/admin/topics/{topic_id}")
@require_admin
def admin_topic_update(topic_id: int):
    error = admin_csrf_error()
    if error:
        return error
    data = json_body() or {}
    try:
        number = clean_topic_number(data.get("number"))
        name = clean_required_text(data.get("name"), "El nombre", 160)
        color = clean_topic_color(data.get("color"))
        draft_ids = clean_attachment_draft_ids(data.get("attachment_draft_ids"))
    except ValueError as exc:
        return api_error(str(exc))

    db = get_db()
    if not db.execute("SELECT id FROM topics WHERE id = ?", (topic_id,)).fetchone():
        return api_error("Tema no encontrado.", 404)
    try:
        db.execute(
            "UPDATE topics SET number = ?, name = ?, color = ? WHERE id = ?",
            (number, name, color, topic_id),
        )
        claim_attachment_drafts(db, topic_id, draft_ids, user_id())
        db.commit()
    except ValueError as exc:
        db.rollback()
        return api_error(str(exc), 409)
    except sqlite3.IntegrityError:
        db.rollback()
        return api_error("Ya existe un tema con ese número.", 409)
    return api_ok({"id": topic_id})

@router.post("/api/admin/topic-attachment-drafts")
@require_admin
def admin_topic_attachment_draft_upload(file: UploadFile = File(...)):
    error = admin_csrf_error()
    if error:
        return error
    cleanup_stale_attachment_drafts()
    if not file or not file.filename:
        return api_error("Selecciona un archivo.")
    try:
        name = clean_attachment_name(file.filename)
        size = attachment_size(file)
        if size <= 0:
            raise ValueError(f"El archivo «{name}» está vacío.")
        if size > MAX_ATTACHMENT_BYTES:
            raise ValueError(f"El archivo «{name}» supera el máximo de 100 MB.")
        mime = str(file.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream")
    except ValueError as exc:
        return api_error(str(exc))

    key = storage_key_for(name)
    try:
        storage_put(file, key, mime)
    except RuntimeError as exc:
        return api_error(str(exc), 503)

    db = get_db()
    try:
        cursor = db.execute(
            """INSERT INTO topic_attachment_drafts(created_by, original_name, storage_key, mime_type, size_bytes, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id(), name, key, mime, size, utc_iso()),
        )
        draft_id = int(cursor.lastrowid)
        db.commit()
    except Exception:
        db.rollback()
        try:
            storage_delete(key)
        except Exception:
            pass
        raise
    row = db.execute(
        "SELECT id, original_name, mime_type, size_bytes FROM topic_attachment_drafts WHERE id = ?",
        (draft_id,),
    ).fetchone()
    return api_ok(attachment_draft_payload(row), 201)

@router.get("/api/admin/topic-attachment-drafts/{draft_id}/download")
@require_admin
def admin_topic_attachment_draft_download(draft_id: int):
    row = get_db().execute(
        """SELECT id, original_name, storage_key, mime_type
             FROM topic_attachment_drafts WHERE id = ? AND created_by = ?""",
        (draft_id, user_id()),
    ).fetchone()
    if not row:
        return api_error("Adjunto temporal no encontrado.", 404)
    try:
        return storage_response(str(row["storage_key"]), str(row["original_name"]), str(row["mime_type"] or "application/octet-stream"))
    except RuntimeError as exc:
        return api_error(str(exc), 503)

@router.delete("/api/admin/topic-attachment-drafts/{draft_id}")
@require_admin
def admin_topic_attachment_draft_delete(draft_id: int):
    error = admin_csrf_error()
    if error:
        return error
    db = get_db()
    row = db.execute(
        "SELECT id, storage_key FROM topic_attachment_drafts WHERE id = ? AND created_by = ?",
        (draft_id, user_id()),
    ).fetchone()
    if not row:
        return api_error("Adjunto temporal no encontrado.", 404)
    db.execute("DELETE FROM topic_attachment_drafts WHERE id = ?", (draft_id,))
    db.commit()
    try:
        storage_delete(str(row["storage_key"]))
    except Exception:
        pass
    return api_ok({"id": draft_id})

@router.post("/api/admin/topics/{topic_id}/attachments")
@require_admin
def admin_topic_attachment_upload(topic_id: int, files: list[UploadFile] = File(...)):
    error = admin_csrf_error()
    if error:
        return error
    db = get_db()
    topic = db.execute("SELECT id FROM topics WHERE id = ?", (topic_id,)).fetchone()
    if not topic:
        return api_error("Tema no encontrado.", 404)

    files = [file for file in files if file and file.filename]
    if not files:
        return api_error("Selecciona al menos un archivo.")
    if len(files) > MAX_ATTACHMENTS_PER_UPLOAD:
        return api_error(f"Puedes subir como máximo {MAX_ATTACHMENTS_PER_UPLOAD} archivos a la vez.")

    prepared: list[tuple[Any, str, str, int, str]] = []
    try:
        for file in files:
            name = clean_attachment_name(file.filename)
            size = attachment_size(file)
            if size <= 0:
                raise ValueError(f"El archivo «{name}» está vacío.")
            if size > MAX_ATTACHMENT_BYTES:
                raise ValueError(f"El archivo «{name}» supera el máximo de 100 MB.")
            mime = str(file.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream")
            prepared.append((file, name, mime, size, storage_key_for(name)))
    except ValueError as exc:
        return api_error(str(exc))

    stored_keys: list[str] = []
    created_ids: list[int] = []
    try:
        for file, name, mime, size, key in prepared:
            storage_put(file, key, mime)
            stored_keys.append(key)
            cursor = db.execute(
                """INSERT INTO topic_attachments(topic_id, original_name, storage_key, mime_type, size_bytes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (topic_id, name, key, mime, size, utc_iso()),
            )
            created_ids.append(int(cursor.lastrowid))
        db.commit()
    except Exception as exc:
        db.rollback()
        for key in stored_keys:
            try:
                storage_delete(key)
            except Exception:
                pass
        if isinstance(exc, RuntimeError):
            return api_error(str(exc), 503)
        raise

    placeholders = ",".join("?" for _ in created_ids)
    rows = db.execute(
        f"SELECT id, topic_id, original_name, mime_type, size_bytes FROM topic_attachments WHERE id IN ({placeholders}) ORDER BY id",
        created_ids,
    ).fetchall()
    return api_ok([attachment_payload(row) for row in rows], 201)

@router.delete("/api/admin/topics/{topic_id}/attachments/{attachment_id}")
@require_admin
def admin_topic_attachment_delete(topic_id: int, attachment_id: int):
    error = admin_csrf_error()
    if error:
        return error
    db = get_db()
    row = db.execute(
        "SELECT id, storage_key FROM topic_attachments WHERE id = ? AND topic_id = ?",
        (attachment_id, topic_id),
    ).fetchone()
    if not row:
        return api_error("Adjunto no encontrado.", 404)
    db.execute("DELETE FROM topic_attachments WHERE id = ?", (attachment_id,))
    db.commit()
    try:
        storage_delete(str(row["storage_key"]))
    except Exception:
        # Metadata is authoritative; an orphaned object can be cleaned up later.
        pass
    return api_ok({"deleted": True})

@router.get("/api/topics/{topic_id}/attachments/{attachment_id}/download")
@require_auth
def topic_attachment_download(topic_id: int, attachment_id: int):
    if topic_id not in set(current_topic_ids()):
        return api_error("Adjunto no encontrado.", 404)
    row = get_db().execute(
        """SELECT id, topic_id, original_name, storage_key, mime_type, size_bytes
           FROM topic_attachments WHERE id = ? AND topic_id = ?""",
        (attachment_id, topic_id),
    ).fetchone()
    if not row:
        return api_error("Adjunto no encontrado.", 404)
    try:
        response = storage_response(
            str(row["storage_key"]),
            str(row["original_name"]),
            str(row["mime_type"] or "application/octet-stream"),
        )
        if hasattr(response, "headers"):
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    except RuntimeError as exc:
        return api_error(str(exc), 503)

@router.delete("/api/admin/topics/{topic_id}")
@require_admin
def admin_topic_delete(topic_id: int):
    error = admin_csrf_error()
    if error:
        return error
    db = get_db()
    if not db.execute("SELECT id FROM topics WHERE id = ?", (topic_id,)).fetchone():
        return api_error("Tema no encontrado.", 404)

    stored_keys = [str(row["storage_key"]) for row in db.execute(
        "SELECT storage_key FROM topic_attachments WHERE topic_id = ?", (topic_id,)
    ).fetchall()]
    try:
        # questions, options, attempts, user assignments and attachment rows cascade.
        db.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return api_error("No se ha podido eliminar el tema.", 409)

    for key in stored_keys:
        try:
            storage_delete(key)
        except Exception:
            # DB deletion must not be rolled back because a storage backend is temporarily unavailable.
            pass
    return api_ok({"deleted": True})

@router.get("/api/admin/questions")
@require_admin
def admin_questions_list():
    db = get_db()
    rows = db.execute(
        """
        SELECT q.id, q.text, q.explanation, q.topic_id, q.created_at,
               t.number AS topic_number, t.name AS topic_name, t.color AS topic_color,
               (SELECT COUNT(*) FROM attempts a WHERE a.question_id = q.id AND a.outcome != 'skipped') AS answered_count,
               (SELECT COUNT(*) FROM attempts a WHERE a.question_id = q.id AND a.outcome = 'correct') AS correct_count
        FROM questions q
        JOIN topics t ON t.id = q.topic_id
        ORDER BY t.number, q.id
        """
    ).fetchall()
    if not rows:
        return api_ok([])

    question_ids = [int(row["id"]) for row in rows]
    placeholders = ",".join("?" for _ in question_ids)
    option_rows = db.execute(
        f"SELECT id, question_id, text, position, is_correct FROM options WHERE question_id IN ({placeholders}) ORDER BY question_id, position",
        question_ids,
    ).fetchall()
    options_by_question: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for option in option_rows:
        options_by_question[int(option["question_id"])].append({
            "id": int(option["id"]),
            "text": option["text"],
            "position": int(option["position"]),
            "is_correct": bool(option["is_correct"]),
        })

    return api_ok([
        {
            "id": int(row["id"]),
            "text": row["text"],
            "explanation": row["explanation"] or None,
            "topic_id": int(row["topic_id"]),
            "created_at": row["created_at"],
            "answered_count": int(row["answered_count"]),
            "correct_count": int(row["correct_count"]),
            "accuracy": round((int(row["correct_count"]) / int(row["answered_count"]) * 100) if int(row["answered_count"]) else 0, 1),
            "topic": {
                "id": int(row["topic_id"]),
                "number": str(row["topic_number"]),
                "name": row["topic_name"],
                "color": row["topic_color"],
            },
            "options": options_by_question[int(row["id"])],
        }
        for row in rows
    ])

@router.post("/api/admin/questions")
@require_admin
def admin_question_create():
    error = admin_csrf_error()
    if error:
        return error
    data = json_body() or {}
    try:
        topic_id, text, explanation, options = validate_question_input(data)
    except ValueError as exc:
        return api_error(str(exc))

    db = get_db()
    now = utc_iso()
    try:
        cursor = db.execute(
            "INSERT INTO questions(topic_id, text, explanation, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (topic_id, text, explanation, now, now),
        )
        question_id = int(cursor.lastrowid)
        db.executemany(
            "INSERT INTO options(question_id, text, position, is_correct) VALUES (?, ?, ?, ?)",
            [
                (question_id, option["text"], position, 1 if option["is_correct"] else 0)
                for position, option in enumerate(options)
            ],
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return api_error("No se ha podido crear la pregunta.", 409)
    return api_ok({"id": question_id}, 201)

@router.put("/api/admin/questions/{question_id}")
@require_admin
def admin_question_update(question_id: int):
    error = admin_csrf_error()
    if error:
        return error
    data = json_body() or {}
    try:
        topic_id, text, explanation, options = validate_question_input(data)
    except ValueError as exc:
        return api_error(str(exc))

    db = get_db()
    question = db.execute(
        "SELECT id FROM questions WHERE id = ?", (question_id,)
    ).fetchone()
    if not question:
        return api_error("Pregunta no encontrada.", 404)

    existing_rows = db.execute(
        "SELECT id, position FROM options WHERE question_id = ? ORDER BY position", (question_id,)
    ).fetchall()
    existing = {int(row["id"]): int(row["position"]) for row in existing_rows}
    submitted_ids = {int(option["id"]) for option in options if option.get("id") is not None}
    if any(option_id not in existing for option_id in submitted_ids):
        return api_error("Alguna respuesta no pertenece a esta pregunta.", 400)

    removed_ids = [option_id for option_id in existing if option_id not in submitted_ids]

    free_positions = [position for position in range(10) if position not in {existing[oid] for oid in submitted_ids}]
    try:
        db.execute(
            "UPDATE questions SET topic_id = ?, text = ?, explanation = ?, updated_at = ? WHERE id = ?",
            (topic_id, text, explanation, utc_iso(), question_id),
        )
        db.execute("UPDATE options SET is_correct = 0 WHERE question_id = ?", (question_id,))

        # Delete unreferenced removed options first so their positions can be reused safely.
        for option_id in removed_ids:
            db.execute("DELETE FROM options WHERE id = ?", (option_id,))

        for option in options:
            option_id = option.get("id")
            if option_id is not None:
                db.execute(
                    "UPDATE options SET text = ?, is_correct = ? WHERE id = ? AND question_id = ?",
                    (option["text"], 1 if option["is_correct"] else 0, int(option_id), question_id),
                )
            else:
                if not free_positions:
                    raise sqlite3.IntegrityError("No free option positions")
                position = free_positions.pop(0)
                db.execute(
                    "INSERT INTO options(question_id, text, position, is_correct) VALUES (?, ?, ?, ?)",
                    (question_id, option["text"], position, 1 if option["is_correct"] else 0),
                )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return api_error("No se ha podido actualizar la pregunta.", 409)
    return api_ok({"id": question_id})

@router.delete("/api/admin/questions/{question_id}")
@require_admin
def admin_question_delete(question_id: int):
    error = admin_csrf_error()
    if error:
        return error
    db = get_db()
    if not db.execute("SELECT id FROM questions WHERE id = ?", (question_id,)).fetchone():
        return api_error("Pregunta no encontrada.", 404)
    try:
        # options and attempts are deleted by their ON DELETE CASCADE foreign keys.
        db.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return api_error("No se ha podido eliminar la pregunta.", 409)
    return api_ok({"deleted": True})

@router.get("/api/admin/users")
@require_admin
def admin_users_list():
    db = get_db()
    rows = db.execute(
        """
        SELECT u.id, u.username, u.display_name, u.role, u.is_active, u.created_at, u.deactivated_at,
               (SELECT COUNT(*) FROM attempts a WHERE a.user_id = u.id AND a.outcome != 'skipped') AS attempt_count,
               (SELECT COUNT(*) FROM attempts a WHERE a.user_id = u.id AND a.outcome = 'correct') AS correct_count
        FROM users u
        ORDER BY u.is_active DESC, u.display_name COLLATE NOCASE, u.username COLLATE NOCASE
        """
    ).fetchall()
    active_topic_ids = [int(row["id"]) for row in db.execute("SELECT id FROM topics").fetchall()]
    topic_rows = db.execute(
        "SELECT user_id, topic_id FROM user_topics ORDER BY user_id, topic_id"
    ).fetchall()
    topics_by_user: dict[int, list[int]] = defaultdict(list)
    for topic_row in topic_rows:
        topics_by_user[int(topic_row["user_id"])].append(int(topic_row["topic_id"]))

    return api_ok([
        {
            "id": int(row["id"]),
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
            "is_active": bool(row["is_active"]),
            "created_at": row["created_at"],
            "deactivated_at": row["deactivated_at"],
            "attempt_count": int(row["attempt_count"]),
            "correct_count": int(row["correct_count"]),
            "accuracy": round((int(row["correct_count"]) / int(row["attempt_count"]) * 100) if int(row["attempt_count"]) else 0, 1),
            "topic_ids": active_topic_ids if row["role"] == "admin" else topics_by_user.get(int(row["id"]), []),
            "is_self": int(row["id"]) == user_id(),
        }
        for row in rows
    ])

@router.get("/api/admin/users/username-suggestion")
@require_admin
def admin_username_suggestion():
    display_name = str(request.args.get("display_name") or "").strip()
    if not display_name:
        return api_ok({"username": ""})
    try:
        display_name = clean_required_text(display_name, "El nombre", 100)
        exclude_id = int(request.args["exclude_id"]) if request.args.get("exclude_id") else None
        username = suggest_username(display_name, exclude_id)
    except (TypeError, ValueError) as exc:
        return api_error(str(exc) or "No se ha podido generar el usuario.")
    return api_ok({"username": username})

@router.get("/api/admin/users/username-check")
@require_admin
def admin_username_check():
    raw = request.args.get("username")
    try:
        username = clean_username(raw)
        exclude_id = int(request.args["exclude_id"]) if request.args.get("exclude_id") else None
    except (TypeError, ValueError) as exc:
        return api_error(str(exc) or "El usuario no es válido.")
    return api_ok({"available": username_is_available(username, exclude_id)})

@router.post("/api/admin/users")
@require_admin
def admin_user_create():
    error = admin_csrf_error()
    if error:
        return error
    data = json_body() or {}
    try:
        username = clean_username(data.get("username"))
        display_name = clean_required_text(data.get("display_name"), "El nombre", 100)
        role = str(data.get("role", "user"))
        if role not in {"user", "admin"}:
            raise ValueError("El rol no es válido.")
        topic_ids = clean_user_topic_ids(data.get("topic_ids"), role)
        salt, digest = new_password_values(str(data.get("password", "")))
    except ValueError as exc:
        return api_error(str(exc))

    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        cursor = db.execute(
            """
            INSERT INTO users(username, display_name, password_salt, password_hash, role, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (username, display_name, salt, digest, role, utc_iso()),
        )
        new_user_id = int(cursor.lastrowid)
        if role == "user":
            db.executemany(
                "INSERT INTO user_topics(user_id, topic_id) VALUES (?, ?)",
                [(new_user_id, topic_id) for topic_id in topic_ids],
            )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return api_error("Ya existe un usuario con ese nombre de usuario.", 409)
    return api_ok({"id": new_user_id}, 201)

@router.put("/api/admin/users/{target_user_id}")
@require_admin
def admin_user_update(target_user_id: int):
    error = admin_csrf_error()
    if error:
        return error
    data = json_body() or {}
    db = get_db()
    if not db.execute("SELECT id FROM users WHERE id = ?", (target_user_id,)).fetchone():
        return api_error("Usuario no encontrado.", 404)

    try:
        username = clean_username(data.get("username"))
        display_name = clean_required_text(data.get("display_name"), "El nombre", 100)
        role = str(data.get("role", "user"))
        if role not in {"user", "admin"}:
            raise ValueError("El rol no es válido.")
        topic_ids = clean_user_topic_ids(data.get("topic_ids"), role)
        password = str(data.get("password", ""))
        password_values = new_password_values(password) if password else None
    except ValueError as exc:
        return api_error(str(exc))

    try:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT * FROM users WHERE id = ?", (target_user_id,)).fetchone()
        if not current:
            db.rollback()
            return api_error("Usuario no encontrado.", 404)
        if current["role"] == "admin" and role != "admin" and active_admins_excluding(target_user_id) == 0:
            db.rollback()
            return api_error("Debe quedar al menos un administrador activo.", 409)

        if password_values:
            salt, digest = password_values
            db.execute(
                "UPDATE users SET username = ?, display_name = ?, role = ?, password_salt = ?, password_hash = ? WHERE id = ?",
                (username, display_name, role, salt, digest, target_user_id),
            )
        else:
            db.execute(
                "UPDATE users SET username = ?, display_name = ?, role = ? WHERE id = ?",
                (username, display_name, role, target_user_id),
            )
        if password_values:
            # No push is involved: existing devices simply fail authentication on their next request.
            db.execute("DELETE FROM sessions WHERE user_id = ?", (target_user_id,))
        db.execute("DELETE FROM user_topics WHERE user_id = ?", (target_user_id,))
        if role == "user":
            db.executemany(
                "INSERT INTO user_topics(user_id, topic_id) VALUES (?, ?)",
                [(target_user_id, topic_id) for topic_id in topic_ids],
            )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return api_error("Ya existe un usuario con ese nombre de usuario.", 409)
    except Exception:
        db.rollback()
        raise
    return api_ok({"id": target_user_id})

@router.post("/api/admin/users/{target_user_id}/deactivate")
@require_admin
def admin_user_deactivate(target_user_id: int):
    error = admin_csrf_error()
    if error:
        return error
    if target_user_id == user_id():
        return api_error("No puedes dar de baja tu propio usuario.", 409)

    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT * FROM users WHERE id = ?", (target_user_id,)).fetchone()
        if not current:
            db.rollback()
            return api_error("Usuario no encontrado.", 404)
        if not current["is_active"]:
            db.rollback()
            return api_ok({"deactivated": True})
        if current["role"] == "admin" and active_admins_excluding(target_user_id) == 0:
            db.rollback()
            return api_error("Debe quedar al menos un administrador activo.", 409)

        db.execute("DELETE FROM sessions WHERE user_id = ?", (target_user_id,))
        db.execute(
            "UPDATE users SET is_active = 0, deactivated_at = ? WHERE id = ?",
            (utc_iso(), target_user_id),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return api_ok({"deactivated": True})

@router.delete("/api/admin/users/{target_user_id}")
@require_admin
def admin_user_delete(target_user_id: int):
    """Permanently remove a user and all personal activity/history."""
    error = admin_csrf_error()
    if error:
        return error
    if target_user_id == user_id():
        return api_error("No puedes eliminar definitivamente tu propio usuario.", 409)

    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT * FROM users WHERE id = ?", (target_user_id,)).fetchone()
        if not current:
            db.rollback()
            return api_error("Usuario no encontrado.", 404)
        if current["role"] == "admin" and current["is_active"] and active_admins_excluding(target_user_id) == 0:
            db.rollback()
            return api_error("Debe quedar al menos un administrador activo.", 409)

        # sessions, attempts and topic assignments cascade from users.
        db.execute("DELETE FROM users WHERE id = ?", (target_user_id,))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return api_error("No se ha podido eliminar definitivamente el usuario.", 409)
    except Exception:
        db.rollback()
        raise
    return api_ok({"deleted": True})

@router.post("/api/admin/users/{target_user_id}/activate")
@require_admin
def admin_user_activate(target_user_id: int):
    error = admin_csrf_error()
    if error:
        return error
    db = get_db()
    current = db.execute("SELECT id, is_active FROM users WHERE id = ?", (target_user_id,)).fetchone()
    if not current:
        return api_error("Usuario no encontrado.", 404)
    if current["is_active"]:
        return api_ok({"activated": True})
    db.execute(
        "UPDATE users SET is_active = 1, deactivated_at = NULL WHERE id = ?",
        (target_user_id,),
    )
    db.commit()
    return api_ok({"activated": True})

