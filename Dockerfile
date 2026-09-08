FROM python:3.13-slim

ARG BOMBAVTEST_VERSION=dev
ARG BOMBAVTEST_REVISION=unknown

LABEL org.opencontainers.image.title="BombAvTest" \
      org.opencontainers.image.source="https://github.com/dariomm2/bombavtest" \
      org.opencontainers.image.version="${BOMBAVTEST_VERSION}" \
      org.opencontainers.image.revision="${BOMBAVTEST_REVISION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    BOMBAVTEST_DB_PATH=/data/app.db \
    BOMBAVTEST_VERSION=${BOMBAVTEST_VERSION} \
    BOMBAVTEST_REVISION=${BOMBAVTEST_REVISION}

WORKDIR /app

COPY pyproject.toml ./
RUN python -m pip install --no-cache-dir --group runtime

COPY src ./src
COPY migrations ./migrations
COPY --chmod=755 entrypoint.sh ./

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
