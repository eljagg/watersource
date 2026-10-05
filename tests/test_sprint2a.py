"""Sprint 2a: restricted classification (Methodology §4A / ADR-0002) and the four dashboards + wall mode."""
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import Client

from apps.accounts import roles
from apps.core.models import AuditLog, Classification
from apps.core.restrict import coarsen, mask_site
from apps.ref.models import Well
from apps.reports import services as bi
from apps.reports.dashboards import DASHBOARDS, WALL_ORDER
from apps.reports.views import dashboard_payload

from .conftest import _user


@pytest.fixture
def public_supply_well(db, parish):
    return Well.objects.create(name="NWC Bog Walk Supply", parish=parish, easting=Decimal("758234.500"), northing=Decimal("653101.250"), elevation_m=42,
                               is_public_supply=True, approval_state="approved", classification="public")


def test_coarsen_snaps_to_grid_centre():
    assert coarsen(Decimal("758234.5")) == Decimal("758500")
    assert coarsen(None) is None


def test_public_supply_coordinates_masked_for_public_but_not_hydrogeologist(public_supply_well, client_user):
    hydro = _user("hg@wra.gov.jm", roles.HYDROGEOLOGIST)
    m = mask_site(public_supply_well, None)
    assert m["coordinates_coarsened"] and m["easting"] == Decimal("758500") and m["elevation_m"] is None
    assert mask_site(public_supply_well, client_user)["coordinates_coarsened"]
    assert not mask_site(public_supply_well, hydro)["coordinates_coarsened"]


def test_api_masks_public_supply_wells(public_supply_well, well):
    r = Client().get("/api/v1/wells/")
    rows = {x["name"]: x for x in r.json()["results"]}
    assert rows["NWC Bog Walk Supply"]["coordinates_coarsened"] is True and Decimal(str(rows["NWC Bog Walk Supply"]["easting"])) == Decimal("758500")
    assert rows["NWC Bog Walk Supply"]["elevation_m"] is None
    assert rows["Bog Walk 1"]["coordinates_coarsened"] is False and Decimal(str(rows["Bog Walk 1"]["easting"])) == Decimal("760000")


def test_restricted_rows_hidden_from_ordinary_staff(db, parish):
    Well.objects.create(name="Restricted Well", parish=parish, approval_state="approved", classification=Classification.RESTRICTED)
    updater = _user("upd@wra.gov.jm", roles.UPDATER)
    reviewer = _user("rev2@wra.gov.jm", roles.REVIEWER)
    assert not Well.objects.visible_to(updater).filter(name="Restricted Well").exists()
    assert Well.objects.visible_to(reviewer).filter(name="Restricted Well").exists()
    assert not Well.objects.visible_to(None).filter(name="Restricted Well").exists()


def test_classification_and_public_supply_changes_are_audited(well):
    well.classification = Classification.RESTRICTED
    well.save()
    well.is_public_supply = True
    well.save()
    actions = list(AuditLog.objects.filter(object_id=str(well.pk)).values_list("action", flat=True))
    assert "classification.changed" in actions and "site.public_supply_changed" in actions


def test_dashboard_payloads_and_pages(db):
    call_command("seed_demo_data", "--force", verbosity=0)
    bi.refresh_all()
    for slug in WALL_ORDER:
        payload = dashboard_payload(slug, wall=True)
        assert payload["kpis"] and payload["panels"]
        for p in payload["panels"]:
            assert p["view"] in payload["data"], p["view"]
    assert dashboard_payload("licensing")["data"]["bi.licensing_kpis"][0]["active_licences"] > 0
    assert len(DASHBOARDS) == 4
    staff = _user("dash@wra.gov.jm", roles.REVIEWER)
    c = Client()
    c.force_login(staff)
    assert c.get("/dashboards/").status_code == 200
    assert c.get("/dashboards/monitoring/").status_code == 200
    r = c.get("/dashboards/monitoring/data/")
    assert r.status_code == 200 and "bi.well_level_status" in r.json()["data"]
    assert c.get("/wall/").status_code == 200


