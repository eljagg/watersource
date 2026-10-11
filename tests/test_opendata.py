"""v0.9.0 public repository: datasets expose only public approved records with masked coordinates; documents publish/withdraw."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.utils import timezone

from apps.obs.models import WellWaterLevel
from apps.opendata.datasets import DATASETS
from apps.opendata.models import PublishedDocument
from apps.ref.models import Well


@pytest.mark.django_db
def test_catalogue_reachable_from_home_and_footer(client):
    html = client.get("/").content.decode()
    assert 'href="/open-data/"' in html
    html = client.get("/open-data/").content.decode()
    assert "Open data and publications" in html and "Water abstraction licence register" in html and "Terms of use" in html
    assert len(DATASETS) == 6


@pytest.mark.django_db
def test_sites_dataset_masks_public_supply_and_hides_non_public(client, well, parish):
    secret = Well.objects.create(name="Staff only well", parish=parish, easting=761000, northing=651000, approval_state="approved", classification="staff_only")
    pending = Well.objects.create(name="Pending well", parish=parish, easting=762000, northing=652000, approval_state="pending", classification="public")
    well.is_public_supply = True
    well.save()
    rows = list(DATASETS["monitoring-sites"].rows())
    names = {r["name"] for r in rows}
    assert well.name in names and secret.name not in names and pending.name not in names
    r = next(x for x in rows if x["name"] == well.name)
    assert r["public_supply"] is True and r["lon"] is not None
    # coarsened: the 1 km grid centre, not the exact point
    from apps.opendata.datasets import _lonlat

    exact = _lonlat(well.easting, well.northing, False)
    assert exact != (r["lon"], r["lat"])
    csv_text = b"".join(client.get("/open-data/monitoring-sites.csv").streaming_content).decode("utf-8-sig")
    assert csv_text.splitlines()[0].startswith("site_type,name,parish") and well.name in csv_text and secret.name not in csv_text
    gj = client.get("/open-data/monitoring-sites.geojson").json()
    assert gj["type"] == "FeatureCollection" and any(f["properties"]["name"] == well.name for f in gj["features"])
    assert client.get("/open-data/licence-register.geojson").status_code == 404  # not spatial
    assert client.get("/open-data/nothing/").status_code == 404


@pytest.mark.django_db
def test_groundwater_monthly_only_counts_public_approved(client, well):
    now = timezone.now()
    WellWaterLevel.objects.create(well=well, measured_at=now, water_level_m=Decimal("10.5"), approval_state="approved", classification="public")
    WellWaterLevel.objects.create(well=well, measured_at=now - timedelta(hours=1), water_level_m=Decimal("99.0"), approval_state="approved", classification="staff_only")
    WellWaterLevel.objects.create(well=well, measured_at=now - timedelta(hours=2), water_level_m=Decimal("50.0"), approval_state="pending", classification="public")
    rows = list(DATASETS["groundwater-levels-monthly"].rows())
    assert len(rows) == 1 and rows[0]["readings"] == 1 and rows[0]["mean_level_m"] == 10.5
    html = client.get("/open-data/groundwater-levels-monthly/").content.decode()
    assert "1 row(s)" in html and "10.5" in html


@pytest.mark.django_db
def test_licence_register_has_no_licensee_particulars(client, reviewer, client_user, party, parish, well):
    from apps.lic.models import ApplicationStatus, Licence, LicenceApplication

    application = LicenceApplication.objects.create(
        applicant_user=client_user, applicant=party, applicant_name="Jane Brown", applicant_address="Old Harbour", applicant_email="jane@example.com",
        applicant_phone="876", parish=parish, water_source="well", source_name="Bog Walk 1", well=well, daily_volume_requested_m3=Decimal("1200"),
        purpose="Irrigation", status=ApplicationStatus.SUBMITTED, submitted_at=timezone.now())

    lic = Licence.issue(application, Decimal("1000"), 1, reviewer, conditions=[])
    rows = list(DATASETS["licence-register"].rows())
    assert rows[0]["licence_number"] == lic.number
    assert "licensee" not in rows[0] and "applicant" not in " ".join(rows[0].keys())
    csv_text = b"".join(client.get("/open-data/licence-register.csv").streaming_content).decode("utf-8-sig")
    assert "Jane Brown" not in csv_text and "jane@example.com" not in csv_text and lic.number in csv_text


@pytest.mark.django_db
def test_documents_publish_withdraw_and_count_downloads(client):
    doc = PublishedDocument(title="Bulletin 1", category="report", summary="s")
    doc.file.save("bulletin.pdf", ContentFile(b"%PDF-1.4\n%demo\n"), save=False)
    doc.original_name = "bulletin.pdf"
    doc.save()
    html = client.get("/open-data/").content.decode()
    assert "Bulletin 1" in html
    r = client.get(f"/open-data/documents/{doc.pk}/")
    assert r.status_code == 200 and r["Content-Disposition"].endswith('filename="bulletin.pdf"')
    doc.refresh_from_db()
    assert doc.downloads == 1
    doc.is_published = False
    doc.save()
    assert "Bulletin 1" not in client.get("/open-data/").content.decode()
    assert client.get(f"/open-data/documents/{doc.pk}/").status_code == 404


@pytest.mark.django_db
def test_demo_seed_publishes_three_documents():
    call_command("load_reference_data", verbosity=0)
    call_command("seed_demo_data", force=True, verbosity=0)
    docs = PublishedDocument.objects.filter(title__startswith="DEMO")
    assert docs.count() == 3 and all(d.file.storage.exists(d.file.name) and d.file.read(5) == b"%PDF-" for d in docs)
    call_command("seed_demo_data", force=True, if_missing=True, verbosity=0)
    assert PublishedDocument.objects.filter(title__startswith="DEMO").count() == 3
