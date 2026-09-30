# Deployment

## Environments
| Env | Where | Purpose |
|---|---|---|
| dev | developer laptop, `docker compose` | build and unit tests |
| staging | Railway (web, worker, beat, PostGIS template, Redis) | integration testing, WRA demos, UAT dry runs — **no production data** (Addendum 1 §6) |
| test | WRA app-vm, Compose project `ws-test` | UAT with migrated data, DR rehearsal |
| prod | WRA app-vm, Compose project `ws-prod` | live |

## app-vm layout (production)
nginx (443) → web (gunicorn gthread, `WEB_CONCURRENCY` = 2×vCPU+1, 4 threads) → PgBouncer → PostgreSQL/PostGIS.
worker + beat (Celery) share the image; Redis for cache/queue/sessions; ClamAV; Metabase on its own database.
Media on the RAID-5 volume (`/srv/watersource/media`), exports on `/srv/watersource/exports` (shared read-only to GIS and Finance).

## Release procedure
1. CI green on the tag → image `watersource:<tag>` pushed to the registry.
2. `docker compose pull && docker compose run --rm web migrate` on **test**; smoke test; ICT Manager go-ahead.
3. Hyper-V checkpoint of the app-vm; same two commands on **prod**; `docker compose up -d`.
4. Roll back = previous tag + restore from checkpoint if the migration cannot be reversed.

## Capacity for 3,000 concurrent users
Assumed think time 30 s → ~100 req/s steady, 300 req/s peak. Measured on a 16-vCPU VM in Stage 7 load tests (Locust
profile in `loadtest/`). Hardware note: the ToR's "anticipated minimum" quad-core CPU is not enough for this target;
the design plan recommends a 16-core CPU on the supplied server (see the Technical Design, §10).


## Schema step and start-up (added 30 Sep 2026)

`scripts/entrypoint.sh migrate` is the schema step: migrate → bootstrap roles/workflows/categories → load reference data → (`DEMO_DATA=1`) seed demo data → refresh bi views. Every part is idempotent.

* Railway: runs as the pre-deploy command **and** again when the `web` container starts (`MIGRATE_ON_START` defaults to 1). The double run costs a few seconds and guarantees the database the web container connects to is migrated.
* WRA production (docker-compose): set `MIGRATE_ON_START=0` on the web service and run `docker compose run --rm web /app/scripts/entrypoint.sh migrate` as an explicit step in the release runbook.
* `/healthz` returns `{"db": "ok", "schema": "ok", "cache": "ok"}`; `schema` becomes `pending: N migrations` with HTTP 503 if the database is behind the code.
