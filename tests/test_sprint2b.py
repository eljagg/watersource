"""Sprint 2b (v0.4.0): model output category + adapters, anomaly flags, profiling report, gis_reader role, governance view."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from apps.catalog.models import DataCategory
from apps.obs.model_adapters import parse_map, swatplus_channel_rows, wflow_csv_rows
from apps.obs.models import ModelOutput, ModelRun, WaterQualitySample
from apps.ref.models import StreamflowStation
from apps.submissions.models import RecordStatus
from apps.submissions.promotion import promote
from apps.submissions.services import create_submission

# --- model output -----------------------------------------------------------------------


@pytest.fixture
def station(db, parish):
    return StreamflowStation.objects.create(name="Rio Cobre at Bog Walk", aliases=["BOGWALK"], parish=parish, approval_state="approved", classification="public")


@pytest.fixture
def run(db):
    return ModelRun.objects.create(code="riocobre-swatplus-2026a", name="Rio Cobre baseline", model_name="SWAT+ rev. 62")


SWAT_TEXT = """SWAT+ channel_sd_day   rev 62
jday mon day yr unit gis_id name area flo_in flo_out evap
--- --- --- --- --- --- --- ha m^3/s m^3/s m^3/s
1 1 1 2025 12 12 cha12 100.0 1.0 2.5 0.1
2 1 2 2025 12 12 cha12 100.0 1.0 2.75 0.1
1 1 1 2025 7 7 cha07 50.0 0.5 0.9 0.0
"""
WFLOW_TEXT = "time,Q_1,Q_2\n2025-01-01,3.2,NaN\n2025-01-02,3.4,1.1\n"


def test_swatplus_adapter_maps_channels_to_stations():
    rows = list(swatplus_channel_rows(SWAT_TEXT, "r1", parse_map("12=Rio Cobre at Bog Walk")))
    assert len(rows) == 3
    assert rows[0]["station"] == "Rio Cobre at Bog Walk" and rows[0]["feature_type"] == "station" and rows[0]["value"] == "2.5"
    assert rows[0]["observed_at"] == "2025-01-01T00:00:00"
    assert rows[2]["station"] == "" and rows[2]["feature_type"] == "reach" and rows[2]["feature_ref"] == "channel 7"


def test_wflow_adapter_skips_nan():
    rows = list(wflow_csv_rows(WFLOW_TEXT, "r1", {"1": "Rio Cobre at Bog Walk"}))
    assert [r["value"] for r in rows] == ["3.2", "3.4", "1.1"]
    assert rows[0]["station"] == "Rio Cobre at Bog Walk" and rows[2]["feature_ref"] == "gauge 2"


@pytest.mark.django_db
def test_model_output_submission_promotes_into_table(reviewer, station, run):
    version = DataCategory.objects.get(code="model_output").current_version
    rows = list(swatplus_channel_rows(SWAT_TEXT, run.code, {"12": station.name}))
    sub = create_submission(version, rows, reviewer)
    assert sub.rejected_count == 0 and sub.row_count == 3
    promote(sub, reviewer, "staff_only")
    out = ModelOutput.objects.filter(run=run)
    assert out.count() == 3
    first = out.get(station=station, observed_at__day=1)
    assert first.value == Decimal("2.5") and first.variable == "discharge_m3_s" and first.approval_state == "approved"
    assert out.filter(feature_type="reach", feature_ref="channel 7").exists()


@pytest.mark.django_db
def test_unknown_run_code_is_rejected(reviewer, station):
    version = DataCategory.objects.get(code="model_output").current_version
    sub = create_submission(version, [{"run": "nope", "feature_type": "station", "station": station.name, "variable": "discharge_m3_s", "observed_at": "2025-01-01T00:00:00", "value": "1"}], reviewer)
    assert sub.rejected_count == 1


@pytest.mark.django_db
def test_import_model_output_command(reviewer, station, run, tmp_path):
    f = tmp_path / "channel_sd_day.txt"
    f.write_text(SWAT_TEXT)
    call_command("import_model_output", str(f), format="swatplus", run=run.code, user=reviewer.email, map="12=Rio Cobre at Bog Walk")
    from apps.submissions.models import Submission

    assert Submission.objects.filter(category_version__category__code="model_output").latest("id").accepted_count == 3


# --- anomaly flags ------------------------------------------------------------------------


@pytest.mark.django_db
def test_anomaly_flags_out_of_character_duplicate_and_future(client_user, well):
    """A chloride value far from the well's record, a duplicate timestamp and a future date are flagged, not rejected."""
    base = timezone.now() - timedelta(days=400)
    for i in range(10):
        WaterQualitySample.objects.create(well=well, source_type="well", sampled_at=base + timedelta(days=30 * i), chloride_mg_l=Decimal(20 + (i % 3)),
                                          approval_state="approved", classification="staff_only")
    version = DataCategory.objects.get(code="water_quality").current_version
    dup_at = timezone.localtime(base + timedelta(days=30 * 3)).strftime("%Y-%m-%dT%H:%M:%S")  # submitters write Jamaica local time
    rows = [
        {"source_type": "well", "well": well.name, "sampled_at": "2026-01-15T08:00:00", "chloride_mg_l": "21"},   # normal
        {"source_type": "well", "well": well.name, "sampled_at": "2026-02-15T08:00:00", "chloride_mg_l": "900"},  # out of character
        {"source_type": "well", "well": well.name, "sampled_at": dup_at, "chloride_mg_l": "22"},                 # duplicate
        {"source_type": "well", "well": well.name, "sampled_at": "2099-01-01T08:00:00", "chloride_mg_l": "21"},   # future
    ]
    sub = create_submission(version, rows, client_user)
    recs = {r.row_no: r for r in sub.records.all()}
    assert recs[1].status == RecordStatus.ACCEPTED and not recs[1].flags
    assert recs[2].status == RecordStatus.FLAGGED and any("out of character" in f for f in recs[2].flags)
    assert any("already exists" in f for f in recs[3].flags)
    assert any("in the future" in f for f in recs[4].flags)
    assert sub.rejected_count == 0 and sub.flagged_count == 3 and sub.accepted_count == 1
    assert sub.anomaly_count == 3


