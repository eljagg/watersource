"""Sprint 1: technical roles, observation quality/approval, site master, seed loaders, bi views."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts import roles
from apps.core.models import ApprovalState, ObservationGrade
from apps.obs import services as obs_services
from apps.obs.models import ApprovalPeriod, HistoryMethod, RecordHistory, SeriesKind, WellWaterLevel
from apps.ref.models import Instrument, InstrumentInstallation, InstrumentKind, Parish, Qualifier, SiteVisit, StreamflowStation, Well, WellEvent, WellPumpTest, WellStatusEvent
from apps.reports import services as bi

from .conftest import _user


@pytest.fixture
def hydrologist(db):
    return _user("hydro@wra.gov.jm", roles.HYDROLOGIST)


@pytest.fixture
def technician(db):
    return _user("tech@wra.gov.jm", roles.TECHNICIAN)


@pytest.fixture
def levels(db, well):
    t0 = timezone.now() - timedelta(days=10)
    return [WellWaterLevel.objects.create(well=well, measured_at=t0 + timedelta(days=i), water_level_m=Decimal("12.345") + i) for i in range(5)]


def test_technical_roles_exist_and_see_working_data(hydrologist, technician, well, levels):
    for name in (roles.HYDROLOGIST, roles.HYDROGEOLOGIST, roles.TECHNICIAN):
        assert Group.objects.filter(name=name).exists()
    assert WellWaterLevel.objects.visible_to(hydrologist).count() == 5  # working rows visible to hydrologists
    assert WellWaterLevel.objects.visible_to(technician).count() == 0  # technicians see approved only
    assert hydrologist.mfa_required and not technician.mfa_required


def test_approve_period_flips_rows_and_records_period(hydrologist, well, levels):
    start = levels[0].measured_at
    period = obs_services.approve_period(SeriesKind.WELL_LEVEL, well, start, start + timedelta(days=3), hydrologist, remarks="September round")
    assert period.rows_approved == 3
    assert WellWaterLevel.objects.filter(approval_state=ApprovalState.APPROVED).count() == 3
    assert ApprovalPeriod.objects.get().site == well


def test_technician_cannot_approve(technician, well, levels):
    with pytest.raises(PermissionDenied):
        obs_services.approve_period(SeriesKind.WELL_LEVEL, well, levels[0].measured_at, timezone.now(), technician)


def test_regrade_working_row_by_technician_and_approved_row_keeps_history(hydrologist, technician, levels):
    row = levels[0]
    obs_services.regrade(row, ObservationGrade.FAIR, ["PUMPING"], technician)
    row.refresh_from_db()
    assert row.grade == ObservationGrade.FAIR and row.qualifiers == ["PUMPING"] and row.graded_by == technician
    row.approval_state = ApprovalState.APPROVED
    row.save()
    with pytest.raises(PermissionDenied):
        obs_services.regrade(row, ObservationGrade.POOR, None, technician, reason="x")
    with pytest.raises(ValueError):
        obs_services.regrade(row, ObservationGrade.POOR, None, hydrologist)  # reason required
    obs_services.regrade(row, ObservationGrade.POOR, None, hydrologist, reason="Logger drift found on download")
    h = RecordHistory.objects.get()
    assert h.method == HistoryMethod.REGRADE and h.old_values["grade"] == "fair" and h.new_values["grade"] == "poor"


def test_well_status_event_updates_current_flags(well):
    WellStatusEvent.objects.create(well=well, event=WellEvent.PUMP_INSTALLED, occurred_on=date(2024, 3, 1))
    WellStatusEvent.objects.create(well=well, event=WellEvent.ABANDONED, occurred_on=date(2026, 1, 15))
    well.refresh_from_db()
    assert well.pump_attached is True and well.is_abandoned is True and well.abandoned_date == date(2026, 1, 15)


def test_pump_test_derives_specific_capacity(well):
    t = WellPumpTest.objects.create(well=well, constant_test_rate_m3_d=Decimal("2400"), constant_test_drawdown_m=Decimal("6"))
    assert t.specific_capacity_m3_d_m == Decimal("400")


def test_site_master_rows_belong_to_exactly_one_site(well, parish, technician):
    station = StreamflowStation.objects.create(name="Rio Cobre at Bog Walk", parish=parish)
    with pytest.raises(IntegrityError), transaction.atomic():
        SiteVisit.objects.create(well=well, station=station, visited_on=date.today(), visited_by=technician)
    with pytest.raises(IntegrityError), transaction.atomic():
        SiteVisit.objects.create(visited_on=date.today(), visited_by=technician)
    inst = Instrument.objects.create(kind=InstrumentKind.LEVEL_LOGGER, serial_number="LL-1")
    InstrumentInstallation.objects.create(instrument=inst, well=well, installed_on=date(2025, 1, 1))
    assert inst.current_installation.site == well


def test_load_reference_data_is_idempotent(db):
    call_command("load_reference_data", verbosity=0)
    n_parish, n_qual = Parish.objects.count(), Qualifier.objects.count()
    assert n_parish == 14 and n_qual >= 10
    call_command("load_reference_data", verbosity=0)
    assert Parish.objects.count() == n_parish and Qualifier.objects.count() == n_qual


def test_seed_demo_data_creates_and_wipes(db):
    call_command("seed_demo_data", "--force", verbosity=0)
    assert Well.objects.filter(name__startswith="DEMO").count() == 12
    assert WellWaterLevel.objects.filter(well__name__startswith="DEMO", approval_state=ApprovalState.APPROVED).exists()
    call_command("seed_demo_data", "--force", verbosity=0)  # idempotent
    assert Well.objects.filter(name__startswith="DEMO").count() == 12
    call_command("seed_demo_data", "--wipe", "--force", verbosity=0)
    assert not Well.objects.filter(name__startswith="DEMO").exists()


def test_bi_refresh_and_licensing_dashboard(db):
    call_command("seed_demo_data", "--force", verbosity=0)
    assert bi.refresh_all() == bi.BI_VIEWS
    data = bi.licensing_dashboard()
    assert set(data) == {v.split(".")[1] for v in bi.LICENSING_DASHBOARD}
    kpis = data["licensing_kpis"][0]
    assert kpis["active_licences"] > 0 and kpis["applications_open"] > 0
    assert bi.fetch("bi.applications_monthly", order_by="-month", limit=3)
    with pytest.raises(ValueError):
        bi.fetch("bi.nope")
    with pytest.raises(ValueError):
        bi.fetch("bi.licence_expiry", order_by="drop_table")
