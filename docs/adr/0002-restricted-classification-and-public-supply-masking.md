# ADR-0002 — Restricted classification and masking of public-supply source details

Date: 4 Oct 2026 · Status: accepted · Sprint 2a

## Context

Methodology §4A of FCC's bid commits to a three-level classification —
Public / Internal / Restricted — under which the exact coordinates and
engineering details of public-supply sources, and licensee particulars, are
restricted by default, excluded from public dashboards, the API and exports,
audit-logged, and changeable by WRA through the admin console. The ToR (H.ix–x)
already requires classification at approval; this adds the third level and a
field-level rule.

## Decision

1. `core.Classification` gains `restricted`. `staff_only` is relabelled
   "Internal (WRA staff)". `PublishedQuerySet.visible_to` hides restricted rows
   from everyone outside `roles.RESTRICTED_DATA_ROLES` (reviewer, approver,
   administrator, hydrologist, hydrogeologist).
2. `ref.Well` and `ref.StreamflowStation` gain `is_public_supply`. A
   public-supply site may still be classified `public` — its name, parish and
   status are not secret — but `core.restrict.mask_site` coarsens its coordinates
   to the centre of a 1 km grid cell (`WATERSOURCE["PUBLIC_COORDINATE_GRID_M"]`)
   and withholds elevation for any caller without a restricted-data role. The
   API serializers, the ArcGIS GeoJSON export and the `bi.public_wells` /
   `bi.public_stations` views apply the same rule, so the three channels can
   never disagree. Engineering detail (lithology, casing, pump tests, reference
   points, instruments) is not exposed outside the admin at all.
3. Licensee particulars (`ref.Party`) appear only on staff pages; the licence API
   is staff-only; the dashboards' "needs attention" list shows reference, source
   and parish, never the applicant.
4. Every change to `classification` or `is_public_supply` writes an `AuditLog`
   entry (`classification.changed`, `site.public_supply_changed`). Both fields
   are edited in the Django admin — the "admin console" of the methodology.

## Consequences

* Dashboards read only `bi.*` aggregates; none carries coordinates or names, so
  the wall display is safe by construction and the `wall_display` role can open
  nothing else.
* Which sources count as public supply is a WRA decision; the flag defaults to
  false and the migration workshop sets it from NWC's intake list.
* Coarsening is 1 km today; if WRA wants a different grid, it is one setting.
