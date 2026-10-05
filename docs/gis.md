# GIS desk: QGIS and ArcGIS Pro on the live database

WaterSource is the system of record; GIS analysts read it directly rather than
waiting for exports (design doc 15 §3.3). Everything below is read-only.

## 1. One-time server step (DBA)

```
manage.py setup_gis_reader --password '<long random password>'
```

Creates the PostgreSQL role `gis_reader` with `SELECT` on `public` and `bi`
(including tables added later), and revokes the user, session, audit and
notification tables so personal data never reaches the GIS desk. For analysts
who must not see public-supply coordinates use a second role:

```
manage.py setup_gis_reader --role gis_public --public-only --password '…'
```

which sees only the boundary lookups and the coarsened `bi.public_wells` /
`bi.public_stations`. Re-run either command to rotate a password.

## 2. Each analyst's PC

1. Install **QGIS 3.44 LTR** (qgis.org/download). Stay on 3.44 until 4.4 LTR has
   had two or three point releases (early 2027).
2. Copy `deploy/gis/pg_service.conf.example` to
   `%APPDATA%\postgresql\.pg_service.conf` (Windows) or `~/.pg_service.conf`
   (Linux/macOS) and set `host=`. Put the password in `pgpass.conf` /
   `.pgpass` or let QGIS prompt.
3. Open `deploy/gis/WaterSource.qgz`. Every layer is defined as
   `service=watersource`, so the project contains no host or credentials and
   can be shared by email.

Layers: parishes, hydrological basins, water management units, rivers, wells
(approved), public-supply sources, streamflow stations (approved), springs,
and three attribute tables — well water levels, station readings and model
output values — linked to their sites.

## 3. Useful QGIS features out of the box

* **Identify a well → see its readings.** *Project → Properties → Relations →
  Discover relations* imports the foreign keys; readings then appear inside the
  well's feature form. (`build_qgis_project.py` sets these up when run inside
  QGIS's Python console and regenerates the project; it is the source of truth.)
* **Time slider.** The levels, readings and model-output layers have temporal
  properties set on their timestamp column; open *View → Panels → Temporal
  Controller*.
* **Charts.** Install the *DataPlotly* plugin and plot `water_level_m` against
  `measured_at` with the filter `well_id = @selected_well`.
* **Shared styles.** An administrator saves a layer's symbology with *Layer
  Properties → Symbology → Style → Save style → In database* and ticks *Use as
  default*; `setup_gis_reader` grants read access to the resulting
  `layer_styles` table, so everyone sees the same cartography.

## 4. ArcGIS Pro

*Insert → Connections → New Database Connection*, platform PostgreSQL, the same
host/database/`gis_reader`. PostGIS `geometry` tables appear directly; views in
`bi` are added as *Query Layers* (choose `id` as the unique field, EPSG:3448).
No ST_Geometry install is needed.

## 5. Exports

GeoPackage is the primary export (no 10-character field-name limit, no 2 GB
limit, real timestamps); shapefiles in JAD2001 are produced as well because the
tender asks for them. Both are made with `ogr2ogr` against the `gis_reader`
role, e.g.

```
ogr2ogr -f GPKG wells.gpkg "PG:service=watersource" -sql "SELECT * FROM ref_well WHERE classification = 'public'" -nln wells -a_srs EPSG:3448
```

## 6. Optional web services (priced extra)

`pg_featureserv` (OGC API – Features) and `pg_tileserv` (vector tiles) from
CrunchyData run as single binaries under the same `gis_reader` role behind
nginx on the app-vm, giving browser maps and QGIS/ArcGIS access without opening
the database port.
