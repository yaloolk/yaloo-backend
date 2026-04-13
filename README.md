## Development Startup

To start all services (Redis, Celery, Django):

```batch
.\start_all.bat
```

This will open 3 windows:

1. Celery Worker - Processes background tasks
2. Celery Beat - Schedules tasks
3. Django Server - Your main application

To stop: Close all 3 windows
