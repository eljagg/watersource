# Performance targets and how they are met

| ToR target | Design |
|---|---|
| ≥ 100 concurrent users (ToR); FCC internal target 3,000 | gunicorn gthread workers behind nginx; Redis-backed sessions and cache; PgBouncer; read-mostly pages cached 60 s for guests; HTMX partial updates instead of full-page reloads |
| Search < 3 s | indexed natural keys and aliases (GIN), composite (site, time) indexes, `select_related` on every list view, pagination at 100 rows |
| Standard reports < 30 s | materialised views in `bi`, refreshed nightly and after bulk approvals; Metabase caches |
| CSV up to 50,000 rows | validated row by row in a Celery task; bulk_create in batches of 1,000 |
| Availability ≥ 99 % business hours | health checks, auto-restart, Hyper-V checkpoints, monitored by Uptime Kuma/Prometheus |

Load test gates (Stage 7): p95 page < 1.5 s and p95 API < 500 ms at 3,000 virtual users; error rate < 0.1 %.
