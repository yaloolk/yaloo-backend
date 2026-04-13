@echo off
echo Starting Yaloo Backend Services...
echo.

REM Change to your project directory
cd /d "F:\1.GCU CS\Yaloo-App\yaloo-backend"

REM Activate virtual environment
call venv_new\Scripts\activate.bat

REM Clean stale Celery Beat schedule (prevents ghost schedules)
echo Cleaning stale Celery Beat schedule...
if exist celerybeat-schedule del /f celerybeat-schedule
if exist celerybeat-schedule.db del /f celerybeat-schedule.db
if exist celerybeat.pid del /f celerybeat.pid

REM Start Redis (if using Docker)
echo Starting Redis...
start /B docker start redis-yaloo 2>nul || docker run -d --name redis-yaloo -p 6379:6379 redis
timeout /t 3 /nobreak >nul

REM Start Celery Worker in new window
echo Starting Celery Worker...
start "Celery Worker" cmd /k "cd /d F:\1.GCU CS\Yaloo-App\yaloo-backend && venv_new\Scripts\activate.bat && celery -A core worker --loglevel=info --pool=solo"
timeout /t 3 /nobreak >nul

REM Start Celery Beat in new window
echo Starting Celery Beat...
start "Celery Beat" cmd /k "cd /d F:\1.GCU CS\Yaloo-App\yaloo-backend && venv_new\Scripts\activate.bat && celery -A core beat --loglevel=info"
timeout /t 2 /nobreak >nul

REM Start Django Server
echo Starting Django Server...
echo.
echo ========================================
echo Services started:
echo   - Redis       (Docker)
echo   - Celery Worker
echo   - Celery Beat
echo   - Django      http://127.0.0.1:8000
echo ========================================
echo.
python manage.py runserver

pause