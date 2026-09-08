from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

SESSION_COOKIE = "bombavtest_session"
SESSION_DAYS = 14
LOGIN_RATE_WINDOW = 60
LOGIN_RATE_MAX = 10
LOGIN_RATE_MAX_KEYS = 5000
MIB = 1024 * 1024
MAX_JSON_BYTES = MIB
MAX_ATTACHMENT_BYTES = 100 * MIB
MAX_ATTACHMENTS_PER_TOPIC = 12
MAX_TOPIC_ATTACHMENTS_BYTES = 200 * MIB
MAX_UPLOAD_REQUEST_BYTES = MAX_TOPIC_ATTACHMENTS_BYTES + 2 * MIB  # margen multipart


def database_path() -> Path:
    return Path(os.environ.get("BOMBAVTEST_DB_PATH", "/data/app.db")).expanduser()

def app_version() -> str:
    return os.environ.get("BOMBAVTEST_VERSION", "dev").strip() or "dev"


def app_revision() -> str:
    return os.environ.get("BOMBAVTEST_REVISION", "unknown").strip() or "unknown"

