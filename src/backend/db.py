from __future__ import annotations

import sqlite3
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from .config import database_path

_current_db: ContextVar[sqlite3.Connection | None] = ContextVar("bombavtest_db", default=None)


def connect_db(path: Path | str | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path is not None else database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def get_db() -> sqlite3.Connection:
    db = _current_db.get()
    if db is None:
        raise RuntimeError("No hay conexión SQLite en este contexto.")
    return db


def bind_db(db: sqlite3.Connection) -> Any:
    return _current_db.set(db)


def reset_db(token: Any) -> None:
    _current_db.reset(token)
