#!/bin/bash
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Creating superuser (if not exists)..."
python manage.py createsuperuser --noinput || true

echo "Setting up notification schedules..."
python manage.py setup_schedules

# Load sample data if requested (command has built-in idempotency guard)
if [ "$LOAD_SAMPLE_DATA" = "true" ]; then
    python manage.py load_sample_data
fi

echo "Starting qcluster in background..."
python manage.py qcluster &

mkdir -p /app/backups

echo "Starting Gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 30
