# Database notes

* One PostgreSQL 16 + PostGIS 3.4 database, `watersource`. Django-managed tables in `public`; reporting objects in `bi`.
* Geometry stored in EPSG:3448 (JAD2001). Exports transform to EPSG:4326.
* Every published table carries `approval_state`, `classification`, `source`, `paper_ref`, `electronic_ref`, `created_by/at`, `updated_by/at`.
* Append-only tables (`core_auditlog`, `workflow_workflowaction`, `obs_recordhistory`): the application role has no UPDATE/DELETE grant (`scripts/db_roles.sql`) and the models refuse updates/deletes in Python as a second line.
* Public views `bi.public_*` select only `approval_state='approved' AND classification='public'`; Metabase's `bi_reader` and the export role can read nothing else.
* Time series: composite indexes on (site, timestamp). When `obs_wellwaterlevel` or `obs_stationreading` passes ~20 M rows, convert to yearly range partitions with pg_partman (runbook `docs/runbooks/partitioning.md`, to be written in the Design Phase); Django needs no model change because the ORM reads the parent table.
* Tuning for the app-vm (40 GB RAM): `shared_buffers=10GB`, `effective_cache_size=28GB`, `work_mem=32MB`, `maintenance_work_mem=1GB`, `max_connections=200` behind PgBouncer (transaction pooling, pool 40).
* Backups: pgBackRest full weekly, differential daily, WAL archiving continuous (RPO ≤ 15 min); weekly automated restore test.
