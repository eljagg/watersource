"""Sprint 2b part 2 (v0.5.0): technical assessment stage + conditions, aquifers and WMU balance, MFA backup codes, Finance export."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.utils import timezone

from apps.accounts import roles
from apps.lic.models import ApplicationStatus, LicenceApplication, LicenceCondition, TechnicalAssessment
from apps.lic.services import wmu_balance
from apps.ref.models import WMU, Aquifer, Basin
from apps.workflow import engine
from apps.workflow.models import WorkflowDefinition
from tests.conftest import _user


@pytest.fixture
def wmu(db):
    basin = Basin.objects.create(code="B99", name="Test basin")
    return WMU.objects.create(code="W99", name="Test WMU", basin=basin, safe_yield_m3_d=Decimal("10000"))


def _verified_login(client, user):
    """Sign in a staff user whose role requires MFA, with a confirmed device marked verified in the session."""
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device = TOTPDevice.objects.get_or_create(user=user, name="t", defaults={"confirmed": True})[0]
    client.force_login(user)
    session = client.session
    session["otp_device_id"] = device.persistent_id
    session.save()


@pytest.fixture
def hydrologist(db):
    return _user("hydro@wra.gov.jm", roles.HYDROLOGIST)


@pytest.fixture
def application(db, client_user, party, parish, well, wmu):
    well.wmu = wmu
    well.save()
    app = LicenceApplication.objects.create(
        applicant_user=client_user, applicant=party, applicant_name="Jane Brown", applicant_address="Old Harbour", applicant_email="jane@example.com",
        applicant_phone="876", parish=parish, water_source="well", source_name="Bog Walk 1", well=well, daily_volume_requested_m3=Decimal("1200"),
        purpose="Irrigation", status=ApplicationStatus.SUBMITTED, submitted_at=timezone.now(),
    )
    engine.start("licence_application", app, client_user, summary=app.reference)
    return app


def _advance_to_assessment(app, reviewer):
    wf = app.workflow
    engine.approve(wf, reviewer, "intake ok")  # intake → technical assessment
    wf.refresh_from_db()
    assert wf.current_stage.code == "hydrogeology"
    return wf


@pytest.mark.django_db
def test_stage_renamed_and_conditions_seeded():
    call_command("bootstrap_workflows", verbosity=0)
    st = WorkflowDefinition.objects.get(code="licence_application").stages.get(code="hydrogeology")
    assert st.name == "Technical assessment" and st.approver_group.name == "hydrologist"
    assert LicenceCondition.objects.filter(is_default=True).count() >= 5


@pytest.mark.django_db
def test_assessment_required_before_stage_advances(client, reviewer, hydrologist, application, wmu):
    call_command("bootstrap_workflows", verbosity=0)
    wf = _advance_to_assessment(application, reviewer)
    with pytest.raises(engine.WorkflowError, match="technical assessment"):
        engine.approve(wf, hydrologist, "no assessment yet")
    # the panel points the hydrologist at the assessment page
    _verified_login(client, hydrologist)
    html = client.get(f"/workflow/{wf.pk}/").content.decode()
    assert "Complete the technical assessment" in html
    # record the assessment through the form (defaults: WMU from the well, default conditions pre-ticked)
    r = client.get(f"/licensing/applications/{application.reference}/assessment/")
    assert r.status_code == 200 and "WMU balance" in r.content.decode() and "10,000" in r.content.decode().replace("10000", "10,000")
    cond = list(LicenceCondition.objects.filter(is_default=True).values_list("pk", flat=True))
    r = client.post(f"/licensing/applications/{application.reference}/assessment/", {
        "wmu": wmu.pk, "impact": "moderate", "recommendation": "grant_reduced", "recommended_daily_volume_m3": "900",
        "conditions": cond, "extra_conditions": "Pumping only between 6 am and 6 pm.", "findings": "Nearby public-supply well 400 m away.",
    })
    assert r.status_code == 302
    ta = TechnicalAssessment.objects.get(application=application)
    assert ta.wmu_safe_yield_m3_d == Decimal("10000") and ta.assessed_by == hydrologist and ta.conditions.count() == len(cond)
    assert ta.wmu_utilisation_after_pct == 9.0
    application.refresh_from_db()
    assert application.wmu == wmu
    # now the stage advances, and the final approval issues the licence with the assessment's volume and conditions
    engine.approve(wf, hydrologist, "assessed")
    wf.refresh_from_db()
    officer = _user("officer@wra.gov.jm", roles.APPROVER)
    engine.approve(wf, officer, "ok")
    wf.refresh_from_db()
    engine.approve(wf, officer, "granted")
    application.refresh_from_db()
    lic = application.licence
    assert lic.daily_volume_granted_m3 == Decimal("900") and lic.wmu == wmu
    assert any("900" in c for c in lic.conditions) and any("6 am and 6 pm" in c for c in lic.conditions)
    assert len(lic.conditions) == len(cond) + 1
    _verified_login(client, officer)
    assert "Conditions of this licence" in client.get(f"/licensing/licences/{lic.number}/").content.decode()


@pytest.mark.django_db
def test_wmu_balance_sheet(client, reviewer, application, wmu):
    bal = wmu_balance(wmu)
    assert bal["pending"] == Decimal("1200") and bal["allocated"] == 0 and bal["utilisation_with_pending_pct"] == 12.0
    client.force_login(reviewer)
    html = client.get("/licensing/balance/").content.decode()
    assert "Test WMU" in html and "1,200" in html.replace("1200", "1,200")


@pytest.mark.django_db
def test_aquifer_model_and_admin(client, wmu):
    aq = Aquifer.objects.create(code="AQ1", name="Rio Cobre limestone", wmu=wmu, safe_yield_m3_d=Decimal("5000"))
    assert str(aq) and aq.aquifer_type == "limestone"


# --- MFA backup codes -----------------------------------------------------------------------


@pytest.mark.django_db
def test_backup_codes_issued_and_usable(client):
    from django.contrib.auth import get_user_model
    from django_otp.plugins.otp_static.models import StaticToken
    from django_otp.plugins.otp_totp.models import TOTPDevice

    u = get_user_model().objects.create_user(email="bk@wra.gov.jm", password="Str0ng-Passw0rd!!", full_name="B", user_type="staff")
    u.groups.add(Group.objects.get(name=roles.APPROVER))
    TOTPDevice.objects.create(user=u, name="phone", confirmed=True)
    client.force_login(u)
    session = client.session
    session["otp_device_id"] = TOTPDevice.objects.get(user=u).persistent_id
    session.save()
    html = client.get("/accounts/mfa/backup-codes/").content.decode()  # first visit issues a set
    assert "Backup codes" in html and StaticToken.objects.filter(device__user=u).count() == 10
    code = StaticToken.objects.filter(device__user=u).first().token
    # new session: password sign-in then the backup code at the verify step
    client.logout()
    client.post("/accounts/login/", {"username": "bk@wra.gov.jm", "password": "Str0ng-Passw0rd!!"})
    r = client.post("/accounts/mfa/verify/", {"token": code})
    assert r.status_code == 302 and StaticToken.objects.filter(device__user=u).count() == 9
    assert client.post("/accounts/mfa/verify/", {"token": code}).status_code == 200  # cannot be reused
    html = client.get("/accounts/profile/").content.decode()
    assert "Backup codes remaining: <strong>9</strong>" in html


# --- Finance export ---------------------------------------------------------------------------


@pytest.fixture
def finance_user(db):
    return _user("finance@wra.gov.jm", roles.FINANCE)


@pytest.mark.django_db
def test_finance_export_csv_and_api(client, finance_user, reviewer, application, wmu):
    from apps.lic.models import Licence
    from apps.obs.models import AbstractionRecord

    lic = Licence.issue(application, Decimal("1000"), 1, reviewer, conditions=["x"])
    now = timezone.now()
    AbstractionRecord.objects.create(licence=lic, well=application.well, source_type="ground", period_start=now - timedelta(days=30), period_end=now - timedelta(days=1),
                                     abstraction_volume_m3=Decimal("31000"), daily_volume_granted_m3=Decimal("1000"), over_limit=True, over_limit_pct=Decimal("6.9"),
                                     approval_state="approved", classification="staff_only")
    # reviewer is not finance → 404
    client.force_login(reviewer)
    assert client.get("/exports/finance/").status_code == 404
    client.force_login(finance_user)
    assert "Licence and abstraction export" in client.get("/exports/finance/").content.decode()
    csv_text = client.get("/exports/finance/licences.csv").content.decode()
    assert csv_text.splitlines()[0].startswith("licence_number,licensee") and lic.number in csv_text
    start, end = (now - timedelta(days=40)).date().isoformat(), now.date().isoformat()
    csv_text = client.get(f"/exports/finance/abstraction.csv?from={start}&to={end}").content.decode()
    assert "31000" in csv_text and "True" in csv_text
    js = client.get(f"/api/v1/exports/finance/abstraction/?from={start}&to={end}").json()
    assert js["count"] == 1 and js["results"][0]["licence_number"] == lic.number
    assert client.get("/api/v1/exports/finance/licences/?download=csv")["Content-Type"].startswith("text/csv")
    client.force_login(reviewer)
    assert client.get("/api/v1/exports/finance/licences/").status_code == 403


# --- v0.5.1: demo accounts refreshed even when the data is kept; orphaned workflow items removed ------------


@pytest.mark.django_db
def test_if_missing_still_creates_new_demo_accounts_and_prunes_orphans():
    from django.contrib.auth import get_user_model
    from django.contrib.contenttypes.models import ContentType

    from apps.submissions.models import Submission
    from apps.workflow.models import WorkflowDefinition, WorkflowInstance

    call_command("load_reference_data", verbosity=0)
    call_command("seed_demo_data", force=True, verbosity=0)
    U = get_user_model()
    U.objects.filter(email="demo.finance@wra-demo.local").delete()  # as on a staging DB seeded before the role existed
    ct = ContentType.objects.get_for_model(Submission)
    orphan = WorkflowInstance.objects.create(definition=WorkflowDefinition.objects.get(code="data_submission_default"), content_type=ct, object_id="999999999", summary="orphan")
    call_command("seed_demo_data", force=True, if_missing=True, verbosity=0)
    assert U.objects.filter(email="demo.finance@wra-demo.local").exists()
    assert U.objects.filter(email="demo.hydrologist@wra-demo.local", groups__name="hydrologist").exists()
    assert not WorkflowInstance.objects.filter(pk=orphan.pk).exists()


@pytest.mark.django_db
def test_demo_set_has_items_at_technical_assessment_and_upgrade_is_idempotent(client):
    from apps.workflow.models import WorkflowInstance

    call_command("load_reference_data", verbosity=0)
    call_command("seed_demo_data", force=True, verbosity=0)
    at = [w for w in WorkflowInstance.objects.filter(state="in_progress", definition__code="licence_application") if w.current_stage.code == "hydrogeology"]
    assert len(at) == 2 and sum(hasattr(w.subject, "assessment") for w in at) == 1
    # hydrologist sees them in the queue
    from django.contrib.auth import get_user_model

    hydro = get_user_model().objects.get(email="demo.hydrologist@wra-demo.local")
    _verified_login(client, hydro)
    html = client.get("/workflow/queue/").content.decode()
    assert "Technical assessment" in html and html.count("DEMO WRA-LA") == 2
    # a second run with the data kept changes nothing
    before = WorkflowInstance.objects.count()
    call_command("seed_demo_data", force=True, if_missing=True, verbosity=0)
    assert WorkflowInstance.objects.count() == before


# --- v0.5.3: panel actions always show their outcome -------------------------------------------


@pytest.mark.django_db
def test_panel_actions_report_outcome_and_return_to_queue(client, reviewer, hydrologist, application):
    call_command("bootstrap_workflows", verbosity=0)
    wf = _advance_to_assessment(application, reviewer)
    _verified_login(client, hydrologist)
    html = client.get(f"/workflow/{wf.pk}/").content.decode()
    assert "Back to review queue" in html and 'name="comment" rows="3" required' in html
    # no comment → stays on the item with the reason shown
    r = client.post(f"/workflow/{wf.pk}/act/", {"action": "request_info", "comment": ""}, follow=True)
    assert r.redirect_chain[-1][0].endswith(f"/workflow/{wf.pk}/") and "Tell the submitter what is needed" in r.content.decode()
    # with a comment → parked, user sent back to the queue with a message
    r = client.post(f"/workflow/{wf.pk}/act/", {"action": "request_info", "comment": "Please attach the pump test."}, follow=True)
    assert r.redirect_chain[-1][0].endswith("/workflow/queue/") and "Information requested" in r.content.decode()
    wf.refresh_from_db()
    assert wf.state == "info_requested"
    assert "Waiting on the submitter" in client.get(f"/workflow/{wf.pk}/").content.decode()
    # htmx callers get an HX-Redirect instead of a panel fragment
    r = client.post(f"/workflow/{wf.pk}/act/", {"action": "comment", "comment": "noted"}, HTTP_HX_REQUEST="true")
    assert r.status_code == 204 and r["HX-Redirect"].endswith(f"/workflow/{wf.pk}/")
    # reject closes the item
    r = client.post(f"/workflow/{wf.pk}/act/", {"action": "reject", "comment": "Aquifer fully allocated."}, follow=True)
    assert "Rejected" in r.content.decode()
    wf.refresh_from_db()
    assert wf.state == "rejected" and "Closed:" in client.get(f"/workflow/{wf.pk}/").content.decode()
