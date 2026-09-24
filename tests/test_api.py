import pytest
from django.urls import reverse

from apps.accounts.models import APIKey
from apps.obs.models import WellWaterLevel


@pytest.mark.django_db
def test_guest_sees_only_public_rows(client, well):
    from django.utils import timezone

    WellWaterLevel.objects.create(well=well, measured_at=timezone.now(), water_level_m=1, approval_state="approved", classification="public")
    WellWaterLevel.objects.create(well=well, measured_at=timezone.now(), water_level_m=2, approval_state="approved", classification="staff_only")
    WellWaterLevel.objects.create(well=well, measured_at=timezone.now(), water_level_m=3, approval_state="pending", classification="public")
    resp = client.get("/api/v1/observations/well-water-levels/")
    assert resp.status_code == 200 and resp.json()["count"] == 1


@pytest.mark.django_db
def test_staff_sees_approved_only_unless_reviewer(client, well, reviewer):
    from django.utils import timezone

    WellWaterLevel.objects.create(well=well, measured_at=timezone.now(), water_level_m=2, approval_state="approved", classification="staff_only")
    WellWaterLevel.objects.create(well=well, measured_at=timezone.now(), water_level_m=3, approval_state="pending")
    client.force_login(reviewer)
    assert client.get("/api/v1/observations/well-water-levels/").json()["count"] == 2


@pytest.mark.django_db
def test_api_key_submission(client, client_user, well):
    key, raw = APIKey.generate(client_user, "lab", scopes=["submissions:write"])
    body = {"category": "water_quality", "rows": [{"source_type": "well", "well": "BW-1", "sampled_at": "2026-02-01T08:00:00", "ph": 7.1}], "idempotency_key": "abc"}
    resp = client.post("/api/v1/submissions/", body, content_type="application/json", HTTP_AUTHORIZATION=f"Api-Key {raw}")
    assert resp.status_code == 202, resp.content
    again = client.post("/api/v1/submissions/", body, content_type="application/json", HTTP_AUTHORIZATION=f"Api-Key {raw}")
    assert again.json()["id"] == resp.json()["id"]  # idempotent
    bad = client.post("/api/v1/submissions/", {"category": "water_quality", "rows": [{"source_type": "well", "well": "BW-1"}]}, content_type="application/json", HTTP_AUTHORIZATION=f"Api-Key {raw}")
    assert bad.status_code == 422 and bad.json()["records"][0]["errors"]["sampled_at"]


@pytest.mark.django_db
def test_api_key_scope_and_revocation(client, client_user):
    key, raw = APIKey.generate(client_user, "ro", scopes=["observations:read"])
    resp = client.post("/api/v1/submissions/", {"category": "water_quality", "rows": [{}]}, content_type="application/json", HTTP_AUTHORIZATION=f"Api-Key {raw}")
    assert resp.status_code == 403
    from django.utils import timezone

    key.revoked_at = timezone.now()
    key.save()
    resp = client.get("/api/v1/wells/", HTTP_AUTHORIZATION=f"Api-Key {raw}")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_schema_and_docs_render(client):
    assert client.get(reverse("api-schema")).status_code == 200
    assert client.get("/api/v1/categories/").json()["count"] == 2


@pytest.mark.django_db
def test_healthz(client):
    assert client.get("/healthz").json()["status"] == "ok"
