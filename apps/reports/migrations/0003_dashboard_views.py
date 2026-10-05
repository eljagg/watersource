"""Sprint 2a: bi views for the four dashboards (design doc 13 §5) and public-supply masking in bi.public_* (ADR-0002).

Every view here is an aggregate with no personal data, so the wall display may
read it. Each materialised view has a unique index so ``REFRESH … CONCURRENTLY``
works. Thresholds for water-quality exceedances follow the Jamaica NRCA /
WHO drinking-water guideline values used in the demo; WRA confirms the list at
the design workshop.
"""
from django.db import migrations

SQL_UP = r"""
-- ---------------------------------------------------------------- public views: coarsen public-supply coordinates
DROP VIEW IF EXISTS bi.public_wells;
CREATE VIEW bi.public_wells AS
  SELECT id, name,
         CASE WHEN is_public_supply THEN floor(easting / 1000) * 1000 + 500 ELSE easting END AS easting,
         CASE WHEN is_public_supply THEN floor(northing / 1000) * 1000 + 500 ELSE northing END AS northing,
         CASE WHEN is_public_supply THEN NULL ELSE elevation_m END AS elevation_m,
         is_public_supply AS coordinates_coarsened,
         parish_id, basin_id, wmu_id, use, is_licensed, is_abandoned, is_index_well
  FROM ref_well WHERE approval_state = 'approved' AND classification = 'public';

DROP VIEW IF EXISTS bi.public_stations;
CREATE VIEW bi.public_stations AS
  SELECT id, name, river_id,
         CASE WHEN is_public_supply THEN floor(easting / 1000) * 1000 + 500 ELSE easting END AS easting,
         CASE WHEN is_public_supply THEN floor(northing / 1000) * 1000 + 500 ELSE northing END AS northing,
         is_public_supply AS coordinates_coarsened, parish_id, basin_id, wmu_id, is_active
  FROM ref_streamflowstation WHERE approval_state = 'approved' AND classification = 'public';

-- ---------------------------------------------------------------- licensing overview (extra panels)
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.application_stage_counts AS
SELECT coalesce(st.name, 'Not started') AS stage, coalesce(st."order", 0) AS stage_order, count(*) AS applications,
       round(avg(extract(epoch FROM (now() - wi.stage_entered_at))/86400)::numeric, 1) AS avg_days_at_stage,
       count(*) FILTER (WHERE wi.stage_entered_at < now() - interval '30 days') AS over_30_days
FROM lic_licenceapplication a
JOIN django_content_type ct ON ct.app_label = 'lic' AND ct.model = 'licenceapplication'
LEFT JOIN workflow_workflowinstance wi ON wi.content_type_id = ct.id AND wi.object_id = a.id::text AND wi.state IN ('in_progress', 'info_requested')
LEFT JOIN workflow_workflowstage st ON st.id = wi.current_stage_id
WHERE a.status IN ('submitted', 'under_review', 'info_requested')
GROUP BY 1, 2;
CREATE UNIQUE INDEX IF NOT EXISTS bi_application_stage_counts_uq ON bi.application_stage_counts (stage);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.open_applications_by_parish AS
SELECT p.name AS parish, count(*) AS applications
FROM lic_licenceapplication a JOIN ref_parish p ON p.id = a.parish_id
WHERE a.status IN ('submitted', 'under_review', 'info_requested')
GROUP BY 1;
CREATE UNIQUE INDEX IF NOT EXISTS bi_open_applications_by_parish_uq ON bi.open_applications_by_parish (parish);

-- longest-waiting open items: reference, source and parish only (no applicant name — wall-safe)
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.longest_waiting_applications AS
SELECT a.reference, a.source_name, p.name AS parish, coalesce(st.name, 'Not started') AS stage,
       round(extract(epoch FROM (now() - coalesce(wi.stage_entered_at, a.submitted_at, a.created_at)))/86400) AS days_waiting
FROM lic_licenceapplication a JOIN ref_parish p ON p.id = a.parish_id
JOIN django_content_type ct ON ct.app_label = 'lic' AND ct.model = 'licenceapplication'
LEFT JOIN workflow_workflowinstance wi ON wi.content_type_id = ct.id AND wi.object_id = a.id::text AND wi.state IN ('in_progress', 'info_requested')
LEFT JOIN workflow_workflowstage st ON st.id = wi.current_stage_id
WHERE a.status IN ('submitted', 'under_review', 'info_requested')
ORDER BY 5 DESC LIMIT 8;
CREATE UNIQUE INDEX IF NOT EXISTS bi_longest_waiting_applications_uq ON bi.longest_waiting_applications (reference);

-- ---------------------------------------------------------------- water resources monitoring
-- latest approved level per well classed against the well's own record (USGS percentile bands; deeper = lower)
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.well_level_status AS
-- the latest reading may still be provisional (approval lags fieldwork); its percentile is taken against the APPROVED record
WITH hist AS (
  SELECT well_id, measured_at, water_level_m FROM obs_wellwaterlevel WHERE approval_state = 'approved' AND grade <> 'missing'
), latest AS (
  SELECT DISTINCT ON (well_id) well_id, measured_at, water_level_m FROM obs_wellwaterlevel
  WHERE approval_state IN ('approved', 'pending', 'under_review') AND grade <> 'missing' ORDER BY well_id, measured_at DESC
), ranked AS (
  SELECT l.well_id, l.measured_at, l.water_level_m,
         -- USGS convention: compare with the same calendar month of the record so seasonality does not mask a trend
         (SELECT count(*) FROM hist h WHERE h.well_id = l.well_id AND extract(month FROM h.measured_at) = extract(month FROM l.measured_at)) AS n,
         (SELECT count(*) FROM hist h WHERE h.well_id = l.well_id AND extract(month FROM h.measured_at) = extract(month FROM l.measured_at) AND h.water_level_m > l.water_level_m)::numeric
           / nullif((SELECT count(*) FROM hist h WHERE h.well_id = l.well_id AND extract(month FROM h.measured_at) = extract(month FROM l.measured_at)), 0) AS pr  -- share of record DEEPER than today: high = shallow = wet
  FROM latest l
)
SELECT w.id AS well_id, w.name AS well, p.name AS parish, b.name AS basin, w.classification,
       l.measured_at AS latest_at, l.water_level_m AS latest_level_m, round(l.pr * 100, 1) AS percentile, l.n AS record_count,
       round(extract(epoch FROM (now() - l.measured_at))/86400) AS days_since_reading,
       CASE WHEN l.measured_at < now() - interval '90 days' THEN 'no_recent_data'
            WHEN l.n < 6 THEN 'insufficient_record'
            WHEN l.pr < 0.10 THEN 'much_below_normal'
            WHEN l.pr < 0.25 THEN 'below_normal'
            WHEN l.pr <= 0.75 THEN 'normal'
            WHEN l.pr <= 0.90 THEN 'above_normal'
            ELSE 'much_above_normal' END AS status
FROM ref_well w JOIN ranked l ON l.well_id = w.id
LEFT JOIN ref_parish p ON p.id = w.parish_id LEFT JOIN ref_basin b ON b.id = w.basin_id
WHERE w.approval_state = 'approved' AND NOT w.is_abandoned;
CREATE UNIQUE INDEX IF NOT EXISTS bi_well_level_status_uq ON bi.well_level_status (well_id);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.station_flow_status AS
WITH hist AS (
  SELECT station_id, read_at, discharge_m3_s FROM obs_stationreading WHERE approval_state = 'approved' AND discharge_m3_s IS NOT NULL
), latest AS (
  SELECT DISTINCT ON (station_id) station_id, read_at, discharge_m3_s FROM obs_stationreading
  WHERE approval_state IN ('approved', 'pending', 'under_review') AND discharge_m3_s IS NOT NULL ORDER BY station_id, read_at DESC
), ranked AS (
  SELECT l.station_id, l.read_at, l.discharge_m3_s,
         (SELECT count(*) FROM hist h WHERE h.station_id = l.station_id AND extract(month FROM h.read_at) = extract(month FROM l.read_at)) AS n,
         (SELECT count(*) FROM hist h WHERE h.station_id = l.station_id AND extract(month FROM h.read_at) = extract(month FROM l.read_at) AND h.discharge_m3_s < l.discharge_m3_s)::numeric
           / nullif((SELECT count(*) FROM hist h WHERE h.station_id = l.station_id AND extract(month FROM h.read_at) = extract(month FROM l.read_at)), 0) AS pr  -- share of same-month record LOWER than today
  FROM latest l
)
SELECT s.id AS station_id, s.name AS station, r.name AS river, p.name AS parish, s.classification,
       l.read_at AS latest_at, l.discharge_m3_s AS latest_discharge_m3_s, round(l.pr * 100, 1) AS percentile, l.n AS record_count,
       round(extract(epoch FROM (now() - l.read_at))/86400) AS days_since_reading,
       CASE WHEN l.read_at < now() - interval '30 days' THEN 'no_recent_data'
            WHEN l.n < 20 THEN 'insufficient_record'
            WHEN l.pr < 0.10 THEN 'much_below_normal'
            WHEN l.pr < 0.25 THEN 'below_normal'
            WHEN l.pr <= 0.75 THEN 'normal'
            WHEN l.pr <= 0.90 THEN 'above_normal'
            ELSE 'much_above_normal' END AS status
FROM ref_streamflowstation s JOIN ranked l ON l.station_id = s.id
LEFT JOIN ref_river r ON r.id = s.river_id LEFT JOIN ref_parish p ON p.id = s.parish_id
WHERE s.approval_state = 'approved' AND s.is_active;
CREATE UNIQUE INDEX IF NOT EXISTS bi_station_flow_status_uq ON bi.station_flow_status (station_id);

-- monthly median depth to water per basin, indexed to the basin's 10-year mean (100 = mean; above 100 = deeper = less water)
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.groundwater_index_by_basin AS
WITH monthly AS (
  SELECT b.name AS basin, date_trunc('month', l.measured_at)::date AS month,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY l.water_level_m) AS median_level_m
  FROM obs_wellwaterlevel l JOIN ref_well w ON w.id = l.well_id JOIN ref_basin b ON b.id = w.basin_id
  WHERE l.approval_state = 'approved' AND l.measured_at >= now() - interval '10 years'
  GROUP BY 1, 2
), means AS (SELECT basin, avg(median_level_m) AS mean_level_m FROM monthly GROUP BY 1)
SELECT m.basin, m.month, round(m.median_level_m::numeric, 3) AS median_level_m,
       round((m.median_level_m / nullif(mn.mean_level_m, 0) * 100)::numeric, 1) AS index_value
FROM monthly m JOIN means mn ON mn.basin = m.basin
WHERE m.month >= date_trunc('month', now()) - interval '23 months';
CREATE UNIQUE INDEX IF NOT EXISTS bi_groundwater_index_by_basin_uq ON bi.groundwater_index_by_basin (basin, month);

-- daily discharge, last 90 days, per station (hydrograph strip)
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.station_flow_recent AS
SELECT s.name AS station, r.read_at::date AS day, round(avg(r.discharge_m3_s)::numeric, 3) AS discharge_m3_s, s.classification
FROM obs_stationreading r JOIN ref_streamflowstation s ON s.id = r.station_id
WHERE r.approval_state = 'approved' AND r.read_at >= now() - interval '90 days' AND r.discharge_m3_s IS NOT NULL
GROUP BY 1, 2, 4;
CREATE UNIQUE INDEX IF NOT EXISTS bi_station_flow_recent_uq ON bi.station_flow_recent (station, day);

-- abstraction as a share of the licensed daily limit, latest complete month, per licence (licence number only)
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.abstraction_share_latest AS
WITH latest_month AS (
  SELECT date_trunc('month', max(period_start)) AS month FROM obs_abstractionrecord WHERE approval_state = 'approved')
SELECT l.number AS licence_number, l.source_name, p.name AS parish, lm.month::date AS month,
       sum(a.abstraction_volume_m3) AS abstracted_m3,
       max(l.daily_volume_granted_m3) * greatest(1, sum(extract(epoch FROM (a.period_end - a.period_start))/86400)) AS allowed_m3,
       round((sum(a.abstraction_volume_m3) / nullif(max(l.daily_volume_granted_m3) * greatest(1, sum(extract(epoch FROM (a.period_end - a.period_start))/86400)), 0) * 100)::numeric, 1) AS share_pct,
       bool_or(a.over_limit) AS over_limit
FROM obs_abstractionrecord a JOIN lic_licence l ON l.id = a.licence_id JOIN ref_parish p ON p.id = l.parish_id, latest_month lm
WHERE a.approval_state = 'approved' AND date_trunc('month', a.period_start) = lm.month
GROUP BY 1, 2, 3, 4;
CREATE UNIQUE INDEX IF NOT EXISTS bi_abstraction_share_latest_uq ON bi.abstraction_share_latest (licence_number);

-- water-quality exceedances in the last 90 days by parameter (guideline values; WRA to confirm)
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.wq_exceedances_90d AS
SELECT parameter, count(*) AS samples_exceeding FROM (
  SELECT 'Nitrate' AS parameter FROM obs_waterqualitysample WHERE approval_state = 'approved' AND sampled_at >= now() - interval '90 days' AND nitrate_mg_l > 50
  UNION ALL SELECT 'Chloride' FROM obs_waterqualitysample WHERE approval_state = 'approved' AND sampled_at >= now() - interval '90 days' AND chloride_mg_l > 250
  UNION ALL SELECT 'pH' FROM obs_waterqualitysample WHERE approval_state = 'approved' AND sampled_at >= now() - interval '90 days' AND (ph < 6.5 OR ph > 8.5)
  UNION ALL SELECT 'Turbidity' FROM obs_waterqualitysample WHERE approval_state = 'approved' AND sampled_at >= now() - interval '90 days' AND turbidity_ntu > 5
  UNION ALL SELECT 'TDS' FROM obs_waterqualitysample WHERE approval_state = 'approved' AND sampled_at >= now() - interval '90 days' AND total_dissolved_solids_mg_l > 1000
  UNION ALL SELECT 'Conductivity' FROM obs_waterqualitysample WHERE approval_state = 'approved' AND sampled_at >= now() - interval '90 days' AND specific_conductivity_us_cm > 1500
  UNION ALL SELECT 'Hardness' FROM obs_waterqualitysample WHERE approval_state = 'approved' AND sampled_at >= now() - interval '90 days' AND hardness_mg_l > 500
) x GROUP BY 1;
CREATE UNIQUE INDEX IF NOT EXISTS bi_wq_exceedances_90d_uq ON bi.wq_exceedances_90d (parameter);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.monitoring_kpis AS
SELECT 1 AS id,
       (SELECT count(*) FROM ref_streamflowstation WHERE approval_state = 'approved' AND is_active) AS stations_active,
       (SELECT count(DISTINCT station_id) FROM obs_stationreading WHERE read_at >= now() - interval '7 days') AS stations_reporting_7d,
       (SELECT count(*) FROM ref_well WHERE approval_state = 'approved' AND NOT is_abandoned) AS wells_monitored,
       (SELECT count(DISTINCT well_id) FROM obs_wellwaterlevel WHERE measured_at >= now() - interval '30 days') AS wells_reporting_30d,
       (SELECT count(*) FROM bi.well_level_status WHERE status IN ('below_normal', 'much_below_normal')) AS wells_below_normal,
       (SELECT count(*) FROM bi.well_level_status WHERE status NOT IN ('no_recent_data', 'insufficient_record')) AS wells_classed,
       (SELECT round(avg(share_pct)::numeric, 1) FROM bi.abstraction_share_latest) AS abstraction_share_pct,
       (SELECT count(*) FROM bi.abstraction_share_latest WHERE over_limit) AS licences_over_limit,
       (SELECT count(*) FROM obs_waterqualitysample WHERE sampled_at >= date_trunc('month', now())) AS wq_samples_this_month,
       (SELECT count(*) FROM obs_waterqualitysample WHERE sampled_at >= date_trunc('month', now()) - interval '12 months' AND sampled_at < date_trunc('month', now()) - interval '11 months') AS wq_samples_same_month_last_year,
       (SELECT count(*) FROM obs_wellwaterlevel WHERE approval_state = 'pending') + (SELECT count(*) FROM obs_stationreading WHERE approval_state = 'pending') AS rows_awaiting_approval,
       now() AS refreshed_at;
CREATE UNIQUE INDEX IF NOT EXISTS bi_monitoring_kpis_uq ON bi.monitoring_kpis (id);

-- ---------------------------------------------------------------- data submissions and quality
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.submissions_monthly AS
SELECT date_trunc('month', s.created_at)::date AS month, s.channel, c.name AS category,
       count(*) AS submissions, sum(s.row_count) AS rows_submitted, sum(s.accepted_count) AS rows_accepted,
       sum(s.flagged_count) AS rows_flagged, sum(s.rejected_count) AS rows_rejected,
       count(*) FILTER (WHERE s.status = 'approved') AS approved, count(*) FILTER (WHERE s.status = 'rejected') AS rejected
FROM submissions_submission s JOIN catalog_categoryversion cv ON cv.id = s.category_version_id JOIN catalog_datacategory c ON c.id = cv.category_id
WHERE s.created_at >= date_trunc('month', now()) - interval '11 months'
GROUP BY 1, 2, 3;
CREATE UNIQUE INDEX IF NOT EXISTS bi_submissions_monthly_uq ON bi.submissions_monthly (month, channel, category);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.review_backlog_age AS
SELECT d.name AS workflow,
       CASE WHEN wi.stage_entered_at >= now() - interval '7 days' THEN '0-7 days'
            WHEN wi.stage_entered_at >= now() - interval '14 days' THEN '8-14 days'
            WHEN wi.stage_entered_at >= now() - interval '30 days' THEN '15-30 days'
            ELSE 'over 30 days' END AS age_band,
       CASE WHEN wi.stage_entered_at >= now() - interval '7 days' THEN 1 WHEN wi.stage_entered_at >= now() - interval '14 days' THEN 2
            WHEN wi.stage_entered_at >= now() - interval '30 days' THEN 3 ELSE 4 END AS band_order,
       count(*) AS items
FROM workflow_workflowinstance wi JOIN workflow_workflowdefinition d ON d.id = wi.definition_id
WHERE wi.state IN ('in_progress', 'info_requested')
GROUP BY 1, 2, 3;
CREATE UNIQUE INDEX IF NOT EXISTS bi_review_backlog_age_uq ON bi.review_backlog_age (workflow, age_band);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.observation_grades AS
SELECT series, grade, count(*) AS rows FROM (
  SELECT 'Well levels' AS series, coalesce(nullif(grade, ''), 'ungraded') AS grade FROM obs_wellwaterlevel WHERE measured_at >= now() - interval '12 months'
  UNION ALL SELECT 'Station readings', coalesce(nullif(grade, ''), 'ungraded') FROM obs_stationreading WHERE read_at >= now() - interval '12 months'
  UNION ALL SELECT 'Abstraction', coalesce(nullif(grade, ''), 'ungraded') FROM obs_abstractionrecord WHERE period_start >= now() - interval '12 months'
  UNION ALL SELECT 'Water quality', coalesce(nullif(grade, ''), 'ungraded') FROM obs_waterqualitysample WHERE sampled_at >= now() - interval '12 months'
) x GROUP BY 1, 2;
CREATE UNIQUE INDEX IF NOT EXISTS bi_observation_grades_uq ON bi.observation_grades (series, grade);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.validation_failures AS
SELECT coalesce(k.key, '__all__') AS field, count(*) AS rows_failed
FROM submissions_submissionrecord r
JOIN submissions_submission s ON s.id = r.submission_id
LEFT JOIN LATERAL jsonb_object_keys(CASE WHEN jsonb_typeof(r.errors::jsonb) = 'object' THEN r.errors::jsonb ELSE '{}'::jsonb END) AS k(key) ON true
WHERE r.status = 'rejected' AND s.created_at >= now() - interval '90 days'
GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
CREATE UNIQUE INDEX IF NOT EXISTS bi_validation_failures_uq ON bi.validation_failures (field);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.submissions_kpis AS
SELECT 1 AS id,
       (SELECT count(*) FROM submissions_submission WHERE created_at >= date_trunc('month', now())) AS submissions_this_month,
       (SELECT coalesce(sum(row_count), 0) FROM submissions_submission WHERE created_at >= date_trunc('month', now())) AS rows_this_month,
       (SELECT round(100.0 * coalesce(sum(accepted_count), 0) / nullif(sum(row_count), 0), 1) FROM submissions_submission WHERE created_at >= now() - interval '90 days') AS acceptance_rate_pct,
       (SELECT coalesce(sum(flagged_count), 0) FROM submissions_submission WHERE created_at >= now() - interval '90 days') AS rows_flagged_90d,
       (SELECT count(*) FROM workflow_workflowinstance WHERE state IN ('in_progress', 'info_requested')) AS items_in_review,
       (SELECT round((percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (closed_at - started_at))/86400))::numeric, 1)
          FROM workflow_workflowinstance WHERE closed_at IS NOT NULL AND closed_at >= now() - interval '90 days') AS median_review_days_90d,
       now() AS refreshed_at;
CREATE UNIQUE INDEX IF NOT EXISTS bi_submissions_kpis_uq ON bi.submissions_kpis (id);

-- ---------------------------------------------------------------- executive and compliance
CREATE MATERIALIZED VIEW IF NOT EXISTS bi.licences_by_status AS
SELECT l.status, l.water_source, count(*) AS licences, sum(l.daily_volume_granted_m3) AS daily_volume_granted_m3
FROM lic_licence l GROUP BY 1, 2;
CREATE UNIQUE INDEX IF NOT EXISTS bi_licences_by_status_uq ON bi.licences_by_status (status, water_source);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.service_standard_monthly AS
SELECT date_trunc('month', decided_at)::date AS month, count(*) AS decided,
       count(*) FILTER (WHERE decided_at - submitted_at <= interval '30 days') AS within_30_days,
       round(100.0 * count(*) FILTER (WHERE decided_at - submitted_at <= interval '30 days') / count(*), 1) AS within_30_days_pct
FROM lic_licenceapplication WHERE decided_at IS NOT NULL AND submitted_at IS NOT NULL AND decided_at >= date_trunc('month', now()) - interval '11 months'
GROUP BY 1;
CREATE UNIQUE INDEX IF NOT EXISTS bi_service_standard_monthly_uq ON bi.service_standard_monthly (month);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.expiries_next_12m AS
WITH months AS (SELECT (date_trunc('month', now()) + (g || ' months')::interval)::date AS month FROM generate_series(0, 11) g)
SELECT m.month,
       (SELECT count(*) FROM lic_licence l WHERE l.status = 'active' AND date_trunc('month', l.expires_on) = m.month) AS expiring,
       (SELECT count(*) FROM lic_licenceapplication a JOIN lic_licence l ON l.id = a.renewal_of_id
         WHERE a.status IN ('submitted', 'under_review', 'info_requested', 'granted') AND date_trunc('month', l.expires_on) = m.month) AS renewals_lodged
FROM months m;
CREATE UNIQUE INDEX IF NOT EXISTS bi_expiries_next_12m_uq ON bi.expiries_next_12m (month);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.governance_kpis AS
SELECT 1 AS id,
       (SELECT count(*) FROM core_auditlog WHERE action = 'account.export' AND at >= now() - interval '12 months') AS subject_access_exports_12m,
       (SELECT count(*) FROM core_auditlog WHERE action = 'retention.sweep' AND at >= now() - interval '12 months') AS retention_sweeps_12m,
       (SELECT count(*) FROM axes_accessattempt) AS lockouts_active,
       (SELECT coalesce(sum(failures_since_start), 0) FROM axes_accessattempt) AS failed_sign_ins_blocked,
       (SELECT count(*) FROM core_auditlog WHERE action = 'classification.changed' AND at >= now() - interval '12 months') AS classification_changes_12m,
       (SELECT count(*) FROM obs_recordhistory WHERE approved_at >= now() - interval '12 months') AS corrections_approved_12m,
       now() AS refreshed_at;
CREATE UNIQUE INDEX IF NOT EXISTS bi_governance_kpis_uq ON bi.governance_kpis (id);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.executive_kpis AS
SELECT 1 AS id,
       (SELECT count(*) FROM lic_licence WHERE status = 'active' AND expires_on >= current_date) AS active_licences,
       (SELECT count(*) FROM lic_licenceapplication WHERE status = 'granted' AND decided_at >= date_trunc('year', now())) AS granted_this_year,
       (SELECT round(100.0 * count(*) FILTER (WHERE decided_at - submitted_at <= interval '30 days') / nullif(count(*), 0), 1)
          FROM lic_licenceapplication WHERE decided_at IS NOT NULL AND submitted_at IS NOT NULL AND decided_at >= now() - interval '12 months') AS service_standard_pct_12m,
       (SELECT coalesce(sum(daily_volume_granted_m3), 0) FROM lic_licence WHERE status = 'active' AND expires_on >= current_date) AS licensed_daily_volume_m3,
       (SELECT count(*) FROM bi.abstraction_share_latest WHERE over_limit) AS licences_over_limit,
       (SELECT count(*) FROM lic_licence WHERE status = 'active' AND expires_on BETWEEN current_date AND current_date + 90) AS expiring_within_90_days,
       now() AS refreshed_at;
CREATE UNIQUE INDEX IF NOT EXISTS bi_executive_kpis_uq ON bi.executive_kpis (id);
"""

