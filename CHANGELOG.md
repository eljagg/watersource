# Changelog

All notable changes to WaterSource Jamaica. Dates are the date the change landed on `main`.

## [0.2.2] — 30 Sep 2026

### Changed
- Entry forms are now wide, sectioned, multi-column layouts (`templates/partials/form_section.html`, `form_grid.html`): licence application in four sections; category forms grouped by the new `CategoryField.section` (seeded categories grouped by migration 0003). Cancel on every form; sticky action bar; required-field markers.
- `manage.py bootstrap_admin` creates the first superuser from `ADMIN_EMAIL` / `ADMIN_PASSWORD` (`ADMIN_NAME` optional) during the schema step; `demo.admin` is a superuser on demo sites.

## [0.2.1] — 30 Sep 2026

### Fixed
- Web container now runs the schema step (migrate, bootstraps, reference data, optional demo data, bi refresh) at start-up unless `MIGRATE_ON_START=0`, so it can never serve an unmigrated database; `/healthz` reports `schema` and answers 503 while migrations are pending.

## [0.2.0] — Sprint 1 (30 Sep 2026)

### Added
- Technical roles `hydrologist`, `hydrogeologist` (approve observations, MFA) and `technician` (field entry).
- Grade, qualifiers and graded-by/at on every observation table; qualifier lookup (`ref.Qualifier`).
- Approval periods (`obs.ApprovalPeriod`) with `obs.services.approve_period`; `obs.services.regrade` with history.
- `RecordHistory.method` (correction, gap fill, estimate, shift, regrade).
- Well status events (drilled → abandoned) that keep the well's current flags in step; depth checks on lithology and casing; screen flag on casing; extra pump-test fields with derived specific capacity.
- Site master record: instruments, installations, reference-point history, site visits — as admin inlines on wells and stations.
- `manage.py load_reference_data` with `data/reference/*.csv` (parishes, basins, WMUs, hydrostratigraphic units, rivers, qualifiers); runs on every deploy.
- `manage.py seed_demo_data` — twelve months of synthetic demo data and six demo users; `DEMO_DATA=1` on Railway.
- Licensing dashboard views in the `bi` schema, `apps.reports.services` (fetch/refresh), `manage.py refresh_bi_views`; beat refresh every 5 minutes.
- API: `grade` and `qualifiers` on well levels and abstraction.
- Browser journey script `scripts/browser_journeys.py` (Playwright).
- Docs: ADR-0001, `docs/hydrology.md`, this changelog.

### Changed
- ruff pydocstyle (`D`, Google convention) enforced in CI; every module, class and public function documented.
- `PublishedQuerySet.visible_to` uses `roles.UNAPPROVED_DATA_ROLES` (hydrologists see working data).
- MFA now also required for hydrologist and hydrogeologist.

## [0.1.0] — starter (25 Sep 2026)
- Accounts, workflow engine, category framework, licence application and data submission applications, REST API, Tailwind v4 UI with light/dark theme, Railway staging pipeline.
