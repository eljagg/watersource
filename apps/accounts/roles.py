"""Fixed role names (ToR H.i–v, F.5; design doc 14 §5 for the technical roles).

Roles are Django groups. Administrators may add stage-specific approver groups
(e.g. ``approver:hydrogeology``) in the admin; the workflow stage points at the
group, so no code change is needed for a new review stage.

The three technical roles added in Sprint 1 come from the hydrologist
provisions (design doc 14):

* ``hydrologist`` / ``hydrogeologist`` — WRA technical staff who grade,
  qualify and approve observations for their discipline and complete the
  Technical Assessment stage of a licence application (Sprint 2). They see
  working (unapproved) observations, like reviewers.
* ``technician`` — field staff who record visits, readings and instrument
  events. Technicians can enter and edit working data but cannot approve
  anything.
"""

CLIENT = "client"
UPDATER = "updater"
REVIEWER = "reviewer"
APPROVER = "approver"
ADMINISTRATOR = "administrator"
DATA_MIGRATION = "data_migration"
BI_ANALYST = "bi_analyst"
HYDROLOGIST = "hydrologist"
HYDROGEOLOGIST = "hydrogeologist"
TECHNICIAN = "technician"
WALL_DISPLAY = "wall_display"
FINANCE = "finance"  # Finance & Accounts Division: downloads the licence / abstraction export for fee calculation (ToR H.xiii)

ALL = [CLIENT, UPDATER, REVIEWER, APPROVER, ADMINISTRATOR, DATA_MIGRATION, BI_ANALYST, HYDROLOGIST, HYDROGEOLOGIST, TECHNICIAN, WALL_DISPLAY, FINANCE]
STAFF_ROLES = [UPDATER, REVIEWER, APPROVER, ADMINISTRATOR, DATA_MIGRATION, BI_ANALYST, HYDROLOGIST, HYDROGEOLOGIST, TECHNICIAN, FINANCE]
#: Roles that may download the Finance export (licences and abstraction volumes with licensee names).
FINANCE_EXPORT_ROLES = [FINANCE, ADMINISTRATOR]
#: Roles that may see observations before they are approved (working / in review).
UNAPPROVED_DATA_ROLES = [REVIEWER, APPROVER, ADMINISTRATOR, HYDROLOGIST, HYDROGEOLOGIST]
#: Roles that may approve observations (set grade/qualifiers and open approval periods).
OBSERVATION_APPROVER_ROLES = [APPROVER, ADMINISTRATOR, HYDROLOGIST, HYDROGEOLOGIST]
#: Roles that may see ``restricted`` records and the exact coordinates / engineering
#: details of public-supply sources and licensee particulars (Methodology §4A, ADR-0002).
RESTRICTED_DATA_ROLES = [APPROVER, ADMINISTRATOR, HYDROLOGIST, HYDROGEOLOGIST, REVIEWER]
#: who may download the GIS package (exact coordinates of every site): technical staff and the GIS unit (v0.7.0)
GIS_EXPORT_ROLES = [ADMINISTRATOR, HYDROLOGIST, HYDROGEOLOGIST, BI_ANALYST, DATA_MIGRATION]

DESCRIPTIONS = {
    CLIENT: "Self-registered external user: applies for licences, submits data, sees own records and public data.",
    UPDATER: "WRA staff who browse public sections and enter/update data (ToR F.5).",
    REVIEWER: "WRA staff who review pending submissions and applications at a workflow stage.",
    APPROVER: "WRA staff who approve, reject, return and classify at a workflow stage. MFA required.",
    ADMINISTRATOR: "Full access: users, roles, categories, workflows, integrations. MFA required.",
    DATA_MIGRATION: "Temporary role for the migration team: staging loads and reconciliation.",
    BI_ANALYST: "Ad hoc SQL in Metabase over the bi schema.",
    HYDROLOGIST: "Surface-water specialist: grades and approves streamflow observations, technical assessment of applications.",
    HYDROGEOLOGIST: "Groundwater specialist: grades and approves well observations, technical assessment of applications.",
    TECHNICIAN: "Field staff: site visits, readings, instrument events and gaugings. No approval rights.",
    WALL_DISPLAY: "Kiosk account for the wall display: may open /wall/ only; sees public-classified aggregates, never personal data.",
}
