-- Database roles (run once by the DBA; see docs/database.md).
-- app_rw     : the Django application. No UPDATE/DELETE on append-only tables.
-- bi_reader  : Metabase. SELECT on schema bi only.
-- export_ro  : scheduled exports. SELECT on bi.public_* only.
-- migrate_rw : the migration team's staging loads (Daine); dropped after go-live.

CREATE ROLE app_rw LOGIN PASSWORD :'app_pw';
GRANT CONNECT ON DATABASE watersource TO app_rw;
GRANT USAGE, CREATE ON SCHEMA public TO app_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_rw;
-- append-only tables: revoke mutation rights from the application role
REVOKE UPDATE, DELETE ON core_auditlog, workflow_workflowaction, obs_recordhistory FROM app_rw;

CREATE ROLE bi_reader LOGIN PASSWORD :'bi_pw';
GRANT CONNECT ON DATABASE watersource TO bi_reader;
GRANT USAGE ON SCHEMA bi TO bi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA bi TO bi_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA bi GRANT SELECT ON TABLES TO bi_reader;
-- bi views join public tables: allow SELECT through the view owner, never directly
GRANT USAGE ON SCHEMA public TO bi_reader;
GRANT SELECT ON ref_parish, ref_basin, ref_wmu, ref_river TO bi_reader;

CREATE ROLE export_ro LOGIN PASSWORD :'export_pw';
GRANT CONNECT ON DATABASE watersource TO export_ro;
GRANT USAGE ON SCHEMA bi TO export_ro;
GRANT SELECT ON bi.public_wells, bi.public_well_water_levels, bi.public_water_quality, bi.public_station_readings TO export_ro;