@pytest.mark.django_db
def test_anomaly_flat_line(client_user, well):
    version = DataCategory.objects.get(code="water_quality").current_version
    rows = [{"source_type": "well", "well": well.name, "sampled_at": f"2026-03-{d:02d}T08:00:00", "chloride_mg_l": "25"} for d in range(1, 8)]
    sub = create_submission(version, rows, client_user)
    assert any("same value" in f for r in sub.records.all() for f in r.flags)


# --- profiling (M3) -----------------------------------------------------------------------


def test_profile_file_finds_issues(tmp_path):
    from apps.core.profiling import profile_file, render_markdown

    csvf = tmp_path / "wells_legacy.csv"
    csvf.write_text(
        "WellName,Parish,Depth,Drilled\n"
        "Bog Walk 1,St. Catherine,120,2001-03-04\n"
        "bog walk 1 ,St Catherine,N/A,04/03/2001\n"
        "May Pen 5,Clarendon,95,2005-07-01\n"
        "May Pen 5,Clarendon,95,2005-07-01\n"
        "Cornwall 9,St. James,9999,2010-01-01\n",
        encoding="utf-8",
    )
    lookup = {"bog walk 1": "Bog Walk 1", "may pen 5": "May Pen 5"}
    prof = profile_file(csvf, {r"well": lookup})
    assert prof.rows == 5 and prof.duplicate_rows == 1
    cols = {c.name: c for c in prof.columns}
    assert cols["Depth"].inferred == "integer" and cols["Depth"].blank == 1 and "N/A" in cols["Depth"].null_tokens
    assert len(cols["Drilled"].date_formats) == 2
    assert cols["WellName"].reference_match["unmatched"] == 1 and cols["WellName"].reference_match["normalised"] >= 1
    assert cols["WellName"].leading_trailing_space == 1
    md = render_markdown([prof])
    assert "Data Quality Assessment Report" in md and "date formats" in md and "Cornwall 9" in md


@pytest.mark.django_db
def test_profile_source_command(tmp_path):
    (tmp_path / "a.csv").write_text("id,value\n1,2\n2,3\n")
    call_command("profile_source", str(tmp_path / "a.csv"), out=str(tmp_path / "dqa"), no_reference=True)
    assert (tmp_path / "dqa.md").exists() and (tmp_path / "dqa.json").exists()


