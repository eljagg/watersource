"""bi.wmu_balance — safe yield vs licensed allocation vs reported abstraction per WMU (design doc 14 §4)."""
from django.db import migrations

SQL_UP = r"""
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.wmu_balance AS
SELECT w.id AS wmu_id, w.code, w.name AS wmu, b.name AS basin, w.safe_yield_m3_d,
       coalesce((SELECT sum(l.daily_volume_granted_m3) FROM lic_licence l LEFT JOIN ref_well wl ON wl.id = l.well_id
                 WHERE l.status = 'active' AND l.expires_on >= current_date AND coalesce(l.wmu_id, wl.wmu_id) = w.id), 0) AS licensed_m3_d,
       (SELECT count(*) FROM lic_licence l LEFT JOIN ref_well wl ON wl.id = l.well_id
         WHERE l.status = 'active' AND l.expires_on >= current_date AND coalesce(l.wmu_id, wl.wmu_id) = w.id) AS active_licences,
       (SELECT sum(a.abstraction_volume_m3) / nullif(sum(extract(epoch FROM (a.period_end - a.period_start)) / 86400), 0)
          FROM obs_abstractionrecord a LEFT JOIN lic_licence l ON l.id = a.licence_id LEFT JOIN ref_well wl ON wl.id = coalesce(a.well_id, l.well_id)
         WHERE a.approval_state = 'approved' AND a.period_start >= now() - interval '12 months' AND coalesce(l.wmu_id, wl.wmu_id) = w.id) AS reported_m3_d,
       coalesce((SELECT sum(ap.daily_volume_requested_m3) FROM lic_licenceapplication ap LEFT JOIN ref_well wl ON wl.id = ap.well_id
                 WHERE ap.status IN ('submitted', 'under_review', 'info_requested') AND coalesce(ap.wmu_id, wl.wmu_id) = w.id), 0) AS pending_m3_d,
       now() AS refreshed_at
FROM ref_wmu w LEFT JOIN ref_basin b ON b.id = w.basin_id;
CREATE UNIQUE INDEX IF NOT EXISTS bi_wmu_balance_uq ON bi.wmu_balance (wmu_id);
"""
SQL_DOWN = "DROP MATERIALIZED VIEW IF EXISTS bi.wmu_balance;"


class Migration(migrations.Migration):
    """Add the WMU balance view."""

    dependencies = [("reports", "0005_governance_audit_names"), ("ref", "0004_technical_assessment"), ("lic", "0003_technical_assessment")]
    operations = [migrations.RunSQL(SQL_UP, SQL_DOWN)]
