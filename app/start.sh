#!/bin/sh
# Container entrypoint: apply Alembic migrations, then serve the API.
set -e
echo "Running Alembic migrations..."
alembic upgrade head
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"