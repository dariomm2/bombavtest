FROM python:3.13-slim

ARG BOMBAVTEST_VERSION=dev
ARG BOMBAVTEST_REVISION=unknown

LABEL org.opencontainers.image.title="BombAvTest" \
      org.opencontainers.image.source="https://github.com/dariomm2/BombAvTest" \
      org.opencontainers.image.version="${BOMBAVTEST_VERSION}" \
      org.opencontainers.image.revision="${BOMBAVTEST_REVISION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BOMBAVTEST_DB_PATH=/data/app.db \
    BOMBAVTEST_VERSION=${BOMBAVTEST_VERSION} \
    BOMBAVTEST_REVISION=${BOMBAVTEST_REVISION}

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY migrations ./migrations
COPY entrypoint.sh ./

RUN mkdir -p /data && chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
