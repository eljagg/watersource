"""Governance panel: count the audit actions the application actually emits (tracker 'governance audit action names').

``dpa.subject_access_export`` (profile export) and ``retention.sweep`` (nightly
sweep, now logged by ``accounts.tasks.retention_sweep``) replace the placeholder
names used in 0003.
"""
from django.db import migrations

SQL_UP = r"""
DROP MATERIALIZED VIEW IF EXISTS bi.governance_kpis;
CREATE MATERIALIZED VIEW bi.governance_kpis AS
SELECT 1 AS id,
       (SELECT count(*) FROM core_auditlog WHERE action = 'dpa.subject_access_export' AND at >= now() - interval '12 months') AS subject_access_exports_12m,
       (SELECT count(*) FROM core_auditlog WHERE action = 'retention.sweep' AND at >= now() - interval '12 months') AS retention_sweeps_12m,
       (SELECT count(*) FROM axes_accessattempt) AS lockouts_active,
       (SELECT coalesce(sum(failures_since_start), 0) FROM axes_accessattempt) AS failed_sign_ins_blocked,
       (SELECT count(*) FROM core_auditlog WHERE action = 'classification.changed' AND at >= now() - interval '12 months') AS classification_changes_12m,
       (SELECT count(*) FROM obs_recordhistory WHERE approved_at >= now() - interval '12 months') AS corrections_approved_12m,
       now() AS refreshed_at;
CREATE UNIQUE INDEX IF NOT EXISTS bi_governance_kpis_uq ON bi.governance_kpis (id);
"""

SQL_DOWN = r"""
DROP MATERIALIZED VIEW IF EXISTS bi.governance_kpis;
CREATE MATERIALIZED VIEW bi.governance_kpis AS
SELECT 1 AS id,
       (SELECT count(*) FROM core_auditlog WHERE action = 'account.export' AND at >= now() - interval '12 months') AS subject_access_exports_12m,
       (SELECT count(*) FROM core_auditlog WHERE action = 'retention.sweep' AND at >= now() - interval '12 months') AS retention_sweeps_12m,
       (SELECT count(*) FROM axes_accessattempt) AS lockouts_active,
       (SELECT coalesce(sum(failures_since_start), 0) FROM axes_accessattempt) AS failed_sign_ins_blocked,
       (SELECT count(*) FROM core_auditlog WHERE action = 'classification.changed' AND at >= now() - interval '12 months') AS classification_changes_12m,
       (SELECT count(*) FROM obs_recordhistory WHERE approved_at >= now() - interval '12 months') AS corrections_approved_12m,
       now() AS refreshed_at;
CREATE UNIQUE INDEX IF NOT EXISTS bi_governance_kpis_uq ON bi.governance_kpis (id);
"""


class Migration(migrations.Migration):
    """Recreate ``bi.governance_kpis`` with the real action names."""

    dependencies = [("reports", "0004_display_settings"), ("obs", "0005_model_output")]
    operations = [migrations.RunSQL(SQL_UP, SQL_DOWN)]
