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

echo "Starting qcluster in background..."
python manage.py qcluster &

mkdir -p /app/backups

echo "Starting Gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 4 --worker-class gthread --timeout 300
