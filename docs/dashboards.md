# Dashboards and the wall display

Design reference: doc 13 *Dashboard design*. Sprint 2a, 4 Oct 2026.

## What exists

| URL | Who | What |
|---|---|---|
| `/dashboards/` | WRA staff, BI analysts | index of the four dashboards |
| `/dashboards/<slug>/` | same | desk view inside the normal site (phone to 4K, light/dark) |
| `/dashboards/<slug>/data/` | same (`?wall=1` also for the kiosk role) | JSON: panel specification + rows of every `bi` view the dashboard reads |
| `/wall/` | staff and the `wall_display` role | full-screen rotation (`?d=<slug>` to start on one, `?theme=light`) |

Slugs: `licensing`, `monitoring`, `submissions`, `executive`.

## How a number gets on the wall

1. Celery beat runs `apps.reports.tasks.refresh_bi_views` every five minutes (also run by the deploy/start-up schema step). Every materialised view in `apps.reports.services.BI_VIEWS` is refreshed, concurrently where possible, so the wall never reads a half-built view.
2. `apps/reports/dashboards.py` declares each dashboard: KPI tiles (which view, which column, unit, format) and panels (which view, which chart idiom, which columns, options such as reference lines and limits). This file is the single source of truth — change a panel there and the desk page, the wall and the JSON change together.
3. `static/js/dashboards.js` renders the panels with Apache ECharts (vendored in `static/js/echarts.min.js`; no CDN, so the Content Security Policy stays `'self'`). Colours come from the `--ds-*` CSS custom properties in `frontend/app.css`, so one chart definition works in both themes; a theme toggle re-renders without a refetch.

Chart idioms (doc 13 §4.4): `kpi`, `hbar` (ranked bars use the sequential ramp), `vbar`, `line` (optional dashed reference line and 12-month average), `stacked` (vertical or horizontal, optional 100 % mode), `status` (count tiles in the reserved status colours), `list` (ranked items with a pill).

## Classification and personal data

Dashboards read only `bi` aggregates. None carries coordinates, applicant names, submitter names or licensee particulars; the "Needs attention" list shows reference, source and parish. Panels carry a `wall_safe` flag (all true today) so a future staff-only panel is excluded from `/wall/` by design.

## Setting up the wall

1. Create an account for the kiosk (e.g. `wall@wra.gov.jm`, user type *staff*), give it only the `wall_display` group. It can open `/wall/` and nothing else, and the session idle timeout does not sign it out while the page is polling.
2. On the kiosk mini-PC open `https://<host>/wall/` in a browser in kiosk mode (Chrome: `--kiosk --incognito https://<host>/wall/`, sign in once). For a 4K screen the layout scales ×1.5 automatically.
3. Rotation and refresh intervals are `WATERSOURCE["WALL_ROTATE_SECONDS"]` (60) and `WATERSOURCE["WALL_REFRESH_SECONDS"]` (300) in settings; arrow keys step between dashboards.

## Adding a panel

Add a `Panel(...)` to the dashboard in `apps/reports/dashboards.py` naming an existing `bi` view and an idiom. If a new view is needed, add it in a `reports` migration (with a unique index for concurrent refresh) and append its name to `services.BI_VIEWS` after any view it depends on. Thresholds used by `bi.wq_exceedances_90d` (nitrate 50, chloride 250, pH 6.5–8.5, turbidity 5 NTU, TDS 1000, conductivity 1500, hardness 500) are guideline values for the demo; WRA confirms them at the design workshop.
