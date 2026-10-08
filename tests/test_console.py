"""v0.8.0 unit console: access, cleansing decisions, unlock, adoption sign-off, profiler → queue."""
import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts import roles
from apps.accounts.models import Unit
from apps.console.models import AdoptionSignoff, CleansingIssue, Decision, IssueKind, IssueStatus
from tests.conftest import _user
from tests.test_sprint2b_part2 import _verified_login


@pytest.fixture
def plu_super(db):
    u = _user("super.plu@wra.gov.jm", roles.REVIEWER, unit="PLU")
    u.is_super_user = True
    u.save(update_fields=["is_super_user"])
    return u


@pytest.mark.django_db
def test_console_access_and_unit_scope(client, reviewer, plu_super):
    client.force_login(reviewer)  # ordinary PLU reviewer, not a Super User
    assert client.get("/unit/").status_code == 404
    client.force_login(plu_super)
    html = client.get("/unit/").content.decode()
    assert "Permits &amp; Licences Unit" in html and "Data-cleansing queue" in html
    assert client.get("/unit/?unit=RMU").status_code == 404  # another unit is off limits
    # administrators see any unit through the selector
    admin = _user("adm@wra.gov.jm", roles.ADMINISTRATOR, unit="CGU")
    _verified_login(client, admin)
    assert "Resource Monitoring Unit" in client.get("/unit/?unit=RMU").content.decode()
    assert 'id="unit-select"' in client.get("/unit/").content.decode()


@pytest.mark.django_db
def test_cleansing_decision_is_recorded_and_audited(client, plu_super):
    from apps.core.models import AuditLog

    plu = Unit.objects.get(code="PLU")
    issue = CleansingIssue.objects.create(unit=plu, kind=IssueKind.UNMATCHED, source="Licences.accdb", column="WELL_REF", summary="3 unmatched",
                                          details={"top_unmatched": [["BW-01", 5]], "candidates": ["Bog Walk 1"]}, rows_affected=5)
    client.force_login(plu_super)
    # 'map' without a target is refused
    r = client.post(f"/unit/issues/{issue.pk}/resolve/", {"decision": Decision.MAP, "note": "", "target": ""}, follow=True)
    assert "Say which record" in r.content.decode()
    r = client.post(f"/unit/issues/{issue.pk}/resolve/", {"decision": Decision.MAP, "note": "legacy code", "target": "Bog Walk 1"}, follow=True)
    assert "Decision recorded" in r.content.decode()
    issue.refresh_from_db()
    assert issue.status == IssueStatus.RESOLVED and issue.decided_by == plu_super and issue.decision_target == "Bog Walk 1"
    assert AuditLog.objects.filter(action="cleansing.resolved").exists()
    # another unit's Super User cannot touch it
    rmu_super = _user("super.rmu@wra.gov.jm", roles.TECHNICIAN, unit="RMU")
    rmu_super.is_super_user = True
    rmu_super.save()
    other = CleansingIssue.objects.create(unit=plu, kind=IssueKind.DUPLICATE, source="x.csv", summary="dup")
    client.force_login(rmu_super)
    assert client.post(f"/unit/issues/{other.pk}/resolve/", {"decision": Decision.REJECT}).status_code == 404


@pytest.mark.django_db
def test_unlock_locked_member(client, plu_super, approver):
    from axes.models import AccessAttempt

    AccessAttempt.objects.create(username=approver.email, ip_address="10.0.0.1", user_agent="t", attempt_time=timezone.now(), failures_since_start=5)
    client.force_login(plu_super)
    html = client.get("/unit/").content.decode()
    assert "Locked out" in html and "1 locked out" in html
    r = client.post(f"/unit/members/{approver.pk}/unlock/", {"unit": "PLU"}, follow=True)
    assert "can sign in again" in r.content.decode()
    assert not AccessAttempt.objects.filter(username=approver.email).exists()


@pytest.mark.django_db
def test_adoption_signoff(client, plu_super, reviewer):
    client.force_login(reviewer)
    assert client.post("/unit/adoption/", {"unit": "PLU", "m_trained": "on"}).status_code == 404
    client.force_login(plu_super)
    r = client.post("/unit/adoption/", {"unit": "PLU", "m_trained": "on", "m_data_loaded": "on"}, follow=True)
    assert "outstanding measures" in r.content.decode()
    s = AdoptionSignoff.objects.get()
    assert not s.complete and s.measures["trained"] and not s.measures["workflow_live"]
    allm = {f"m_{c}": "on" for c in ("trained", "data_loaded", "workflow_live", "cleansing_cleared", "support_known")}
    r = client.post("/unit/adoption/", {"unit": "PLU", **allm, "statement": "Done."}, follow=True)
    assert "Adoption sign-off recorded." in r.content.decode() and AdoptionSignoff.objects.first().complete
    assert "fully signed off" in client.get("/unit/").content.decode()


@pytest.mark.django_db
def test_profile_source_raises_issues(tmp_path, well):
    csv = tmp_path / "GroundwaterLevels_old.csv"
    rows = ["well,date,level_m"] + [f"{'Bog Walk 1' if i % 3 else 'Bogg Walk #1'},{'01/02/2020' if i % 2 else '2020-02-01'},{10 + i}" for i in range(20)]
    rows += ["Bog Walk 1,01/02/2020,10", "Bog Walk 1,01/02/2020,10", "Unknown Well X,N/A,999"]
    csv.write_text("\n".join(rows))
    call_command("profile_source", str(csv), out=str(tmp_path / "dqa"), raise_issues=True, verbosity=0)
    issues = CleansingIssue.objects.filter(unit__code="RMU", source=str(csv))
    kinds = set(issues.values_list("kind", flat=True))
    assert IssueKind.DUPLICATE in kinds and IssueKind.DATE_FORMATS in kinds
    n = issues.count()
    call_command("profile_source", str(csv), out=str(tmp_path / "dqa"), raise_issues=True, verbosity=0)  # idempotent
    assert CleansingIssue.objects.filter(source=str(csv)).count() == n


@pytest.mark.django_db
def test_demo_seed_fills_each_units_queue(client):
    call_command("load_reference_data", verbosity=0)
    call_command("seed_demo_data", force=True, verbosity=0)
    counts = {u: CleansingIssue.objects.filter(unit__code=u, status=IssueStatus.OPEN).count() for u in ("RMU", "PLU", "PIU")}
    assert counts == {"RMU": 5, "PLU": 2, "PIU": 1}
    call_command("seed_demo_data", force=True, if_missing=True, verbosity=0)
    assert CleansingIssue.objects.count() == 8
