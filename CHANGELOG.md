# Changelog

All notable changes to WaterSource Jamaica. Dates are the date the change landed on `main`.

## [0.7.0] — 6 Oct 2026

Maps (stakeholder-model plan, "maps and ArcGIS file export").

### Added
- **Map page** `/maps/` (Home tile "Map"; link from the WMU balance sheet): Leaflet (vendored, no CDN) with parishes, basins, WMUs coloured by licensed utilisation, aquifers, and wells/stations/springs with click-through details. Public-supply sources are coarsened for anyone outside the restricted-data roles, as in the API.
- **GeoJSON layers** `/maps/layers/<layer>.geojson` in WGS 84, simplified for the browser.
- **GIS package** `/maps/export/`: one GeoPackage (parishes, basins, WMUs, aquifers, wells, stations, springs, licences) in JAD2001 or WGS 84, built with `ogr2ogr`, cached ten minutes, audited; technical/GIS roles only (`GIS_EXPORT_ROLES`).
- **Boundary loader** `load_boundaries`: WRA GeoJSON files per layer; geoBoundaries parishes (CC BY 4.0) by default; `--demo-shapes` Voronoi stand-ins for basins/WMUs tagged "demonstration stand-in". `geom_source` on every boundary table. Runs on every deploy (demo shapes when `DEMO_DATA=1`/`reseed`).
- Settings `MAP_TILES_URL` / `MAP_TILES_ATTRIBUTION` (OpenStreetMap on staging; ArcGIS Enterprise basemap on WRA's server); CSP `img-src` follows the tile host.

### Notes
- Boundaries for basins/WMUs/aquifers are placeholders until WRA supplies its shapefiles (doc 17 §7); parishes are real.
- The admin console map widget (drawing boundaries by hand) is not included: Django's widget loads OpenLayers from a CDN, which the content-security policy blocks. Boundaries are loaded from files instead.

## [0.6.1] — 5 Oct 2026

### Changed
- **Layout and type scale, app-wide** (Omar, 5 Oct 2026): page content now spans the same width as the navigation bar (max-w-7xl instead of 6xl); the Tailwind v4 type scale is redefined in one place (`frontend/app.css` `@theme`) so body/table text is 16 px (was 14), labels 14 px (was 12), card titles 20 px, page titles 32 px. Navigation tabs keep fixed pixel sizes so seven equal tabs still fit. Finance export page widened to match forms.
- **Dates show the day of the week** wherever a date is displayed (`Mon 05 Oct 2026 15:58`). Review queue gains a **Submitted** column and shows the date and time next to "waiting at this stage".
- Application page: a draft says plainly that it has not been submitted and cannot be reviewed; a submitted application links staff straight to its review item.

## [0.6.0] — 5 Oct 2026

Package 1 of the WRA stakeholder model (design doc 17): ownership by unit.

### Added
- **Ownership by unit.** Workflow stages and submission categories carry the WRA unit that owns them (`WorkflowStage.owning_unit`, `DataCategory.owning_unit`; editable in the admin console). Reference and observation families are mapped to their owning unit in `apps/accounts/ownership.py` (Resource Monitoring: wells, stations, springs, levels, readings, quality; Permits & Licences: applications, licences, conditions, abstraction returns; Planning & Investigation: basins, WMUs, aquifers, model runs).
- **Enforcement.** Only members of the owning unit may act on an item at a stage that has an owner; other units read. The review queue shows only items the user's unit may act on, and its empty state says so. Superusers are exempt. Staff with no unit cannot approve owned items — assign a unit in the admin console.
- Seeded defaults (filled only when blank, so WRA's own choices stand): licence stages Intake, Licensing officer and Director → Permits & Licences Unit; Technical assessment → Resource Monitoring Unit; categories: water abstraction → PLU, water quality → RMU, model output → PIU.
- WRA unit admin page shows everything the unit owns (data families, categories, stages).
- **Home** tab in the navigation (first tab; active on the landing page only).
- Demo account `demo.monitoring@wra-demo.local` (Resource Monitoring; reviewer + approver) so RMU-owned submissions have a reviewer in the demo set. Password as the other demo accounts.

### Changed
- `demo.reviewer` / `demo.approver` (Permits & Licences) no longer see water-quality submissions in their queue — those belong to Resource Monitoring. Use `demo.monitoring` for them.

## [0.5.3] — 5 Oct 2026

### Fixed
- Review panel: **Request information**, **Reject**, **Return** and **Add comment** appeared to do nothing. The panel refreshed itself in place, so the reason an action was refused (a comment is mandatory for all of them) and the success message were never shown. Every action now reloads the page with a clear outcome message and the updated history; actions that move the item away from the user's stage (approve, reject, return, request information) take the user back to the review queue.
- Review panel: the comment box is marked required (Approve is the only action that works without one), and an item that is waiting on the submitter says so instead of looking untouched.

### Added
- "← Back to review queue" link at the top of every workflow item.

## [0.5.2] — 5 Oct 2026

### Changed
- **`DEMO_DATA=1` is now the only setting needed.** On every deploy the demo set is kept, the demo accounts are refreshed, and the demo set is *upgraded* to the current release without a rebuild: safe yields on the demo WMUs, demo aquifers, conditions on demo licences, and two live applications moved to the Technical assessment stage (one with its assessment already recorded). `DEMO_DATA=reseed` remains available only as an optional full rebuild.
- Demo data: two of the four open applications now sit at the Technical assessment stage, so the hydrologist's review queue is not empty.
- Review queue: the empty-state message names the stage(s) the signed-in user acts at and explains that items arrive once the previous stage approves them.

### Fixed
- `DEMO_DATA=reseed` failed when a demo technical assessment referenced a demo aquifer (protected foreign key); the demo aquifers are now removed after the applications.

## [0.5.1] — 5 Oct 2026

### Fixed
- With `DEMO_DATA=1` the demo **accounts** are now brought up to date on every deploy even though the demo data is kept — so `demo.hydrologist` and `demo.finance` exist on an environment seeded before those roles were added. Orphaned review-queue items whose submission was removed by an earlier re-seed are cleaned up at the same time (they showed as a history-only page with no data card).

## [0.5.0] — 5 Oct 2026 — Sprint 2b, part 2

### Added
- **Technical assessment stage** (design doc 14 §4). The second stage of the licence workflow is now "Technical assessment", acted on by the `hydrologist` role, and cannot be approved until the assessment is recorded: WMU and aquifer, impact, recommendation (grant / reduced / more information / refuse), recommended daily volume, standard conditions ticked from the library plus free-text conditions, and findings. The WMU balance (safe yield, licensed, reported 12-month average, pending, utilisation) is shown on the form and snapshotted on the record. At final approval the licensing officer's volume defaults to the recommendation and the conditions are printed on the licence (`Licence.conditions`, shown on the licence page).
- **Conditions library** (Admin console → Licensing → Licence conditions): ten standard conditions seeded with `{volume}` / `{source}` placeholders, categories, surface/ground applicability, default flag and order; WRA edits freely.
- **Aquifers** (Admin console → Reference data → Aquifers): named aquifers with type, hydrostratigraphic unit, WMU/basin, safe yield and saline-risk flag; wells link to their aquifer. **WMU safe yield** and source on each watershed management unit.
- **WMU balance sheet** at Licence applications → WMU balance (home tile for staff) and `bi.wmu_balance` for dashboards: safe yield vs active licences vs reported abstraction vs pending requests, with headroom and utilisation; rows over 85 % amber, over 100 % with pending red.
- **MFA backup codes**: ten one-time eight-digit codes issued right after enrolment and on demand from the account page; accepted at the code step when the phone is unavailable; "Reset authenticator (new phone)" with a confirm page. Audit: `auth.mfa_backup_codes_issued`, `auth.mfa_backup_code_used`, `auth.mfa_reset`.
- **Finance export** for the Finance & Accounts Division: new `finance` role; `/exports/finance/` page with the licence register and abstraction-returns CSVs for a period; API `GET /api/v1/exports/finance/licences/` and `/abstraction/?from=&to=` (JSON, `?download=csv`) for Finance's own system via API key. Every download is audited (`export.finance_*`). Demo user demo.finance@wra-demo.local.
- Demo data: safe yields on the demo WMUs, a demo aquifer per basin, conditions on demo licences.

## [0.4.4] — 5 Oct 2026

### Changed
- Reverted the blue fill from 0.4.3 (Omar, 5 Oct): tiles are back to the original card colour with the thin metallic red border; navigation tabs are outlined in red, all the same size (fixed width and height, two-line labels), and only the **active** tab is filled blue. The user-name link is plain text again. Header content width widened to 7xl so six tabs fit on a 1280-px screen; the user name shows from 1280 px up.

## [0.4.3] — 5 Oct 2026

### Changed
- **Home-page tiles and navigation tabs** are now solid blue with a thin metallic red border (Omar, 5 Oct). Both colours are set in Admin console → Site settings and audit → Site branding → Colours (tile colour, border colour) and apply site-wide through CSS variables — no redeploy.
- **Copyright line** in the footer: "© {year} {organisation}. All rights reserved." by default, with the year filled in automatically every 1 January; the wording is editable in Site branding (leave empty to hide).

## [0.4.2] — 5 Oct 2026

### Changed
- **Demo data is seeded once, not on every deploy.** `DEMO_DATA=1` now seeds only when the demo set is absent (`seed_demo_data --if-missing`); `DEMO_DATA=reseed` rebuilds it. Together with 0.4.1 this means deploys never touch accounts, enrolments or demo records again.

### Added
- **WRA units and Super Users** from the FCC stakeholder–system model (5 Oct): `accounts.Unit` seeded by `bootstrap_roles` with WRA's real branch names (Resource Monitoring, Permits & Licences, Planning & Investigation, Computer & GIS, Finance & Accounts, Information & Documentation, HR, Office Services, Managing Director's Office), division, operating flag, primary modules and Super User expectation; `User.unit` and `User.is_super_user` (informational, Work Plan A12) in the admin user list/filters and on the profile page. Demo staff are assigned to units; three are Super Users.

## [0.4.1] — 5 Oct 2026

### Fixed
- **Re-seeding the demo data no longer deletes the demo accounts.** `seed_demo_data --force` (run on every deploy with `DEMO_DATA=1`) used to delete and recreate `demo.*` users, which cascaded to their authenticator enrolments — so after each deploy the two-factor set-up page came back and the code in Google Authenticator was refused. Users are now kept and refreshed (password, role, flags); their TOTP devices survive. One more scan is needed after this deploy; none after that.

## [0.4.0] — 5 Oct 2026 — Sprint 2b, part 1

### Added
- **Anomaly flags for reviewers** (`apps/submissions/anomalies.py`, docs/data-quality.md): every submission is checked against the site's approved record — out-of-character values (robust z > 3.5), big jumps, duplicates of approved rows, future dates, flat lines, abstraction volumes out of pattern for the licence. Findings are plain-English messages on the row; rows move to *Flagged for review*; the submission page shows a count. Nothing is rejected automatically.
- **Model output category** (design doc 15 §3.1): `obs.ModelRun` (model, scenario, basin, calibration NSE/KGE, notes) and `obs.ModelOutput` (run × element × variable × time), the seeded *Model output* data category with CSV template, a `model_run` reference field type, and `manage.py import_model_output` with SWAT+ (`channel_sd_day.txt`) and Wflow (gauge CSV) adapters. Results are provisional until a reviewer approves them and never mix with observations.
- **Source profiling for Milestone 3**: `manage.py profile_source` writes the Data Quality Assessment Report body (Markdown) and JSON from legacy CSV/XLSX extracts — types, completeness, placeholder blanks, date formats, spaces/case variants, outliers, duplicate rows, candidate keys, and match rates against WaterSource reference tables with the unmatched work queue.
- **GIS desk** (docs/gis.md): `manage.py setup_gis_reader` creates the read-only `gis_reader` role (personal-data tables revoked; `--public-only` variant sees coarsened public views), `deploy/gis/pg_service.conf.example`, `deploy/gis/WaterSource.qgz` (all layers as `service=watersource`, no credentials), and `build_qgis_project.py` to regenerate it inside QGIS with relations and the time slider.
- Demo data: a SWAT+-style model run with a year of daily simulated discharge; a pending water-quality submission that trips the anomaly checks; water-quality history extended to three years.

### Fixed
- Governance panel on the Executive dashboard now counts the audit actions the application really emits (`dpa.subject_access_export`; the nightly retention sweep now logs `retention.sweep`).
- Dashboards index wording follows the admin-set data-refresh interval instead of a fixed "five minutes".
- Submission detail no longer lists empty fields in the Data column.

## [0.3.4] — 5 Oct 2026

### Added
- **Site branding** in the admin console (Site settings and audit → Site branding): organisation name, application name, tagline, footer line, and a logo upload (PNG/JPEG/WebP/SVG ≤ 512 KB, optional dark-background variant). The logo replaces the droplet mark in the header, on the wall display and in the admin console header; names flow through every page title, the footer and the wall sub-title. Stored in the database so every container serves the same image; changes show within a minute; recorded in the audit trail (`branding.changed`).

### Changed
- Admin console header reads "WaterSource admin console" (follows the application name) instead of "Django administration"; the "Core" section is now "Site settings and audit".

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
