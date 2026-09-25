# WaterSource Jamaica

Consolidated water-resources database and two web applications for the Water Resources Authority of Jamaica
(RFB No. 2026-08-28-WRA-B — *Data Consolidation and Application Development Software and Services*).

One Django project, two user-facing applications on one PostgreSQL/PostGIS database:

| App | ToR | Django apps |
|---|---|---|
| Licence Application Processing | §G.1 | `lic` (+ `workflow`, `core`, `accounts`, `ref`) |
| Data Submission | §G.2 | `submissions`, `catalog` (+ `workflow`, `obs`) |
| Consolidated database & BI | §C, §F.4 | `ref`, `obs`, `reports` (bi schema), Metabase |
| Integrations & exports | §E, Add. 1 §9, H.xiii | `integrations` |
| REST API | §F.7, H.xii | `api` (OpenAPI at `/api/docs/`) |

Design reference: `WRA-2004-38/Design Plan/12_WRA_Technical_Design_and_Build_Plan.pdf`.

## Stack

Python 3.12 · Django 5.2 LTS · PostgreSQL 16 + PostGIS 3.4 · Redis 7 · Celery 5 · HTMX 2 + Tailwind CSS v4 (compiled, no CDN; light/dark theme) ·
Django REST Framework + drf-spectacular · django-otp (TOTP MFA) · django-axes (lockout) · django-csp · Gunicorn behind nginx ·
Metabase (open-source) · Docker Compose. Production runs on WRA's own server (Addendum 1 §6); Railway is used for
development/staging only.

## Local development

```bash
cp .env.example .env                       # edit DATABASE_URL / REDIS_URL if needed
docker compose up -d db pgbouncer redis    # or use your own PostGIS + Redis
pip install -r requirements-dev.txt
npm install && npm run build               # compiles Tailwind v4 (frontend/app.css → static/css/app.css); commit the output
python manage.py migrate
python manage.py bootstrap_roles && python manage.py bootstrap_workflows && python manage.py bootstrap_categories
python manage.py createsuperuser
python manage.py runserver
```

Then: `/` (public), `/accounts/register/` (client self-registration with email verification), `/admin/` (staff
configuration: categories, workflows, roles), `/workflow/queue/` (staff review queue), `/api/docs/` (OpenAPI).

Everything in Docker: `docker compose up --build` (add `--profile bi` for Metabase, `--profile security` for ClamAV).

## Tests, lint, security checks

```bash
pytest                                     # 26 tests: auth policy, workflow engine, category validation, promotion, corrections, API, expiry alerts
ruff check . && bandit -q -r apps config -c pyproject.toml && pip-audit -r requirements.txt
DJANGO_SETTINGS_MODULE=config.settings.prod SECRET_KEY=x ALLOWED_HOSTS=example.com python manage.py check --deploy
locust -f loadtest/locustfile.py --host http://localhost:8000     # performance profile (docs/performance.md)
```

CI (`.github/workflows/ci.yml`) runs the same on every push plus a Trivy scan of the image.

## Railway (staging)

1. Create a project with the **PostGIS** template (the default Postgres service has no PostGIS; templates need the Hobby plan)
   and a **Redis** service.
2. Add three services from this repo: `web` (default), `worker` (start command `/app/scripts/entrypoint.sh worker`) and
   `beat` (`/app/scripts/entrypoint.sh beat`). `railway.json` sets the Dockerfile build, `/healthz` health check and
   the pre-deploy migration for `web`.
3. Variables on each service: `DJANGO_SETTINGS_MODULE=config.settings.prod`, `SECRET_KEY`, `ALLOWED_HOSTS`,
   `CSRF_TRUSTED_ORIGINS`, `SITE_URL`, `DATABASE_URL=${{PostGIS.DATABASE_URL}}` (use the private-network URL),
   `REDIS_URL=${{Redis.REDIS_URL}}`, `EMAIL_URL`.
4. A volume mounted at `/app/media` on `web` and `worker` for uploads (staging only — production uses the app-vm disk).

## Production (WRA app-vm)

See `docs/deployment.md`: Ubuntu 24.04 VM under Hyper-V on the WRA server, Docker Compose with nginx (TLS), web ×N,
worker, beat, PostgreSQL/PostGIS, PgBouncer, Redis, ClamAV, Metabase; pgBackRest and monitoring on the ops-vm.
Database roles for the application, Metabase and exports: `scripts/db_roles.sql`.

## Repository layout

```
config/            settings (base/dev/test/prod), urls, celery
apps/core          audit log, notifications, upload validation, health check, request id
apps/accounts      User (email login), roles, password policy, MFA enforcement, API keys, data-subject export, retention
apps/ref           parishes/basins/WMUs, parties, wells (+lithology, casing, pump tests, ownership), stations, springs
apps/obs           well water levels, station readings, abstraction records, water-quality samples, correction history
apps/catalog       data category framework: versions, fields, rules → form, CSV template, JSON Schema, validation
apps/workflow      configurable multi-stage approval engine + staff review queue
apps/lic           licence applications, documents (scan + DSpace), licences, expiry alerts
apps/submissions   submissions (form/CSV/API), records, promotion into typed tables, corrections
apps/integrations  DSpace, Aquarius, HGA clients; ArcGIS and Finance exports; run log
apps/api           DRF viewsets, API-key auth, OpenAPI
apps/reports       bi schema (materialised views) + refresh task
templates/ static/ HTMX + Tailwind UI (compiled CSS, CSP nonces, no inline scripts)
tests/             pytest suite (PostGIS required)
scripts/           entrypoint, db_roles.sql
loadtest/          Locust profile
docs/              database, security, deployment, performance notes
```

## Licence / ownership

All source, documentation, database structures and configuration produced under the contract become the property
of the Water Resources Authority on final payment (ToR §13). Third-party components are open source (BSD/MIT/PSF/AGPL
for Metabase, run as a separate service).
