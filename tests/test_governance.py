"""v0.13.0 package 4: executive view for the governance layer and the milestone acceptance log."""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.core.models import AuditLog
from apps.governance.models import Milestone, MilestoneStatus
from apps.governance.services import can_decide_milestones, can_view_executive
from tests.conftest import _user


def _login(client, user):
    """Sign in with a verified MFA device (administrators must use two-factor sign-in)."""
    from django_otp.plugins.otp_totp.models import TOTPDevice

    device = TOTPDevice.objects.get_or_create(user=user, name="t", defaults={"confirmed": True})[0]
    client.force_login(user)
    session = client.session
    session["otp_device_id"] = device.persistent_id
    session.save()


def _ict_manager():
    return _user("ict.manager@wra.gov.jm", "administrator", unit="CGU")


@pytest.mark.django_db
def test_bootstrap_milestones_is_idempotent():
    call_command("bootstrap_milestones", verbosity=0)
    assert Milestone.objects.count() == 10 and [m.code for m in Milestone.objects.all()[:3]] == ["M1", "M2", "M3"]
    Milestone.objects.filter(code="M1").update(title="Changed by WRA")
    call_command("bootstrap_milestones", verbosity=0)
    assert Milestone.objects.count() == 10 and Milestone.objects.get(code="M1").title == "Changed by WRA"
    assert Milestone.objects.get(code="M9").due_week == 36 and Milestone.objects.get(code="M17").title.startswith("Adoption")


@pytest.mark.django_db
def test_who_may_see_and_who_may_decide(reviewer, client_user):
    call_command("bootstrap_roles", verbosity=0)
    ict = _ict_manager()
    md = _user("md@wra.gov.jm", "bi_analyst", unit="MDO")
    plu_admin = _user("plu.admin@wra.gov.jm", "administrator", unit="PLU")
    assert can_view_executive(ict) and can_view_executive(md) and can_view_executive(plu_admin)
    assert not can_view_executive(reviewer) and not can_view_executive(client_user)
    assert can_decide_milestones(ict) and not can_decide_milestones(md) and not can_decide_milestones(plu_admin)
    c = Client()
    c.force_login(reviewer)
    assert c.get("/executive/").status_code == 403
    _login(c, md)
    html = c.get("/executive/").content.decode()
    assert "Executive view" in html and "Milestone acceptance log" in html and "Mark delivered" not in html  # read-only for the MD
    assert "Executive view" in c.get("/").content.decode()  # reachable from Home
    c.force_login(reviewer)
    assert 'href="/executive/"' not in c.get("/").content.decode()


@pytest.mark.django_db
def test_milestone_delivery_acceptance_and_return_are_audited():
    call_command("bootstrap_roles", verbosity=0)
    call_command("bootstrap_milestones", verbosity=0)
    ict = _ict_manager()
    c = Client()
    _login(c, ict)
    m1 = Milestone.objects.get(code="M1")
    r = c.post(f"/executive/milestones/{m1.pk}/", {"action": "delivered", "evidence_url": "https://example.org/inception.pdf"})
    assert r.status_code == 302
    m1.refresh_from_db()
    assert m1.status == MilestoneStatus.DELIVERED and m1.delivered_on and m1.evidence_url.endswith("inception.pdf")
    # returning without remarks is refused
    c.post(f"/executive/milestones/{m1.pk}/", {"action": "return", "remarks": ""})
    m1.refresh_from_db()
    assert m1.status == MilestoneStatus.DELIVERED
    c.post(f"/executive/milestones/{m1.pk}/", {"action": "return", "remarks": "Work plan lacks the training schedule."})
    m1.refresh_from_db()
    assert m1.status == MilestoneStatus.RETURNED and m1.decided_by == ict and "training" in m1.remarks
    c.post(f"/executive/milestones/{m1.pk}/", {"action": "delivered"})
    c.post(f"/executive/milestones/{m1.pk}/", {"action": "accept", "remarks": "Accepted at SC meeting 3."})
    m1.refresh_from_db()
    assert m1.status == MilestoneStatus.ACCEPTED and m1.decided_at is not None
    actions = list(AuditLog.objects.filter(action__startswith="milestone.").order_by("at").values_list("action", flat=True))
    assert actions == ["milestone.delivered", "milestone.returned", "milestone.delivered", "milestone.accepted"]
    html = c.get("/executive/").content.decode()
    assert "1 accepted" in html and "Accepted at SC meeting 3." in html
    # the MD's office cannot decide
    md = _user("md2@wra.gov.jm", "bi_analyst", unit="MDO")
    _login(c, md)
    assert c.post(f"/executive/milestones/{m1.pk}/", {"action": "reopen"}).status_code == 403


@pytest.mark.django_db
def test_executive_figures_come_from_live_data(reviewer, client_user, party, parish, well):
    from decimal import Decimal

    from django.utils import timezone

    from apps.lic.models import ApplicationStatus, Licence, LicenceApplication
    from apps.ref.models import WMU

    call_command("bootstrap_roles", verbosity=0)
    call_command("load_reference_data", verbosity=0)
    wmu = WMU.objects.get(name="Hope River")
    wmu.safe_yield_m3_d = Decimal("1000")
    wmu.save()
    app = LicenceApplication.objects.create(applicant_user=client_user, applicant=party, applicant_name="Jane Brown", applicant_address="x", applicant_email="j@example.com",
                                            applicant_phone="1", parish=parish, water_source="well", source_name="w", well=well, wmu=wmu, daily_volume_requested_m3=Decimal("900"),
                                            purpose="Irrigation", status=ApplicationStatus.SUBMITTED, submitted_at=timezone.now())
    Licence.issue(app, Decimal("900"), 1, reviewer, conditions=[])
    LicenceApplication.objects.filter(pk=app.pk).update(status=ApplicationStatus.GRANTED)  # as the workflow would
    ict = _ict_manager()
    c = Client()
    _login(c, ict)
    html = c.get("/executive/").content.decode()
    assert "Licences issued this year" in html and "900 m³/day granted" in html
    assert "Hope River" in html and "90.0 %" in html  # over 85 % table
    assert "Backlog by branch" in html and "Adoption by unit" in html and "Data quality" in html


@pytest.mark.django_db
def test_workflow_root_redirects_to_the_queue(client):
    r = client.get("/workflow/")
    assert r.status_code == 302 and r["Location"] == "/workflow/queue/"
