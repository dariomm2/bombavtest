#!/bin/sh
set -eu

export BOMBAVTEST_DB_PATH="${BOMBAVTEST_DB_PATH:-/data/app.db}"
mkdir -p "$(dirname "$BOMBAVTEST_DB_PATH")"

YOYO_DATABASE="sqlite:///$BOMBAVTEST_DB_PATH"
yoyo --no-config-file --batch apply \
  --database "$YOYO_DATABASE" \
  migrations

exec uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips='*'
