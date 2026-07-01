#!/bin/sh

# Fail-fast: exit immediately if any command exits with a non-zero status.
# If database migrations fail (e.g. database offline, connection timeouts, or schema conflicts),
# the script will terminate right here. The Docker container will exit with a failure code,
# preventing the FastAPI application from starting on a broken or outdated database schema.
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting FastAPI application..."
# Use PORT environment variable (standard on Railway, fallback to 8000)
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
