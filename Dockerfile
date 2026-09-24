# WaterSource Jamaica — application image (web, worker and beat share it)
FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DJANGO_SETTINGS_MODULE=config.settings.prod
# GeoDjango runtime libraries + libmagic for upload validation
RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils libproj-dev gdal-bin libgdal32 libgeos-c1v5 libmagic1 curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN SECRET_KEY=build DATABASE_URL=postgis://x:x@localhost/x python manage.py collectstatic --noinput
RUN chmod +x /app/scripts/entrypoint.sh && useradd -r -u 10001 app && mkdir -p /app/media /app/exports && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://127.0.0.1:${PORT:-8000}/healthz || exit 1
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["web"]
