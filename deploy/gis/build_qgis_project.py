"""Build WaterSource.qgz with QGIS's own API (run inside QGIS: Plugins → Python Console → Show editor → open → run).

Creates a project in EPSG:3448 (JAD2001) whose layers all use ``service=watersource``
(see pg_service.conf.example), discovers the wells→levels and stations→readings
relations from the database foreign keys, sets temporal properties on the two
time-series layers and saves ``WaterSource.qgz`` next to this script. Re-run it
after new reference tables are added; it is the source of truth for the project
shipped in this folder.
"""
import os

from qgis.core import (  # noqa: E402  (available inside QGIS)
    QgsCoordinateReferenceSystem,
    QgsDataSourceUri,
    QgsProject,
    QgsRelation,
    QgsVectorLayer,
    QgsVectorLayerTemporalProperties,
)

SERVICE = "watersource"
SRID = 3448
LAYERS = [
    # (title, schema, table, geometry column, geometry type, key, filter)
    ("Parishes", "public", "ref_parish", "geom", "MultiPolygon", "id", ""),
    ("Hydrological basins", "public", "ref_basin", "geom", "MultiPolygon", "id", ""),
    ("Water management units", "public", "ref_wmu", "geom", "MultiPolygon", "id", ""),
    ("Rivers", "public", "ref_river", "geom", "MultiPolygon", "id", ""),
    ("Wells", "public", "ref_well", "location", "Point", "id", "approval_state = 'approved'"),
    ("Public-supply sources (restricted)", "public", "ref_well", "location", "Point", "id", "is_public_supply = true"),
    ("Streamflow stations", "public", "ref_streamflowstation", "location", "Point", "id", "approval_state = 'approved'"),
    ("Springs", "public", "ref_spring", "location", "Point", "id", ""),
    ("Well water levels (approved)", "public", "obs_wellwaterlevel", None, None, "id", "approval_state = 'approved'"),
    ("Station readings (approved)", "public", "obs_stationreading", None, None, "id", "approval_state = 'approved'"),
    ("Licences", "public", "lic_licence", None, None, "id", ""),
    ("Model output values", "public", "obs_modeloutput", None, None, "id", ""),
]


def uri_for(schema, table, geom, key, where):
    uri = QgsDataSourceUri()
    uri.setConnection(SERVICE, "", "", "")  # service-only: host/db/user come from pg_service.conf
    uri.setDataSource(schema, table, geom or "", where, key)
    if geom:
        uri.setSrid(str(SRID))
    return uri.uri(False)


def main():
    project = QgsProject.instance()
    project.clear()
    project.setCrs(QgsCoordinateReferenceSystem(f"EPSG:{SRID}"))
    project.setTitle("WaterSource Jamaica — GIS desk")
    layers = {}
    for title, schema, table, geom, gtype, key, where in LAYERS:
        lyr = QgsVectorLayer(uri_for(schema, table, geom, key, where), title, "postgres")
        if not lyr.isValid():
            print(f"!! could not load {schema}.{table}: {lyr.error().message()}")
            continue
        project.addMapLayer(lyr)
        layers[title] = lyr
    # relations: site → readings (QGIS can also discover these from the FKs)
    for parent, child, field in (("Wells", "Well water levels (approved)", "well_id"), ("Streamflow stations", "Station readings (approved)", "station_id")):
        if parent in layers and child in layers:
            rel = QgsRelation()
            rel.setId(f"{child}->{parent}")
            rel.setName(f"{parent} → {child}")
            rel.setReferencingLayer(layers[child].id())
            rel.setReferencedLayer(layers[parent].id())
            rel.addFieldPair(field, "id")
            if rel.isValid():
                project.relationManager().addRelation(rel)
    # temporal properties for the time slider
    for title, field in (("Well water levels (approved)", "measured_at"), ("Station readings (approved)", "read_at"), ("Model output values", "observed_at")):
        if title in layers:
            tp = layers[title].temporalProperties()
            tp.setIsActive(True)
            tp.setMode(QgsVectorLayerTemporalProperties.ModeFeatureDateTimeInstantFromField)
            tp.setStartField(field)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd(), "WaterSource.qgz")
    project.write(out)
    print(f"saved {out} with {len(layers)} layers")


main()
