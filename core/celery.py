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

app.conf.timezone = 'Asia/Colombo'  # Your timezone

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')

# ═══════════════════════════════════════════════════════════
# REQUIRED SETTINGS IN settings.py
# ═══════════════════════════════════════════════════════════

"""
Add to your settings.py:

# Celery Configuration
CELERY_BROKER_URL = 'redis://localhost:6379/0'  # Or your Redis URL
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Colombo'  # Your timezone

# Celery Beat (Scheduler)
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
"""


# ═══════════════════════════════════════════════════════════
# HOW TO RUN
# ═══════════════════════════════════════════════════════════

"""
1. Install Celery and Redis:
   pip install celery redis django-celery-beat

2. Add to INSTALLED_APPS in settings.py:
   INSTALLED_APPS = [
       ...
       'django_celery_beat',
   ]

3. Run migrations:
   python manage.py migrate django_celery_beat

4. Start Celery worker:
   celery -A config worker --loglevel=info

5. Start Celery beat (scheduler):
   celery -A config beat --loglevel=info

6. Or run both together (development only):
   celery -A config worker --beat --loglevel=info
"""