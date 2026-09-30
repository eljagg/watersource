# ADR-0001 — Observation quality grades, qualifiers and approval periods

Date: 30 Sep 2026 · Status: accepted · Sprint 1

## Context

The ToR (H.ix–x, H.xvii–xxi) requires every record to carry an approval state and a
classification, and every correction to approved data to be traceable. WRA's
hydrologists additionally work the way Aquarius Time-Series does: each value carries a
*grade* (good / fair / poor / estimated / missing) and *qualifiers* (pumping, flood,
equipment fault…), and data is approved in *periods*, not row by row
(design doc 14, §3.2). Migrated Aquarius data must keep those states.

## Decision

1. **One state machine, not two.** `PublishableModel.approval_state` already has
   `pending`, `under_review`, `approved`, `rejected`. The hydrologists' "working" is
   `pending` and "in review" is `under_review`; we did not add a parallel field.
2. **`core.QualityMixin`** adds `grade`, `qualifiers[]`, `graded_by`, `graded_at` to
   every observation table (`obs.WellWaterLevel`, `StationReading`,
   `AbstractionRecord`, `WaterQualitySample`). Qualifier codes are text, taken from
   the `ref.Qualifier` lookup, stored denormalised so exports and Metabase need no
   join.
3. **`obs.ApprovalPeriod`** records a site + series + time window approved as a
   block, with who/when and the row count; `obs.services.approve_period` flips the
   rows and writes the period in one transaction.
4. **`obs.RecordHistory.method`** distinguishes correction, gap fill, estimate,
   datum shift and re-grade. Re-grading an approved row goes through
   `obs.services.regrade`, which requires an observation-approver role and a reason.
5. **Roles.** `hydrologist`, `hydrogeologist` (approve observations, MFA required)
   and `technician` (enter working data, no approval).

## Consequences

* Public views, exports and dashboards keep filtering on `approval_state = 'approved'`;
  grade is available to them as an extra column.
* Aquarius sync (Sprint 4) maps Aquarius grade codes and approval levels onto these
  columns directly.
* A future "approval levels" requirement (e.g. provisional vs final) would be a new
  `ApprovalState` value, not a new table.
