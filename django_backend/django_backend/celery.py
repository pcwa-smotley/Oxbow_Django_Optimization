# django_backend/django_backend/celery.py

import os
import sys
from pathlib import Path
from celery import Celery
from celery.schedules import crontab

# Ensure the repository root (which holds the abay_opt package) is importable
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_backend.settings')

app = Celery('django_backend')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Configure periodic tasks
app.conf.beat_schedule = {
    'check-alerts-every-minute': {
        'task': 'optimization_api.tasks.check_system_alerts',
        'schedule': 60.0,  # Run every 60 seconds
    },
    'cleanup-old-alerts-daily': {
        'task': 'optimization_api.tasks.cleanup_old_alert_logs',
        'schedule': crontab(hour=2, minute=0),  # Run at 2 AM daily
    },
}


