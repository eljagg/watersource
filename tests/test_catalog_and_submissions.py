from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import DataCategory
from apps.catalog.services import build_json_schema, csv_template, validate_row
from apps.lic.models import ApplicationStatus, Licence, LicenceApplication, Sequence
from apps.obs.models import AbstractionRecord, RecordHistory, WaterQualitySample
from apps.submissions import services
from apps.submissions.models import SubmissionStatus
from apps.workflow import engine


@pytest.fixture
def licence(db, party, parish, well, approver):
    app = LicenceApplication.objects.create(
        applicant=party, applicant_name=party.name, applicant_address="x", applicant_email=party.email, applicant_phone="1",
        parish=parish, water_source="well", source_name=well.name, well=well, daily_volume_requested_m3=100, purpose="irrigation",
        status=ApplicationStatus.GRANTED,
    )
    return Licence.issue(app, Decimal("100"), 1, approver)


@pytest.mark.django_db
def test_json_schema_and_template_from_definition():
    v = DataCategory.objects.get(code="water_quality").current_version
    schema = build_json_schema(v)
    assert schema["properties"]["ph"]["maximum"] == 14 and "sampled_at" in schema["required"]
    assert csv_template(v).splitlines()[0].startswith("source_type,well,spring,station")


@pytest.mark.django_db
def test_validation_hard_errors_and_soft_flags(well):
    v = DataCategory.objects.get(code="water_quality").current_version
    cleaned, errors, flags = validate_row(v, {"source_type": "well", "well": "BW-1", "sampled_at": "2026-05-01T09:00", "ph": "3.0", "temperature_c": "70"})
    assert cleaned["well"] == well  # alias resolved
    assert "temperature_c" in errors  # above hard max 60
    assert any("pH" in f for f in flags)  # below soft min
    _, errors, _ = validate_row(v, {"source_type": "lake", "sampled_at": "yesterday"})
    assert "source_type" in errors and "sampled_at" in errors


@pytest.mark.django_db
def test_abstraction_submission_flags_over_limit_and_promotes_with_alert(licence, client_user, reviewer, approver, django_capture_on_commit_callbacks):
    v = DataCategory.objects.get(code="water_abstraction").current_version
    start = timezone.now() - timedelta(days=10)
    rows = [{"licence": licence.number, "source_type": "ground", "period_start": start.isoformat(), "period_end": (start + timedelta(days=10)).isoformat(),
             "abstraction_volume_m3": "1500"}]  # 100 m3/day * 10 days = 1000 allowed
    sub = services.create_submission(v, rows, client_user, channel="api")
    assert sub.status == SubmissionStatus.UNDER_REVIEW and sub.flagged_count == 1
    inst = sub.workflow
    engine.approve(inst, reviewer, "ok")
    with django_capture_on_commit_callbacks(execute=True):
        engine.approve(inst, approver, "publish", classification="public")
    sub.refresh_from_db()
    assert sub.status == SubmissionStatus.APPROVED and sub.classification == "public"
    rec = AbstractionRecord.objects.get()
    assert rec.over_limit and rec.approval_state == "approved" and rec.classification == "public" and rec.licence == licence
    assert rec.over_limit_pct == Decimal("50.00")
    assert reviewer.notifications.filter(kind="over_abstraction").exists()


@pytest.mark.django_db
def test_csv_channel_rejects_bad_rows_but_keeps_good(well, client_user):
    v = DataCategory.objects.get(code="water_quality").current_version
    csv = "source_type,well,spring,station,sample_ref,sampled_at,analysed_at,sampled_by,analysed_by,sample_depth_m,specific_conductivity_us_cm,temperature_c,ph,colour,odour,turbidity_ntu,percent_sodium,sodium_adsorption_ratio,calcium_mg_l,magnesium_mg_l,potassium_mg_l,carbonate_mg_l,bicarbonate_mg_l,sulphate_mg_l,chloride_mg_l,nitrate_mg_l,hardness_mg_l,alkalinity_mg_l,total_dissolved_solids_mg_l\n"
    csv += "well,Bog Walk 1,,,S1,2026-01-05T08:00:00,,,,,,25,7.2,,,,,,,,,,,,,,,,\n"
    csv += "well,Nowhere,,,S2,2026-01-05T08:00:00,,,,,,25,7.2,,,,,,,,,,,,,,,,\n"
    from django.core.files.uploadedfile import SimpleUploadedFile

    f = SimpleUploadedFile("wq.csv", csv.encode(), content_type="text/csv")
    sub = services.create_from_csv(v, f, client_user)
    assert sub.accepted_count == 1 and sub.rejected_count == 1 and sub.status == SubmissionStatus.UNDER_REVIEW
    rejected = sub.records.get(row_no=2)
    assert "well" in rejected.errors


