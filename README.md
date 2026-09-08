# BombAvTest

BombAvTest is a web application for firefighter exam preparation, featuring question practice, mock exams, statistics, and syllabus and user management.

## Tech Stack

* FastAPI + Uvicorn
* SQLite + Yoyo
* HTML, CSS, and JavaScript
* S3-compatible object storage
* MinIO for local development
* Docker
* Railway
* GitHub Actions

## Project Structure

```text
src/backend/    Backend and API
src/frontend/   Web interface
migrations/     Database migrations
tests/          Test suite
```

In production, the SQLite database is stored at `/data/app.db`.

File attachments are stored using S3-compatible object storage. MinIO is used as the local development storage backend.

Yoyo migrations are automatically applied before Uvicorn starts.

## Environment Variables

BombAvTest uses the following environment variables:

```env
# App
BOMBAVTEST_DB_PATH=/data/app.db

# Initial admin (required only when users table is empty)
BOMBAVTEST_ADMIN_USERNAME=admin
BOMBAVTEST_ADMIN_PASSWORD=admin
BOMBAVTEST_ADMIN_DISPLAY_NAME=Admin

# S3-compatible storage
S3_ENDPOINT_URL=http://minio:9000
S3_BUCKET=bombavtest
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_REGION=us-east-1
S3_ADDRESSING_STYLE=path
```

The values required for local development are already configured in `compose.yaml`.

## Local Development

Start the application and MinIO:

```bash
docker compose up --build -d
```

BombAvTest:

```text
http://localhost:8000
```

MinIO Console:

```text
http://localhost:9001
```

To stop the environment and remove all local data:

```bash
docker compose down -v
```

> Warning: This removes both the local SQLite database and the MinIO volume.

## Tests

Install the development dependencies:

```bash
python -m pip install --group dev
python -m playwright install --with-deps chromium
```

Run the full test suite:

```bash
python -m pytest -v
```