def test_wall_role_sees_wall_only(db):
    kiosk = _user("wall@wra.gov.jm", roles.WALL_DISPLAY)
    client = Client()
    client.force_login(kiosk)
    assert client.get("/wall/").status_code == 200
    assert client.get("/dashboards/licensing/data/?wall=1").status_code == 200
    assert client.get("/dashboards/licensing/data/").status_code == 403
    assert client.get("/dashboards/").status_code == 403
    guest = Client()
    assert guest.get("/wall/").status_code == 302  # login required


def test_staff_navigation_reaches_every_tool(db):
    """Every staff page is linked from the header or the home page — no typed URLs (Omar, 5 Oct)."""
    staff = _user("nav@wra.gov.jm", roles.REVIEWER)
    staff.is_staff = True
    staff.save()
    c = Client()
    c.force_login(staff)
    body = c.get("/").content.decode()
    for href in ("/workflow/queue/", "/dashboards/", "/wall/", "/admin/", "/api/docs/"):
        assert f'href="{href}"' in body, href
    wall = c.get("/wall/").content.decode()
    assert 'href="/dashboards/"' in wall
    anon = Client().get("/").content.decode()
    assert "Staff tools" not in anon


def test_display_settings_drive_wall_and_refresh(db):
    """Rotation/refresh timing and order come from the admin-editable DisplaySettings; stale data refreshes on demand."""
    from django.core.cache import cache

    from apps.reports.models import DisplaySettings

    ds = DisplaySettings.get()
    ds.rotate_seconds, ds.page_refresh_seconds, ds.wall_order, ds.wall_theme = 25, 40, ["executive", "licensing"], "light"
    ds.save()
    assert DisplaySettings.objects.count() == 1 and DisplaySettings.get().order == ["executive", "licensing"]
    staff = _user("ds@wra.gov.jm", roles.REVIEWER)
    c = Client()
    c.force_login(staff)
    body = c.get("/wall/").content.decode()
    assert "rotate: 25" in body and "refresh: 40" in body and 'data-dot="1"' in body and 'data-dot="2"' not in body and "Exit wall" in body
    assert 'class="h-full"' in body  # light theme → no dark class
    cache.delete("bi:refreshed_at")
    assert bi.refresh_if_stale(5) is True
    assert bi.refresh_if_stale(5) is False  # fresh now
    r = c.get("/dashboards/licensing/data/")
    assert r.json()["refreshed_at"]


# --- MFA enrolment page and CSRF failure handling (v0.3.3) ---------------------------------


@pytest.mark.django_db
def test_mfa_setup_shows_qr_and_manual_key(client):
    """The enrolment page renders an inline SVG QR code and the grouped manual key."""
    from django.contrib.auth import get_user_model

    u = get_user_model().objects.create_user(email="mfa@example.com", password="Str0ng-Passw0rd!!", full_name="M")
    client.force_login(u)
    r = client.get("/accounts/mfa/setup/")
    assert r.status_code == 200
    html = r.content.decode()
    assert "<svg" in html and "Scan this QR code" in html
    assert "WaterSource Jamaica" in html
    assert "Enter the key manually" in html


@pytest.mark.django_db
def test_mfa_setup_accepts_spaced_code(client):
    """'123 456' as shown by authenticator apps is accepted as 123456."""
    from django.contrib.auth import get_user_model
    from django_otp.oath import totp
    from django_otp.plugins.otp_totp.models import TOTPDevice

    u = get_user_model().objects.create_user(email="mfa2@example.com", password="Str0ng-Passw0rd!!", full_name="M")
    client.force_login(u)
    client.get("/accounts/mfa/setup/")
    device = TOTPDevice.objects.get(user=u, confirmed=False)
    code = f"{totp(device.bin_key, device.step, device.t0, device.digits, device.drift):06d}"
    r = client.post("/accounts/mfa/setup/", {"token": code[:3] + " " + code[3:]})
    assert r.status_code == 302
    assert TOTPDevice.objects.get(user=u).confirmed is True


