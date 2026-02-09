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

# Load sample data if requested and DB is empty
if [ "$LOAD_SAMPLE_DATA" = "true" ]; then
    python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blaine.settings')
django.setup()
from stakeholders.models import Stakeholder
if not Stakeholder.objects.exists():
    print('Loading sample data...')
    import subprocess
    subprocess.run(['python', 'manage.py', 'load_sample_data'], check=True)
else:
    print('Sample data already loaded, skipping.')
"
fi

echo "Starting qcluster in background..."
python manage.py qcluster &

echo "Starting Gunicorn..."
exec gunicorn blaine.wsgi:application --bind 0.0.0.0:8000 --workers 2
