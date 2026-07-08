#!/bin/bash
set -e

# If arguments are passed (e.g. "docker compose run web python manage.py restore ..."),
# skip the full startup and run the command directly.
if [ $# -gt 0 ]; then
    exec "$@"
fi

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Creating superuser (if not exists)..."
python manage.py createsuperuser --noinput || true

echo "Setting up notification schedules..."
python manage.py setup_schedules || echo "WARNING: setup_schedules failed (non-fatal)"

# Load sample data if requested (command has built-in idempotency guard)
if [ "$LOAD_SAMPLE_DATA" = "true" ]; then
    python manage.py load_sample_data || echo "WARNING: load_sample_data failed (non-fatal)"
fi

# NOTE: the Django-Q2 cluster is no longer launched here. It runs as its own
# `qcluster` compose service (restart: unless-stopped) so a worker crash is
# supervised and auto-restarted instead of silently dying inside this
# container while gunicorn stays up (async chat-title generation would
# otherwise stop with no signal). See docker-compose.yml.

mkdir -p /app/backups

echo "Starting Gunicorn..."
# --threads 16: each streaming assistant turn holds a gthread slot for
# minutes (SSE response + detached drains), so 2x4=8 slots starved the rest
# of the app during 2-3 concurrent turns. gthread threads are cheap for
# I/O-bound work; 2x16=32 slots. Workers stay at 2 — SQLite is
# single-writer, so more processes only add lock contention.
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 16 --worker-class gthread --timeout 300 --error-logfile - --capture-output