@pytest.mark.django_db
def test_csrf_failure_on_logout_signs_out(client):
    """A stale sign-out form (bad CSRF token) still signs the user out instead of a bare 403."""
    from django.contrib.auth import get_user_model
    from django.test import Client

    u = get_user_model().objects.create_user(email="csrf@example.com", password="Str0ng-Passw0rd!!", full_name="C")
    c = Client(enforce_csrf_checks=True)
    c.force_login(u)
    r = c.post("/accounts/logout/", {"csrfmiddlewaretoken": "stale"})
    assert r.status_code == 302 and r["Location"].startswith("/accounts/login")
    assert c.get("/accounts/profile/").status_code == 302  # no longer signed in


@pytest.mark.django_db
def test_csrf_failure_elsewhere_is_friendly(client):
    """Other CSRF failures get the explanatory page, still a 403."""
    from django.test import Client

    c = Client(enforce_csrf_checks=True)
    r = c.post("/accounts/login/", {"username": "x", "password": "y"})
    assert r.status_code == 403
    assert "That page had expired" in r.content.decode()


# --- Site branding (v0.3.4) ---------------------------------------------------------------


@pytest.fixture
def superuser(db, client):
    """A superuser for admin tests, signed in and MFA-verified."""
    from django.contrib.auth import get_user_model
    from django_otp.plugins.otp_totp.models import TOTPDevice

    u = get_user_model().objects.create_superuser(email="root@example.com", password="Str0ng-Passw0rd!!", full_name="Root")
    device = TOTPDevice.objects.create(user=u, name="t", confirmed=True)
    client.force_login(u)
    session = client.session
    session["otp_device_id"] = device.persistent_id
    session.save()
    return u


def _png(w=120, h=40):
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (0, 158, 224)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.django_db
def test_branding_defaults_render(client):
    """Without any upload the header shows the defaults and the logo URL is a 404."""
    r = client.get("/")
    html = r.content.decode()
    assert "WaterSource" in html and "Water Resources Authority of Jamaica" in html
    assert client.get("/branding/logo/").status_code == 404


@pytest.mark.django_db
def test_branding_upload_via_admin(client, superuser):
    """Uploading a PNG and changing names through the admin changes every page and serves the logo."""
    from django.core.cache import cache
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.branding import SiteBranding

    client.force_login(superuser)
    r = client.get("/admin/core/sitebranding/")
    assert r.status_code == 302 and r["Location"].endswith("/admin/core/sitebranding/1/change/")
    r = client.post(r["Location"], {
        "organisation_name": "Water Resources Authority", "product_name": "HydroHub", "tagline": "Jamaica", "footer_text": "",
        "copyright_text": "© {year} WRA", "tile_color": "#1c5ac6", "accent_color": "#b22234",
        "logo_upload": SimpleUploadedFile("logo.png", _png(), content_type="image/png"),
    })
    assert r.status_code == 302, r.content.decode()[:500]
    cache.clear()
    b = SiteBranding.get()
    assert b.product_name == "HydroHub" and b.has_logo and b.logo_type == "image/png"
    logo = client.get("/branding/logo/")
    assert logo.status_code == 200 and logo["Content-Type"] == "image/png" and logo["Cache-Control"].startswith("public")
    html = client.get("/").content.decode()
    assert "HydroHub" in html and "/branding/logo/?v=" in html
    admin_html = client.get("/admin/").content.decode()
    assert "HydroHub admin console" in admin_html and "Django administration" not in admin_html


@pytest.mark.django_db
def test_branding_rejects_bad_files(client, superuser):
    """A text file or an SVG with scripting is refused."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    client.force_login(superuser)
    url = "/admin/core/sitebranding/1/change/"
    client.get("/admin/core/sitebranding/")  # creates the row
    base = {"organisation_name": "X", "product_name": "Y", "tagline": "", "footer_text": "", "copyright_text": "", "tile_color": "#1c5ac6", "accent_color": "#b22234"}
    r = client.post(url, {**base, "logo_upload": SimpleUploadedFile("x.txt", b"hello", content_type="text/plain")})
    assert r.status_code == 200 and "Use a PNG, JPEG, WebP or SVG image" in r.content.decode()
    bad_svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    r = client.post(url, {**base, "logo_upload": SimpleUploadedFile("x.svg", bad_svg, content_type="image/svg+xml")})
    assert r.status_code == 200 and "scripting" in r.content.decode()
