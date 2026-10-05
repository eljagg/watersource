# Changelog

All notable changes to WaterSource Jamaica. Dates are the date the change landed on `main`.

## [0.3.3] — 5 Oct 2026

### Changed
- **Two-factor set-up redesigned**: a scannable QR code (inline SVG, rendered server-side — nothing leaves the server), three plain steps, "Can't scan? Enter the key manually" with the key in groups of four, a large numeric code box that accepts `123 456`, and a "Not now — sign out" exit. The account is labelled **WaterSource Jamaica (email)** in Google / Microsoft Authenticator (`OTP_TOTP_ISSUER`).
- The code-entry page at sign-in has the same treatment and a lost-phone note.

### Fixed
- **"Forbidden (403) CSRF verification failed" on Sign out.** A stale sign-out form (page open across an idle time-out, or a second sign-in in another tab) now simply signs the user out and returns to the sign-in page. Any other CSRF failure shows a plain-language "That page had expired" page instead of Django's default; each failure is recorded in the audit trail (`auth.csrf_failed`) with the path and reason so the cause can be seen in the admin console.

## [0.3.2] — 5 Oct 2026

### Added
- **Display settings** in the admin console (Business intelligence → Display settings): seconds per dashboard, page refresh seconds, data-refresh minutes, dashboards shown and their order, wall theme, clock. No redeploy to change timing.
- Wall controls in the header: ‹ previous · ⏸ pause/resume · › next · **Exit wall**; dots are clickable; keyboard ← → space Esc; footer shows which dashboard is next.
- Near-real-time data: the bi views refresh on demand when a dashboard or the wall is opened and the data is older than the admin-set interval (60-second lock), so staging stays current without a Celery worker; the beat task now checks every minute against the same setting. Desk dashboards re-fetch live on the page-refresh interval; KPI tiles link through to the underlying lists.

## [0.3.1] — 5 Oct 2026

### Changed
- Navigation: every staff page reachable without typing a URL — header gains **Admin console** (accounts with admin access) and the mobile menu gains **Wall display**; staff home page shows a "Staff tools" row (Review queue, Dashboards, Wall display, Admin console, API docs); the wall footer links back to Dashboards.

## [0.3.0] — Sprint 2a (4 Oct 2026)

### Added
- Four dashboards (`/dashboards/`): Licensing overview, Water resources monitoring, Data submissions and quality, Executive and compliance summary — Apache ECharts (vendored, CSP-clean), light/dark, phone to 4K; declarative panel specs in `apps/reports/dashboards.py`; JSON per dashboard at `/dashboards/<slug>/data/`.
- Wall display `/wall/`: full-screen kiosk rotating through the four dashboards every 60 s, data refresh every 5 min, dark by default (`?theme=light`), arrow keys to step; `wall_display` role for the kiosk account.
- Twenty new `bi` views (migration 0003): application stages, longest-waiting items, well/station percentile status (USGS bands), groundwater index by basin, abstraction share by licence, water-quality exceedances, submissions by month/channel/category, review backlog age, validation failures, observation grades, licences by status, service-standard trend, expiries next 12 months, governance and executive KPIs.
- Restricted classification (Methodology §4A, ADR-0002): `restricted` level; `is_public_supply` on wells and stations; coordinates coarsened to 1 km and elevation withheld for public-supply sources in the API, ArcGIS export and `bi.public_*` views; classification and flag changes audited.
- Demo data: three years of well levels with declining/recovering/stale wells, over-limit licences, water-quality exceedances, thirteen months of submissions with validation outcomes, public-supply flags.

### Changed
- `staff_only` relabelled "Internal (WRA staff)"; `visible_to` hides restricted rows from staff without a restricted-data role.
- Dashboards link in the header for staff.

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
