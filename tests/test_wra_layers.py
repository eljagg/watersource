"""v0.11.0: WRA's real layers from the Government of Jamaica ArcGIS Online, new map layers, Esri topographic default basemap."""
import json

import pytest
from django.core.management import call_command

from apps.maps import wra_arcgis
from apps.maps.models import WraFeature
from apps.ref.models import WMU, Basin

SQ = [[[-77.0, 18.0], [-76.9, 18.0], [-76.9, 18.1], [-77.0, 18.1], [-77.0, 18.0]]]
SQ2 = [[[-77.3, 18.2], [-77.2, 18.2], [-77.2, 18.3], [-77.3, 18.3], [-77.3, 18.2]]]


def _fc(feats):
    return {"type": "FeatureCollection", "features": feats}


def _write(tmp_path):
    (tmp_path / "basins.geojson").write_text(json.dumps(_fc([
        {"type": "Feature", "properties": {"FID": 1, "BasinNo": " ", "Hydrobasin": " "}, "geometry": {"type": "Polygon", "coordinates": SQ}},
        {"type": "Feature", "properties": {"FID": 3, "BasinNo": "2", "Hydrobasin": "Kingston", "Area": 251.7}, "geometry": {"type": "Polygon", "coordinates": SQ}},
    ])))
    (tmp_path / "wmus.geojson").write_text(json.dumps(_fc([
        {"type": "Feature", "properties": {"FID": 19, "Wmu_No": "18", "Wmu_Name": "Hope River", "Hydrobasin": "Kingston"}, "geometry": {"type": "Polygon", "coordinates": SQ}},
        {"type": "Feature", "properties": {"FID": 10, "Wmu_No": "9", "Wmu_Name": "Wagwater River", "Hydrobasin": "Blue Mountain North"}, "geometry": {"type": "Polygon", "coordinates": SQ2}},
        {"type": "Feature", "properties": {"FID": 99, "Wmu_No": "27", "Wmu_Name": "Test River", "Hydrobasin": "Kingston"}, "geometry": {"type": "Polygon", "coordinates": SQ2}},
    ])))
    (tmp_path / "gauges.geojson").write_text(json.dumps(_fc([
        {"type": "Feature", "properties": {"OBJECTID": 1, "NEWSTNCODE": "B21", "STATION": "Hope River at Gordon Town", "WMU": "Hope River", "HYDROBASIN": "Kingston",
                                           "STATE": "Active", "TYPE": "Gauging", "DR_AREA_KM": 48.5, "ELEVATN_M": 320, "Shape__Length": 1},
         "geometry": {"type": "Point", "coordinates": [-76.72, 18.03]}},
    ])))
    (tmp_path / "hydrostrat.geojson").write_text(json.dumps(_fc([
        {"type": "Feature", "properties": {"OBJECTID": 5, "HYDRO_STRA": "Limestone Aquifer"}, "geometry": {"type": "Polygon", "coordinates": SQ}},
        {"type": "Feature", "properties": {"OBJECTID": 6, "HYDRO_STRA": None}, "geometry": {"type": "Polygon", "coordinates": SQ2}},
    ])))


@pytest.mark.django_db
def test_load_wra_layers_from_files_matches_reference_rows(tmp_path, client):
    call_command("load_reference_data", verbosity=0)
    assert WMU.objects.count() == 26  # the official list is now complete in wmus.csv
    _write(tmp_path)
    call_command("load_wra_layers", from_dir=str(tmp_path), layers="basins,wmus,gauges,hydrostrat", verbosity=0)
    k = Basin.objects.get(name="Kingston")
    assert k.geom is not None and k.geom.srid == 3448 and "WRA" in k.geom_source and "basin 2" in k.geom_source
    hope = WMU.objects.get(name="Hope River")
    assert hope.geom is not None and "WMU 18" in hope.geom_source
    assert WMU.objects.get(name="Wag Water River").geom is not None  # alias: WRA spells it Wagwater
    new = WMU.objects.get(name="Test River")
    assert new.code == "W27" and new.basin == k and new.geom is not None
    assert WraFeature.objects.filter(layer="gauges").count() == 1 and WraFeature.objects.filter(layer="hydrostrat").count() == 2
    g = WraFeature.objects.get(layer="gauges")
    assert g.feature_id == "B21" and g.name == "Hope River at Gordon Town" and "Shape__Length" not in g.props and g.geom.srid == 3448
    # running again refreshes rather than duplicates; a feature WRA dropped disappears
    (tmp_path / "hydrostrat.geojson").write_text(json.dumps(_fc([{"type": "Feature", "properties": {"OBJECTID": 5, "HYDRO_STRA": "Alluvium Aquifer"}, "geometry": {"type": "Polygon", "coordinates": SQ}}])))
    call_command("load_wra_layers", from_dir=str(tmp_path), layers="hydrostrat", verbosity=0)
    assert list(WraFeature.objects.filter(layer="hydrostrat").values_list("name", flat=True)) == ["Alluvium Aquifer"]
    # a boundary WRA handed us as a file is never overwritten by the online copy
    hope.geom_source = "WRA file wmus_2026.geojson"
    hope.save(update_fields=["geom_source"])
    call_command("load_wra_layers", from_dir=str(tmp_path), layers="wmus", verbosity=0)
    assert WMU.objects.get(name="Hope River").geom_source == "WRA file wmus_2026.geojson"
    # the map serves the new layers and shows their controls only when loaded
    gj = client.get("/maps/layers/gauges.geojson").json()
    assert gj["features"][0]["properties"]["code"] == "B21" and gj["features"][0]["properties"]["drainage_km2"] == 48.5
    hs = client.get("/maps/layers/hydrostrat.geojson").json()
    assert hs["features"][0]["properties"]["unit"] == "Alluvium Aquifer" and hs["sources"] == [wra_arcgis.SOURCE]
    html = client.get("/maps/").content.decode()
    assert 'data-layer="gauges"' in html and 'data-layer="hydrostrat"' in html and 'data-layer="rivers"' not in html


@pytest.mark.django_db
def test_missing_network_never_breaks_the_command(tmp_path):
    call_command("load_wra_layers", from_dir=str(tmp_path), layers="rivers", verbosity=0)  # file missing → reported, no exception
    assert WraFeature.objects.count() == 0


def test_fetch_follows_arcgis_paging():
    pages = {"0": {"type": "FeatureCollection", "features": [{"id": i} for i in range(wra_arcgis.PAGE)], "properties": {"exceededTransferLimit": True}},
             "1000": {"type": "FeatureCollection", "features": [{"id": 1000}, {"id": 1001}]}}
    calls = []

    def opener(url, timeout):
        calls.append(url)
        offset = url.split("resultOffset=")[1].split("&")[0]
        return json.dumps(pages[offset])

    feats = wra_arcgis.fetch("Water_Resources/FeatureServer/0", opener=opener)
    assert len(feats) == 1002 and len(calls) == 2 and "outSR=4326" in calls[0] and "f=geojson" in calls[0]
    assert wra_arcgis.pick({"Wmu_Name": " Hope River ", "FID": 1}, ("wmu_name",)) == "Hope River"


@pytest.mark.django_db
def test_default_basemap_is_esri_topographic_and_hillshade_offered(client):
    html = client.get("/maps/").content.decode()
    assert html.index("Topographic") < html.index("Streets") and "World_Topo_Map" in html and "World_Hillshade" in html
    assert "data-hillshade=" in html
