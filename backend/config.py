from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

SESSION_COOKIE = "bombavtest_session"
SESSION_DAYS = 14
PBKDF2_ITERATIONS = 310_000
LOGIN_RATE_WINDOW = 60
LOGIN_RATE_MAX = 10
LOGIN_RATE_MAX_KEYS = 5000
MAX_JSON_BYTES = 1024 * 1024
MAX_ATTACHMENT_BYTES = 100 * 1024 * 1024
MAX_ATTACHMENTS_PER_UPLOAD = 12
MAX_UPLOAD_REQUEST_BYTES = 202 * 1024 * 1024  # ~200 MiB + margen multipart


def database_path() -> Path:
    return Path(os.environ.get("BOMBAVTEST_DB_PATH", "/data/app.db")).expanduser()

def app_version() -> str:
    return os.environ.get("BOMBAVTEST_VERSION", "dev").strip() or "dev"


def app_revision() -> str:
    return os.environ.get("BOMBAVTEST_REVISION", "unknown").strip() or "unknown"

