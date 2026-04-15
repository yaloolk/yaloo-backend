# core/celery.py

import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# Create Celery app
app = Celery('yaloo')

# Load config from Django settings with 'CELERY' prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Schedule for cleanup task
app.conf.beat_schedule = {
    'cleanup-past-availability-daily': {
        'task': 'accounts.tasks.cleanup_past_availability_slots',
        'schedule': crontab(hour=3, minute=0),  # 3 AM daily
      #   'schedule': 30.0, 
    },
}

app.conf.timezone = 'Asia/Karachi'

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')