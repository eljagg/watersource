"""Write a minimal WaterSource.qgs / .qgz without QGIS (fallback for the PyQGIS builder; same layers, default styling).

Run with plain Python: ``python deploy/gis/make_qgs.py``. QGIS fills in default
symbology when it opens the project; use build_qgis_project.py inside QGIS for
relations and temporal settings.
"""
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

SRID = 3448
WKT = ('PROJCRS["JAD2001 / Jamaica Metric Grid",BASEGEOGCRS["JAD2001",DATUM["Jamaica 2001",ELLIPSOID["WGS 84",6378137,298.257223563]],'
       'ID["EPSG",4758]],CONVERSION["Jamaica Metric Grid 2001",METHOD["Lambert Conic Conformal (1SP)"],PARAMETER["Latitude of natural origin",18],'
       'PARAMETER["Longitude of natural origin",-77],PARAMETER["Scale factor at natural origin",1],PARAMETER["False easting",750000],'
       'PARAMETER["False northing",650000]],CS[Cartesian,2],AXIS["easting",east],AXIS["northing",north],LENGTHUNIT["metre",1],ID["EPSG",3448]]')
LAYERS = [
    ("parishes", "Parishes", "ref_parish", "geom", "MultiPolygon", ""),
    ("basins", "Hydrological basins", "ref_basin", "geom", "MultiPolygon", ""),
    ("wmus", "Water management units", "ref_wmu", "geom", "MultiPolygon", ""),
    ("rivers", "Rivers", "ref_river", "geom", "MultiPolygon", ""),
    ("wells", "Wells", "ref_well", "location", "Point", "approval_state = 'approved'"),
    ("public_supply", "Public-supply sources (restricted)", "ref_well", "location", "Point", "is_public_supply = true"),
    ("stations", "Streamflow stations", "ref_streamflowstation", "location", "Point", "approval_state = 'approved'"),
    ("springs", "Springs", "ref_spring", "location", "Point", ""),
    ("well_levels", "Well water levels (approved)", "obs_wellwaterlevel", None, None, "approval_state = 'approved'"),
    ("station_readings", "Station readings (approved)", "obs_stationreading", None, None, "approval_state = 'approved'"),
    ("model_output", "Model output values", "obs_modeloutput", None, None, ""),
]


def srs():
    return f'<spatialrefsys nativeFormat="Wkt"><wkt>{escape(WKT)}</wkt><srsid>1400</srsid><srid>{SRID}</srid><authid>EPSG:{SRID}</authid><description>JAD2001 / Jamaica Metric Grid</description><projectionacronym>lcc</projectionacronym><ellipsoidacronym>EPSG:7030</ellipsoidacronym><geographicflag>false</geographicflag></spatialrefsys>'


def datasource(table, geom, where):
    ds = "service=watersource key='id' "
    if geom:
        ds += f"srid={SRID} type={LAYERS_GEOM[table][0]} checkPrimaryKeyUnicity='1' "
    ds += f'table="public"."{table}"'
    if geom:
        ds += f" ({geom})"
    ds += f" sql={where}"
    return ds


LAYERS_GEOM = {t: (g or "", c) for _, _, t, c, g, _ in LAYERS}


def build():
    tree, layers = [], []
    for lid, title, table, geom, gtype, where in LAYERS:
        ds = datasource(table, geom, where)
        tree.append(f'<layer-tree-layer id="{lid}" name="{escape(title)}" source="{escape(ds, {chr(34): "&quot;"})}" providerKey="postgres" checked="Qt::Checked" expanded="0"/>')
        layers.append(
            f'<maplayer type="vector" geometry="{gtype or "No geometry"}" autoRefreshEnabled="0" readOnly="1" simplifyDrawingHints="1" styleCategories="AllStyleCategories">'
            f'<id>{lid}</id><datasource>{escape(ds)}</datasource><layername>{escape(title)}</layername>'
            f'<srs>{srs()}</srs><provider encoding="UTF-8">postgres</provider></maplayer>'
        )
    xml = (
        "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"
        '<qgis version="3.44.0-Solothurn" projectname="WaterSource Jamaica — GIS desk" saveUser="watersource" saveUserFull="WaterSource">'
        '<homePath path=""/><title>WaterSource Jamaica — GIS desk</title>'
        f"<projectCrs>{srs()}</projectCrs>"
        '<layer-tree-group><customproperties/>' + "".join(tree) + "</layer-tree-group>"
        f'<mapcanvas name="theMapCanvas" annotationsVisible="1"><units>meters</units><destinationsrs>{srs()}</destinationsrs>'
        '<extent><xmin>600000</xmin><ymin>580000</ymin><xmax>900000</xmax><ymax>720000</ymax></extent></mapcanvas>'
        "<projectlayers>" + "".join(layers) + "</projectlayers>"
        '<properties><Measurement><DistanceUnits type="QString">meters</DistanceUnits><AreaUnits type="QString">km2</AreaUnits></Measurement></properties>'
        "</qgis>"
    )
    here = Path(__file__).parent
    (here / "WaterSource.qgs").write_text(xml, encoding="utf-8")
    with zipfile.ZipFile(here / "WaterSource.qgz", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("WaterSource.qgs", xml)
    print("wrote WaterSource.qgs and WaterSource.qgz")


if __name__ == "__main__":
    build()