SQL_DOWN = r"""
DROP MATERIALIZED VIEW IF EXISTS bi.executive_kpis, bi.governance_kpis, bi.expiries_next_12m, bi.service_standard_monthly, bi.licences_by_status,
  bi.submissions_kpis, bi.validation_failures, bi.observation_grades, bi.review_backlog_age, bi.submissions_monthly,
  bi.monitoring_kpis, bi.wq_exceedances_90d, bi.abstraction_share_latest, bi.station_flow_recent, bi.groundwater_index_by_basin,
  bi.station_flow_status, bi.well_level_status, bi.longest_waiting_applications, bi.open_applications_by_parish, bi.application_stage_counts;
DROP VIEW IF EXISTS bi.public_stations, bi.public_wells;
CREATE VIEW bi.public_wells AS
  SELECT id, name, easting, northing, elevation_m, parish_id, basin_id, wmu_id, use, is_licensed, is_abandoned, is_index_well
  FROM ref_well WHERE approval_state = 'approved' AND classification = 'public';
"""


class Migration(migrations.Migration):
    dependencies = [("reports", "0002_licensing_dashboard_views"), ("ref", "0003_restricted_classification"), ("submissions", "0002_restricted_classification"), ("axes", "0010_accessattemptexpiration")]
    operations = [migrations.RunSQL(SQL_UP, SQL_DOWN)]
