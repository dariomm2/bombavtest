#!/bin/sh
set -eu

mkdir -p "$(dirname "$BOMBAVTEST_DB_PATH")"

yoyo --no-config-file --batch apply \
  --database "sqlite:///$BOMBAVTEST_DB_PATH" \
  migrations

exec uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips="*"