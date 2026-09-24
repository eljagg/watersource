"""Fixed role names. Administrators may add stage-specific approver groups
(e.g. 'approver:hydrogeology') in the admin; the workflow stage points at the group."""
CLIENT = "client"
UPDATER = "updater"
REVIEWER = "reviewer"
APPROVER = "approver"
ADMINISTRATOR = "administrator"
DATA_MIGRATION = "data_migration"
BI_ANALYST = "bi_analyst"

ALL = [CLIENT, UPDATER, REVIEWER, APPROVER, ADMINISTRATOR, DATA_MIGRATION, BI_ANALYST]
STAFF_ROLES = [UPDATER, REVIEWER, APPROVER, ADMINISTRATOR, DATA_MIGRATION, BI_ANALYST]

DESCRIPTIONS = {
    CLIENT: "Self-registered external user: applies for licences, submits data, sees own records and public data.",
    UPDATER: "WRA staff who browse public sections and enter/update data (ToR F.5).",
    REVIEWER: "WRA staff who review pending submissions and applications at a workflow stage.",
    APPROVER: "WRA staff who approve, reject, return and classify at a workflow stage. MFA required.",
    ADMINISTRATOR: "Full access: users, roles, categories, workflows, integrations. MFA required.",
    DATA_MIGRATION: "Temporary role for the migration team: staging loads and reconciliation.",
    BI_ANALYST: "Ad hoc SQL in Metabase over the bi schema.",
}
