FROM python:3.13-slim

ARG BOMBAVTEST_VERSION=dev
ARG RAILWAY_GIT_COMMIT_SHA=unknown

LABEL org.opencontainers.image.title="BombAvTest" \
      org.opencontainers.image.source="https://github.com/dariomm2/bombavtest" \
      org.opencontainers.image.version="${BOMBAVTEST_VERSION}" \
      org.opencontainers.image.revision="${RAILWAY_GIT_COMMIT_SHA}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BOMBAVTEST_DB_PATH=/data/app.db \
    BOMBAVTEST_VERSION=${BOMBAVTEST_VERSION} \
    BOMBAVTEST_REVISION=${RAILWAY_GIT_COMMIT_SHA}

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY migrations ./migrations
COPY --chmod=755 entrypoint.sh ./

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]