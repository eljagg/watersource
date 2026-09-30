# Hydrology handbook — observation QA and the site master record

Audience: WRA hydrologists, hydrogeologists, technicians and the handover team.
Design reference: doc 14 *Hydrologist functions and provisions*; ADR-0001.

## Roles

| Role | Can | Cannot |
|---|---|---|
| technician | enter working observations, site visits, instrument events; grade working rows | approve anything |
| hydrologist / hydrogeologist | everything a technician can, plus grade/re-grade approved rows (with reason), approve periods, see working data; MFA required | administer users or categories |
| approver / administrator | as before, plus observation approval | — |

Roles are Django groups (`manage.py bootstrap_roles`).

## Observation columns

Every observation row (well levels, station readings, abstraction, water quality) has:

* `approval_state` — pending (*working*), under_review (*in review*), approved, rejected
* `classification` — staff_only or public (applied at approval)
* `grade` — good, fair, poor, estimated, missing, or blank (ungraded)
* `qualifiers` — list of codes from **Reference data → Qualifiers** (e.g. `PUMPING`, `FLOOD`, `EQUIP`)
* `graded_by`, `graded_at`

Only approved rows reach public views (`bi.public_*`), exports and dashboards.

## Approving a period

`apps.obs.services.approve_period(series, site, starts_at, ends_at, user, remarks)`
approves every unapproved row of that series at that site in the window and stores an
`ApprovalPeriod`. The Sprint 3 hydrologist screens call this; until then it is
available from `manage.py shell`. Periods are listed under **Observations → Approval
periods** in the admin.

## Correcting or re-grading approved data

`apps.obs.services.regrade(row, grade, qualifiers, user, reason)` writes a
`RecordHistory` entry with method `regrade`. Value corrections still go through a
correction submission (workflow `correction`) which writes method `correction`; gap
fills and datum shifts use `gap_fill` and `shift`.

## Site master record

On each well and station page in the admin:

* **Status events** (wells) — dated drilled / completed / pump installed / licensed /
  abandoned / replaced… Saving an event updates the well's current-status flags.
* **Lithology, casing (with screens), pump tests** — depth intervals are checked
  (`depth_to ≥ depth_from`); specific capacity is derived from the constant-rate test.
* **Reference points** — measuring-point history (elevation, height above ground, valid
  from/to). Add a new row when the casing is cut or the gauge is re-set.
* **Instruments** — register under **Reference data → Instruments**; an installation row
  links an instrument to a site for a period, with its sensor offset.
* **Site visits** — who, when, purpose, findings, actions, follow-up due date, optional
  photo. The full log is under **Reference data → Site visits**.

## Reference data and demo data

* `manage.py load_reference_data` seeds parishes, basins, WMUs (partial — confirm
  with WRA), hydrostratigraphic units, rivers and qualifiers from
  `data/reference/*.csv`. Re-run after editing a CSV; rows are matched on `code`.
* `manage.py seed_demo_data` builds twelve months of synthetic `DEMO` data and six
  `demo.*` users (`--wipe` removes it). On Railway set `DEMO_DATA=1`.

## BI views for the Licensing dashboard

`bi.licensing_kpis`, `bi.licensing_pipeline`, `bi.applications_monthly`,
`bi.licence_expiry`, `bi.licence_active_by_parish`, `bi.licensing_monthly` —
refreshed every 5 minutes by Celery beat and by `manage.py refresh_bi_views`.
`apps.reports.services.licensing_dashboard()` returns them as dicts for the Sprint 3
dashboard page.
