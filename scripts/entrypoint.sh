#!/usr/bin/env bash
# Usage: entrypoint.sh web|worker|beat|migrate|shell
set -euo pipefail
PORT="${PORT:-8000}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-$(( $(nproc) * 2 + 1 ))}"
THREADS="${GUNICORN_THREADS:-4}"
case "${1:-web}" in
  web)
    exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT}" --workers "${WEB_CONCURRENCY}" --threads "${THREADS}" \
      --worker-class gthread --timeout 60 --graceful-timeout 30 --keep-alive 5 --max-requests 2000 --max-requests-jitter 200 \
      --access-logfile - --error-logfile - --forwarded-allow-ips="*" ;;
  worker) exec celery -A config worker --loglevel=INFO --concurrency "${CELERY_CONCURRENCY:-4}" -Q celery ;;
  beat)   exec celery -A config beat --loglevel=INFO ;;
  migrate) python manage.py migrate --noinput && python manage.py bootstrap_roles && python manage.py bootstrap_workflows && python manage.py bootstrap_categories ;;
  shell)  exec python manage.py shell ;;
  *)      exec "$@" ;;
esac
