#!/usr/bin/env bash
# Container entrypoint. Usage: entrypoint.sh web|worker|beat|migrate|shell
#
#   web      run the schema step (unless MIGRATE_ON_START=0), then gunicorn
#   migrate  schema step only: migrate → bootstrap roles/admin/workflows/categories →
#            load reference data → (DEMO_DATA=1: seed demo data) → refresh bi views
#
# Railway runs `migrate` as the pre-deploy command AND `web` runs it again at
# start-up. Every step is idempotent, so the double run costs a few seconds and
# guarantees the database gunicorn actually connects to is migrated — the
# 30 Sep incident was a web container serving a database with no tables.
# Production on WRA's server (docker-compose) sets MIGRATE_ON_START=0 and runs
# the migrate step as an explicit job (docs/deployment.md).
set -euo pipefail
PORT="${PORT:-8000}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-$(( $(nproc) * 2 + 1 ))}"
if [ "$WEB_CONCURRENCY" -gt 8 ]; then WEB_CONCURRENCY=8; fi   # cap: container CPU counts on shared hosts are misleading
THREADS="${GUNICORN_THREADS:-4}"

schema_step() {
  echo "[entrypoint] schema step: migrate + bootstrap + reference data (DEMO_DATA=${DEMO_DATA:-0})"
  python manage.py migrate --noinput
  python manage.py bootstrap_roles
  python manage.py bootstrap_admin
  python manage.py bootstrap_workflows
  python manage.py bootstrap_categories
  python manage.py load_reference_data
  if [ "${DEMO_DATA:-0}" = "1" ]; then python manage.py seed_demo_data --force; fi
  python manage.py refresh_bi_views
  echo "[entrypoint] schema step done"
}

case "${1:-web}" in
  web)
    if [ "${MIGRATE_ON_START:-1}" = "1" ]; then schema_step; fi
    exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT}" --workers "${WEB_CONCURRENCY}" --threads "${THREADS}" \
      --worker-class gthread --timeout 60 --graceful-timeout 30 --keep-alive 5 --max-requests 2000 --max-requests-jitter 200 \
      --access-logfile - --error-logfile - --forwarded-allow-ips="*" ;;
  worker) exec celery -A config worker --loglevel=INFO --concurrency "${CELERY_CONCURRENCY:-4}" -Q celery ;;
  beat)   exec celery -A config beat --loglevel=INFO ;;
  migrate) schema_step ;;
  shell)  exec python manage.py shell ;;
  *)      exec "$@" ;;
esac