@pytest.mark.django_db
def test_correction_reenters_workflow_and_writes_history(well, client_user, reviewer, approver):
    v = DataCategory.objects.get(code="water_quality").current_version
    sample = WaterQualitySample.objects.create(source_type="well", well=well, sampled_at=timezone.now(), ph=Decimal("7.10"), approval_state="approved", classification="public")
    sub = services.create_correction(v, sample, {"source_type": "well", "well": well.name, "sampled_at": sample.sampled_at.isoformat(), "ph": "7.40"}, reviewer, "transcription error")
    assert sub.is_correction and sub.workflow.definition.code == "correction"
    sample.refresh_from_db()
    assert sample.ph == Decimal("7.10")  # unchanged until approved
    engine.approve(sub.workflow, reviewer)
    engine.approve(sub.workflow, approver, classification="public")
    sample.refresh_from_db()
    assert sample.ph == Decimal("7.40")
    h = RecordHistory.objects.get()
    assert h.old_values["ph"] == "7.10" and h.new_values["ph"] == "7.40" and h.reason == "transcription error" and h.approved_by == approver


@pytest.mark.django_db
def test_licence_application_end_to_end(client, client_user, reviewer, approver, parish, well):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.urls import reverse

    client.force_login(client_user)
    resp = client.post(reverse("lic:application_create"), {
        "kind": "new", "applicant_name": "Jane Brown", "applicant_address": "Spanish Town", "applicant_email": "jane@example.com",
        "applicant_phone": "876", "parish": parish.pk, "water_source": "well", "source_name": well.name, "well": well.pk,
        "daily_volume_requested_m3": "50", "purpose": "irrigation",
    })
    app = LicenceApplication.objects.get()
    assert resp.status_code == 302 and app.reference.startswith("WRA-LA-")
    pdf = SimpleUploadedFile("id.pdf", b"%PDF-1.4\n%fake\n", content_type="application/pdf")
    client.post(reverse("lic:application_upload", args=[app.reference]), {"kind": "id", "file": pdf})
    assert app.documents.count() == 1
    client.post(reverse("lic:application_submit", args=[app.reference]))
    app.refresh_from_db()
    assert app.status == ApplicationStatus.UNDER_REVIEW
    inst = app.workflow
    assert inst.current_stage.code == "intake"
    engine.approve(inst, reviewer)  # intake (reviewer group)
    engine.approve(inst, reviewer)  # hydrogeology (reviewer group)
    engine.approve(inst, approver)  # licensing officer
    engine.approve(inst, approver, "granted", daily_volume_granted_m3="40", term_years=2)  # director
    app.refresh_from_db()
    assert app.status == ApplicationStatus.GRANTED and app.daily_volume_granted_m3 == Decimal("40")
    lic = app.licence
    assert lic.number.startswith("WRA-L-") and lic.expires_on.year == date.today().year + 2
    well.refresh_from_db()
    assert well.is_licensed and well.licence_number == lic.number


@pytest.mark.django_db
def test_expiry_alerts(licence, settings):
    from apps.lic.tasks import raise_expiry_alerts

    licence.expires_on = date.today() + timedelta(days=20)
    licence.save()
    out = raise_expiry_alerts()
    assert out["warned"] >= 1
    licence.refresh_from_db()
    assert 30 in licence.expiry_alerts_sent and 90 in licence.expiry_alerts_sent and 7 not in licence.expiry_alerts_sent
    licence.expires_on = date.today() - timedelta(days=1)
    licence.save()
    raise_expiry_alerts()
    licence.refresh_from_db()
    assert licence.status == "expired"


@pytest.mark.django_db
def test_sequences_are_yearly_and_gap_free(db):
    a, b = Sequence.next("t", "T"), Sequence.next("t", "T")
    assert a.endswith("000001") and b.endswith("000002")
