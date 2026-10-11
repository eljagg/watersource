"""v0.10.0: living water background, personalised Home greeting, "Last viewed", nav option B (Open data tab)."""
import pytest
from django.test import Client

from apps.core.models import RecentView


@pytest.mark.django_db
def test_water_background_and_pause_control_on_every_page(client):
    html = client.get("/").content.decode()
    assert '<div class="water" aria-hidden="true">' in html and html.count('class="wave w') == 3
    assert "data-motion-toggle" in html and "ws-motion" in html  # footer pause control, remembered per browser
    assert '<div class="water"' in client.get("/open-data/").content.decode()
    css = open("static/css/app.css", encoding="utf-8").read()
    assert "prefers-reduced-motion" in css and "html.still .water" in css and "backdrop-filter" in css


@pytest.mark.django_db
def test_nav_option_b_open_data_tab_and_api_still_reachable(client):
    html = client.get("/").content.decode()
    assert '>Open data</a>' in html and 'class="nav-link ' in html
    assert '/api/docs/" class="nav-link' not in html  # API tab gone from the header …
    assert 'href="/api/docs/"' in client.get("/open-data/").content.decode()  # … but documented from Open data


@pytest.mark.django_db
def test_anonymous_home_has_no_greeting_or_history(client):
    html = client.get("/").content.decode()
    assert 'id="welcome"' not in html and "Last viewed" not in html
    assert RecentView.objects.count() == 0


@pytest.mark.django_db
def test_signed_in_home_greets_by_first_name_with_weekday_and_queue(reviewer):
    c = Client()
    c.force_login(reviewer)
    html = c.get("/").content.decode()
    first = reviewer.full_name.split()[0]
    assert f", {first}." in html and any(w in html for w in ("Good morning", "Good afternoon", "Good evening"))
    assert any(d in html for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))
    assert "waiting on you" in html or "Nothing is waiting on you" in html


@pytest.mark.django_db
def test_last_viewed_records_pages_and_shows_latest_five(reviewer):
    c = Client()
    c.force_login(reviewer)
    c.get("/open-data/monitoring-sites/")
    c.get("/maps/")
    c.get("/open-data/monitoring-sites/")  # again: refreshed, not duplicated
    c.get("/", HTTP_HX_REQUEST="true")
    c.get("/accounts/profile/")  # account pages are never remembered
    labels = list(RecentView.objects.filter(user=reviewer).values_list("label", flat=True))
    assert labels == ["Open data › Monitoring sites", "Map"]
    for slug in ("groundwater-levels-monthly", "streamflow-monthly", "water-quality", "licence-register", "wmu-balance"):
        c.get(f"/open-data/{slug}/")
    assert RecentView.objects.filter(user=reviewer).count() == 7
    c.get("/open-data/groundwater-levels-monthly/?page=2")  # same page: refreshed, not duplicated
    assert RecentView.objects.filter(user=reviewer).count() == 7
    c.get("/licensing/applications/")
    c.get("/submissions/")
    assert RecentView.objects.filter(user=reviewer).count() == RecentView.KEEP  # oldest dropped
    assert not RecentView.objects.filter(user=reviewer, path="/maps/").exists()  # /maps/ was the oldest visit
    html = c.get("/").content.decode()
    assert "Last viewed" in html and html.count("<li>") - html.count("<li>", 0, html.find('id="recent-views"')) >= 5
    assert 'href="/open-data/wmu-balance/"' in html and "Open data › WMU balance" in html
    anon = Client().get("/").content.decode()
    assert "Last viewed" not in anon


# --- v0.10.1 "← Back" beside the breadcrumbs ---------------------------------------------------


@pytest.mark.django_db
def test_back_link_returns_inside_the_app_or_home(client):
    html = client.get("/maps/").content.decode()
    assert '<a class="back-link" href="/">← Back</a>' in html  # arrived from outside: Home
    html = client.get("/maps/", HTTP_REFERER="http://testserver/open-data/monitoring-sites/?q=bog").content.decode()
    assert '<a class="back-link" href="/open-data/monitoring-sites/?q=bog">← Back</a>' in html
    html = client.get("/maps/", HTTP_REFERER="https://evil.example/open-data/").content.decode()
    assert 'class="back-link" href="/"' in html  # another site never becomes a Back target
    html = client.get("/maps/", HTTP_REFERER="http://testserver/maps/").content.decode()
    assert 'class="back-link" href="/"' in html  # a reload does not point at itself
    assert "back-link" not in client.get("/").content.decode()
