# Technical assessment, conditions and the WMU balance sheet

Design doc 14 §4; stakeholder model: Permits & Licences Unit owns applications and licences, Planning & Investigation owns basins, WMUs and aquifers.

## Workflow

Licence application: Intake review (reviewer) → **Technical assessment (hydrologist)** → Licensing officer (approver) → Director approval (approver). The engine asks the application `workflow_can_advance()` before every approval; at the technical-assessment stage it returns a blocker until a `TechnicalAssessment` exists, and the review panel links to the assessment form.

## The assessment form (`/licensing/applications/<ref>/assessment/`)

Resource (WMU, aquifer — defaulted from the well), assessment (impact, recommendation, recommended daily volume, findings) and conditions (standard conditions from the library, pre-ticked where `is_default`; extra conditions one per line). The WMU balance for the selected unit is shown and snapshotted onto the record (`wmu_safe_yield_m3_d`, `wmu_allocated_m3_d`, `wmu_reported_m3_d`). Saving sets `application.wmu` and writes `licence.assessment_recorded` to the audit trail.

## Final approval

The licensing officer's "Daily volume granted" defaults to the recommended volume. `Licence.issue()` copies the rendered conditions (`{volume}`, `{source}` filled) onto `Licence.conditions`, which the licence page prints. WRA edits the library at Admin console → Licensing → Licence conditions; changing a library entry never changes a licence already issued.

## WMU balance sheet (`/licensing/balance/`, `bi.wmu_balance`)

Per WMU: safe yield (set on the WMU in the admin, cite the Master Plan source), licensed = active licences' granted daily volume (licence WMU, else its well's WMU), reported = approved abstraction over the last 12 months divided by the days covered, pending = requested volume of open applications, headroom and utilisation. Amber above 85 %, red when allocation plus pending exceeds the safe yield.
