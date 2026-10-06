"""v0.7.0 maps: boundaries loader, GeoJSON layers (masking), GeoPackage export (roles)."""
import shutil

import pytest
from django.core.management import call_command

from apps.accounts import roles
from apps.ref.models import WMU, Basin, Parish
from tests.conftest import _user


@pytest.fixture
def boundaries(db):
    call_command("load_reference_data", verbosity=0)
    call_command("load_boundaries", demo_shapes=True, verbosity=0)


@pytest.mark.django_db
def test_boundaries_loaded_and_demo_shapes_tagged(boundaries):
    assert Parish.objects.filter(geom__isnull=False).count() == 14
    assert Parish.objects.get(code="STC").geom_source.startswith("geoBoundaries")
    assert Basin.objects.filter(geom__isnull=False).count() == 10 and WMU.objects.filter(geom__isnull=False).count() == 15
    assert WMU.objects.get(code="W05").geom_source == "demonstration stand-in"
    # the Rio Cobre WMU stand-in sits inside its basin, and the basin inside the island
    w, b = WMU.objects.get(code="W05"), Basin.objects.get(code="B03")
    assert b.geom.buffer(50).contains(w.geom)
    # idempotent: a second run changes nothing
    before = {o.code: o.geom.wkt for o in WMU.objects.all()}
    call_command("load_boundaries", demo_shapes=True, verbosity=0)
    assert before == {o.code: o.geom.wkt for o in WMU.objects.all()}


@pytest.mark.django_db
def test_layers_and_masking(client, boundaries, well, reviewer):
    well.is_public_supply = True
    well.save()
    r = client.get("/maps/layers/wmus.geojson")
    assert r.status_code == 200 and r["Content-Type"] == "application/geo+json"
    js = r.json()
    assert js["type"] == "FeatureCollection" and len(js["features"]) == 15
    props = js["features"][0]["properties"]
    assert {"code", "name", "utilisation_pct", "safe_yield", "source"} <= set(props)
    g = js["features"][0]["geometry"]
    ring = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
    assert -79 < ring[0][0] < -75 and 17 < ring[0][1] < 19  # WGS 84, Jamaica
    # anonymous viewer: public-supply well coarsened; reviewer: exact
    anon = client.get("/maps/layers/sites.geojson").json()
    f = next(x for x in anon["features"] if x["properties"]["name"] == well.name)
    assert f["properties"]["coordinates_coarsened"] is True and anon["exact_coordinates"] is False
    client.force_login(reviewer)
    staff = client.get("/maps/layers/sites.geojson").json()
    f = next(x for x in staff["features"] if x["properties"]["name"] == well.name)
    assert f["properties"]["coordinates_coarsened"] is False and staff["exact_coordinates"] is True
    assert client.get("/maps/layers/nothing.geojson").status_code == 404
    assert "Water management units" in client.get("/maps/").content.decode()


@pytest.mark.django_db
def test_geopackage_export_roles(client, boundaries, reviewer):
    from tests.test_sprint2b_part2 import _verified_login

    client.force_login(reviewer)  # reviewer is not a GIS-export role
    assert client.get("/maps/export/").status_code == 404 and client.get("/maps/export/watersource.gpkg").status_code == 404
    gis = _user("gis@wra.gov.jm", roles.HYDROGEOLOGIST, unit="RMU")
    _verified_login(client, gis)
    assert "GeoPackage" in client.get("/maps/export/").content.decode()
    if shutil.which("ogr2ogr") is None:
        pytest.skip("GDAL not installed")
    r = client.get("/maps/export/watersource.gpkg?srid=4326&refresh=1")
    assert r.status_code == 200 and r["Content-Disposition"].endswith('watersource-4326.gpkg"')
    body = b"".join(r.streaming_content)
    assert body[:15] == b"SQLite format 3"
