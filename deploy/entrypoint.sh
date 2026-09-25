#!/bin/sh
# Container start: bring the database and static files up to date, then serve.
# Running migrations here (and not from cron) keeps a single, predictable place where
# the schema changes — see deploy/crontab.
set -e

echo "==> migracje"
python manage.py migrate --noinput

echo "==> pliki statyczne"
python manage.py collectstatic --noinput --clear

echo "==> gunicorn"
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${APP_PORT:-8000}" \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout 60 \
    --max-requests 500 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile -
