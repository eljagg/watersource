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

## 5. Exports and the web map (v0.7.0)

**Web map** — `/maps/` shows parishes, basins, WMUs coloured by licensed utilisation
(from the balance sheet), aquifers and monitoring sites on a Leaflet map. Layers are
served as GeoJSON in WGS 84 from `/maps/layers/<parishes|basins|wmus|aquifers|sites>.geojson`;
site coordinates pass through the same public-supply masking as the API. The base map is
any XYZ tile service: `MAP_TILES_URL` / `MAP_TILES_ATTRIBUTION` (OpenStreetMap on staging;
on WRA's server point it at the ArcGIS Enterprise basemap, e.g.
`https://gis.wra.gov.jm/arcgis/rest/services/Basemap/MapServer/tile/{z}/{y}/{x}`, and the
content-security policy follows automatically).

**GeoPackage** — `/maps/export/` (administrator, hydrologist, hydrogeologist, BI analyst,
data-migration roles) downloads one `.gpkg` with parishes, basins, WMUs, aquifers, wells,
stations, springs and licences, in JAD2001 or WGS 84, built by `ogr2ogr` and cached ten
minutes. Every download is audited (`maps.gis_export`). Open it in ArcGIS Pro/QGIS and
export a shapefile from there if one is needed — GeoPackage is the master (shapefiles
truncate field names).

**Boundaries** — `manage.py load_boundaries`:

* `--parishes/--basins/--wmus/--aquifers <file.geojson>` loads WRA's own boundaries
  (convert a shapefile first: `ogr2ogr -f GeoJSON out.geojson in.shp`); features match on a
  `code` property (or `name`). Any CRS; reprojected to EPSG:3448.
* Parishes default to geoBoundaries (CC BY 4.0, `data/gis/ATTRIBUTION.md`) when empty.
* `--demo-shapes` builds Voronoi stand-ins for basins and WMUs without a boundary, tagged
  `geom_source = "demonstration stand-in"`; the map legend and the GeoPackage show the tag.
  Real boundaries loaded later replace them.

## 6. Optional web services (priced extra)

`pg_featureserv` (OGC API – Features) and `pg_tileserv` (vector tiles) from
CrunchyData run as single binaries under the same `gis_reader` role behind
nginx on the app-vm, giving browser maps and QGIS/ArcGIS access without opening
the database port.