# --- gis_reader role and governance view ------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_setup_gis_reader_creates_read_only_role():
    role = "test_gis_reader_ws"
    try:
        call_command("setup_gis_reader", role=role, password="x-y-z-123")
        with connection.cursor() as cur:
            cur.execute("SELECT has_table_privilege(%s, 'ref_well', 'SELECT'), has_table_privilege(%s, 'ref_well', 'INSERT'), has_table_privilege(%s, 'accounts_user', 'SELECT')", [role, role, role])
            can_read, can_write, sees_users = cur.fetchone()
        assert can_read and not can_write and not sees_users
    finally:
        with connection.cursor() as cur:
            cur.execute(f"DROP OWNED BY {role}; DROP ROLE IF EXISTS {role}")


@pytest.mark.django_db
def test_governance_view_counts_real_actions():
    with connection.cursor() as cur:
        cur.execute("SELECT pg_get_viewdef('bi.governance_kpis'::regclass)")
        sql = cur.fetchone()[0]
    assert "dpa.subject_access_export" in sql and "account.export" not in sql


@pytest.mark.django_db
def test_dashboards_index_reads_display_settings(client, reviewer):
    from apps.reports.models import DisplaySettings

    ds = DisplaySettings.get()
    ds.data_refresh_minutes = 7
    ds.save()
    client.force_login(reviewer)
    assert "every 7 minutes" in client.get("/dashboards/").content.decode()


# --- re-seeding keeps demo accounts (and their authenticator enrolments) -----------------------


@pytest.mark.django_db
def test_reseed_keeps_demo_users_and_mfa_devices():
    """``seed_demo_data --force`` twice: demo.admin keeps the same primary key and its confirmed TOTP device."""
    from django.contrib.auth import get_user_model
    from django_otp.plugins.otp_totp.models import TOTPDevice

    call_command("load_reference_data", verbosity=0)
    call_command("seed_demo_data", force=True, verbosity=0)
    admin = get_user_model().objects.get(email="demo.admin@wra-demo.local")
    TOTPDevice.objects.create(user=admin, name="phone", confirmed=True)
    call_command("seed_demo_data", force=True, verbosity=0)
    again = get_user_model().objects.get(email="demo.admin@wra-demo.local")
    assert again.pk == admin.pk and again.is_superuser
    assert TOTPDevice.objects.filter(user=again, confirmed=True).exists()


# --- WRA units and Super Users (stakeholder model) ----------------------------------------------


@pytest.mark.django_db
def test_units_seeded_and_super_user_shown(client, reviewer):
    from apps.accounts.models import Unit

    call_command("bootstrap_roles", verbosity=0)
    assert Unit.objects.filter(is_operating=True).count() == 3
    assert Unit.objects.filter(has_super_user=True).count() == 6
    plu = Unit.objects.get(code="PLU")
    reviewer.unit, reviewer.is_super_user = plu, True
    reviewer.save()
    assert list(plu.super_users) == [reviewer]
    client.force_login(reviewer)
    html = client.get("/accounts/profile/").content.decode()
    assert "Permits &amp; Licences Unit" in html and "Super User" in html


@pytest.mark.django_db
def test_seed_if_missing_skips_when_present():
    from io import StringIO

    call_command("load_reference_data", verbosity=0)
    call_command("seed_demo_data", force=True, verbosity=0)
    out = StringIO()
    call_command("seed_demo_data", force=True, if_missing=True, stdout=out)
    assert "already present" in out.getvalue()


# --- branding colours and copyright -----------------------------------------------------------


@pytest.mark.django_db
def test_footer_copyright_uses_current_year_and_colours_are_emitted(client):
    from django.utils import timezone as tz

    from apps.core.branding import SiteBranding

    html = client.get("/").content.decode()
    assert f"© {tz.localdate().year} Water Resources Authority of Jamaica" in html
    assert "--ws-tile:#1c5ac6" in html and "--ws-accent:#b22234" in html
    b = SiteBranding.get()
    b.tile_color, b.accent_color, b.copyright_text = "#123456", "#abcdef", "Copyright {year} WRA"
    b.save()
    html = client.get("/").content.decode()
    assert "--ws-tile:#123456" in html and f"Copyright {tz.localdate().year} WRA" in html


@pytest.mark.django_db
def test_active_tab_marked(client, reviewer):
    client.force_login(reviewer)
    html = client.get("/dashboards/").content.decode()
    assert 'class="nav-link is-active">Dashboards' in html
    assert 'class="nav-link ">Data submissions' in html
