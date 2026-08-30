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
backend/       Backend and API
frontend/      Web interface
migrations/    Database migrations
tests/         Test suite
data/          Local SQLite data
```

In production, the SQLite database is stored at `/data/app.db`.

File attachments are stored using S3-compatible object storage. MinIO is used as the local development storage backend.

Yoyo migrations are automatically applied before Uvicorn starts.

## Local Development

Start the application and MinIO:

```bash
docker compose -f docker-compose.local.yml up --build -d
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
docker compose -f docker-compose.local.yml down -v && rm -rf ./data/*
```

> Warning: This removes both the local SQLite database and the MinIO volume.

## Tests

Install the development dependencies:

```bash
pip install -r requirements-dev.txt
python -m playwright install --with-deps chromium
```

Run the full test suite:

```bash
python -m pytest -v
```