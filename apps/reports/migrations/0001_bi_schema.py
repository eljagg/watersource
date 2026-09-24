"""bi schema: materialised views for Metabase (design plan §7). Two families —
bi.public_* (safe for guest dashboards) and bi.staff_* — plus the five named
indicator views. Refreshed by apps.reports.tasks.refresh_bi_views."""
from django.db import migrations

SQL_UP = r"""
CREATE SCHEMA IF NOT EXISTS bi;

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.licensing_monthly AS
SELECT date_trunc('month', l.issued_on)::date AS month, p.name AS parish, l.water_source,
       count(*) AS licences_issued, sum(l.daily_volume_granted_m3) AS daily_volume_granted_m3
FROM lic_licence l JOIN ref_parish p ON p.id = l.parish_id
GROUP BY 1,2,3;
CREATE UNIQUE INDEX IF NOT EXISTS bi_licensing_monthly_uq ON bi.licensing_monthly (month, parish, water_source);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.abstraction_vs_granted AS
SELECT l.number AS licence_number, p.name AS parish, l.water_source,
       date_trunc('month', a.period_start)::date AS month,
       sum(a.abstraction_volume_m3) AS abstracted_m3,
       max(l.daily_volume_granted_m3) * greatest(1, sum(extract(epoch FROM (a.period_end - a.period_start))/86400)) AS granted_m3,
       bool_or(a.over_limit) AS any_over_limit, a.classification
FROM obs_abstractionrecord a JOIN lic_licence l ON l.id = a.licence_id JOIN ref_parish p ON p.id = l.parish_id
WHERE a.approval_state = 'approved'
GROUP BY 1,2,3,4,8;
CREATE UNIQUE INDEX IF NOT EXISTS bi_abstraction_vs_granted_uq ON bi.abstraction_vs_granted (licence_number, month, classification);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.water_quality_by_parish AS
SELECT coalesce(pw.name, ps.name, pp.name) AS parish, s.source_type, date_trunc('quarter', s.sampled_at)::date AS quarter,
       count(*) AS samples, avg(s.ph) AS ph_avg, avg(s.specific_conductivity_us_cm) AS conductivity_avg,
       avg(s.nitrate_mg_l) AS nitrate_avg, avg(s.chloride_mg_l) AS chloride_avg, avg(s.total_dissolved_solids_mg_l) AS tds_avg,
       s.classification
FROM obs_waterqualitysample s
LEFT JOIN ref_well w ON w.id = s.well_id LEFT JOIN ref_parish pw ON pw.id = w.parish_id
LEFT JOIN ref_streamflowstation st ON st.id = s.station_id LEFT JOIN ref_parish ps ON ps.id = st.parish_id
LEFT JOIN ref_spring sp ON sp.id = s.spring_id LEFT JOIN ref_parish pp ON pp.id = sp.parish_id
WHERE s.approval_state = 'approved'
GROUP BY 1,2,3,10;
CREATE UNIQUE INDEX IF NOT EXISTS bi_wq_by_parish_uq ON bi.water_quality_by_parish (parish, source_type, quarter, classification);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.application_turnaround AS
SELECT a.reference, p.name AS parish, a.water_source, a.status, a.submitted_at, a.decided_at,
       extract(epoch FROM (a.decided_at - a.submitted_at))/86400 AS days_to_decision,
       (SELECT count(*) FROM workflow_workflowaction wa JOIN workflow_workflowinstance wi ON wi.id = wa.instance_id
          JOIN django_content_type ct ON ct.id = wi.content_type_id
         WHERE ct.app_label = 'lic' AND ct.model = 'licenceapplication' AND wi.object_id = a.id::text AND wa.action = 'return') AS returns
FROM lic_licenceapplication a JOIN ref_parish p ON p.id = a.parish_id
WHERE a.submitted_at IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS bi_application_turnaround_uq ON bi.application_turnaround (reference);

CREATE MATERIALIZED VIEW IF NOT EXISTS bi.well_inventory AS
SELECT p.name AS parish, b.name AS basin, w.use, w.is_licensed, w.is_abandoned, w.classification, count(*) AS wells
FROM ref_well w LEFT JOIN ref_parish p ON p.id = w.parish_id LEFT JOIN ref_basin b ON b.id = w.basin_id
WHERE w.approval_state = 'approved'
GROUP BY 1,2,3,4,5,6;
CREATE UNIQUE INDEX IF NOT EXISTS bi_well_inventory_uq ON bi.well_inventory (parish, basin, use, is_licensed, is_abandoned, classification);

-- public-only views: what a guest dashboard may query
CREATE OR REPLACE VIEW bi.public_wells AS
  SELECT id, name, easting, northing, elevation_m, parish_id, basin_id, wmu_id, use, is_licensed, is_abandoned, is_index_well
  FROM ref_well WHERE approval_state = 'approved' AND classification = 'public';
CREATE OR REPLACE VIEW bi.public_well_water_levels AS
  SELECT id, well_id, measured_at, water_level_m, well_state FROM obs_wellwaterlevel
  WHERE approval_state = 'approved' AND classification = 'public';
CREATE OR REPLACE VIEW bi.public_water_quality AS
  SELECT id, source_type, well_id, spring_id, station_id, sampled_at, ph, specific_conductivity_us_cm, temperature_c,
         nitrate_mg_l, chloride_mg_l, total_dissolved_solids_mg_l, hardness_mg_l
  FROM obs_waterqualitysample WHERE approval_state = 'approved' AND classification = 'public';
CREATE OR REPLACE VIEW bi.public_station_readings AS
  SELECT id, station_id, read_at, recorder_reading_m, observer_reading_m, discharge_m3_s FROM obs_stationreading
  WHERE approval_state = 'approved' AND classification = 'public';
"""

SQL_DOWN = r"""
DROP VIEW IF EXISTS bi.public_station_readings, bi.public_water_quality, bi.public_well_water_levels, bi.public_wells;
DROP MATERIALIZED VIEW IF EXISTS bi.well_inventory, bi.application_turnaround, bi.water_quality_by_parish, bi.abstraction_vs_granted, bi.licensing_monthly;
DROP SCHEMA IF EXISTS bi;
"""


class Migration(migrations.Migration):
    dependencies = [("lic", "0001_initial"), ("obs", "0001_initial"), ("workflow", "0001_initial")]
    operations = [migrations.RunSQL(SQL_UP, SQL_DOWN)]
