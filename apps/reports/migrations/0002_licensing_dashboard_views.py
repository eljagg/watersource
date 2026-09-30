"""Sprint 1: materialised views behind the Licensing overview dashboard (design doc 13 §5.1).

All views are aggregates with no personal data, so they may be read by the
wall-only role. Each has a unique index so ``REFRESH … CONCURRENTLY`` works.
"""
from django.db import migrations

SQL_UP = r"""
-- Snapshot of the application pipeline: how many at each status and how old they are.
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.licensing_pipeline AS
SELECT a.status,
       count(*)                                                           AS applications,
       round(avg(extract(epoch FROM (now() - coalesce(a.submitted_at, a.created_at)))/86400)::numeric, 1) AS avg_age_days,
       round(max(extract(epoch FROM (now() - coalesce(a.submitted_at, a.created_at)))/86400)::numeric, 1) AS oldest_days,
       sum(a.daily_volume_requested_m3)                                   AS daily_volume_requested_m3
FROM lic_licenceapplication a
GROUP BY 1;
CREATE UNIQUE INDEX IF NOT EXISTS bi_licensing_pipeline_uq ON bi.licensing_pipeline (status);

-- Applications received and decided per month, with turnaround.
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.applications_monthly AS
WITH received AS (
  SELECT date_trunc('month', submitted_at)::date AS month, count(*) AS received
  FROM lic_licenceapplication WHERE submitted_at IS NOT NULL GROUP BY 1),
decided AS (
  SELECT date_trunc('month', decided_at)::date AS month,
         count(*) FILTER (WHERE status = 'granted') AS granted,
         count(*) FILTER (WHERE status = 'refused') AS refused,
         round(avg(extract(epoch FROM (decided_at - submitted_at))/86400)::numeric, 1) AS avg_days_to_decision,
         round((percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (decided_at - submitted_at))/86400))::numeric, 1) AS median_days_to_decision
  FROM lic_licenceapplication WHERE decided_at IS NOT NULL AND submitted_at IS NOT NULL GROUP BY 1)
SELECT coalesce(r.month, d.month) AS month, coalesce(r.received, 0) AS received, coalesce(d.granted, 0) AS granted,
       coalesce(d.refused, 0) AS refused, d.avg_days_to_decision, d.median_days_to_decision
FROM received r FULL OUTER JOIN decided d ON d.month = r.month;
CREATE UNIQUE INDEX IF NOT EXISTS bi_applications_monthly_uq ON bi.applications_monthly (month);

-- Licences by time to expiry: what the licensing officer must chase.
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.licence_expiry AS
SELECT CASE WHEN l.status = 'expired' OR l.expires_on < current_date THEN 'expired'
            WHEN l.expires_on <= current_date + 30 THEN 'within_30_days'
            WHEN l.expires_on <= current_date + 60 THEN 'within_60_days'
            WHEN l.expires_on <= current_date + 90 THEN 'within_90_days'
            ELSE 'later' END AS bucket,
       count(*) AS licences, sum(l.daily_volume_granted_m3) AS daily_volume_granted_m3
FROM lic_licence l WHERE l.status IN ('active', 'expired')
GROUP BY 1;
CREATE UNIQUE INDEX IF NOT EXISTS bi_licence_expiry_uq ON bi.licence_expiry (bucket);

-- Active licences and granted volume by parish and source (map + bar chart).
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.licence_active_by_parish AS
SELECT p.name AS parish, l.water_source, count(*) AS licences, sum(l.daily_volume_granted_m3) AS daily_volume_granted_m3
FROM lic_licence l JOIN ref_parish p ON p.id = l.parish_id
WHERE l.status = 'active' AND l.expires_on >= current_date
GROUP BY 1, 2;
CREATE UNIQUE INDEX IF NOT EXISTS bi_licence_active_by_parish_uq ON bi.licence_active_by_parish (parish, water_source);

-- Headline numbers for the KPI tiles (one row).
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.licensing_kpis AS
SELECT 1 AS id,
       (SELECT count(*) FROM lic_licence WHERE status = 'active' AND expires_on >= current_date) AS active_licences,
       (SELECT coalesce(sum(daily_volume_granted_m3), 0) FROM lic_licence WHERE status = 'active' AND expires_on >= current_date) AS active_daily_volume_m3,
       (SELECT count(*) FROM lic_licenceapplication WHERE status IN ('submitted', 'under_review', 'info_requested')) AS applications_open,
       (SELECT count(*) FROM lic_licenceapplication WHERE status = 'granted' AND decided_at >= now() - interval '12 months') AS granted_last_12m,
       (SELECT count(*) FROM lic_licenceapplication WHERE status = 'refused' AND decided_at >= now() - interval '12 months') AS refused_last_12m,
       (SELECT round((percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (decided_at - submitted_at))/86400))::numeric, 1)
          FROM lic_licenceapplication WHERE decided_at IS NOT NULL AND submitted_at IS NOT NULL AND decided_at >= now() - interval '12 months') AS median_days_to_decision_12m,
       (SELECT count(*) FROM lic_licence WHERE status = 'active' AND expires_on BETWEEN current_date AND current_date + 90) AS expiring_within_90_days,
       (SELECT count(DISTINCT licence_id) FROM obs_abstractionrecord WHERE over_limit AND approval_state = 'approved' AND period_start >= now() - interval '12 months') AS over_limit_licences_12m,
       now() AS refreshed_at;
CREATE UNIQUE INDEX IF NOT EXISTS bi_licensing_kpis_uq ON bi.licensing_kpis (id);
"""

SQL_DOWN = r"""
DROP MATERIALIZED VIEW IF EXISTS bi.licensing_kpis, bi.licence_active_by_parish, bi.licence_expiry, bi.applications_monthly, bi.licensing_pipeline;
"""


class Migration(migrations.Migration):
    dependencies = [("reports", "0001_bi_schema"), ("obs", "0003_sprint1_quality_and_site_master")]
    operations = [migrations.RunSQL(SQL_UP, SQL_DOWN)]
