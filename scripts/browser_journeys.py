"""Browser journeys for WaterSource (Playwright, headless Chromium) — the two main paths through the system.

Journey 1 — client: sign in as ``demo.client``, start a licence application, upload a
document, submit it, see it listed.
Journey 2 — staff: sign in as ``demo.reviewer``, open the review queue, open the
application just submitted, add a comment and approve it to the next stage.

Runs against any environment that has the demo users (``manage.py seed_demo_data``)::

    pip install playwright && playwright install chromium
    BASE_URL=https://watersource-production.up.railway.app python scripts/browser_journeys.py

Environment: ``BASE_URL`` (default http://127.0.0.1:8000), ``DEMO_PASSWORD``
(default WaterSource-Demo-2026!), ``SHOTS`` (directory for screenshots, default
``./browser-shots``), ``HEADED=1`` to watch it. Exit code 0 = both journeys passed.
Not collected by pytest: it needs a running server.
"""
from __future__ import annotations

import glob
import os
import re
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
PASSWORD = os.environ.get("DEMO_PASSWORD", "WaterSource-Demo-2026!")
SHOTS = Path(os.environ.get("SHOTS", "browser-shots"))
SHOTS.mkdir(parents=True, exist_ok=True)
CLIENT, REVIEWER = "demo.client@example.com", "demo.reviewer@wra-demo.local"


def shot(page: Page, name: str) -> None:
    """Full-page screenshot into ``SHOTS``."""
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def login(page: Page, email: str) -> None:
    """Sign in through the login form (no MFA for client/reviewer demo users)."""
    page.goto(f"{BASE}/accounts/login/")
    page.fill("input[name=username]", email)
    page.fill("input[name=password]", PASSWORD)
    page.click("button.btn-primary")
    page.wait_for_load_state("networkidle")
    assert "/accounts/login" not in page.url, f"login failed for {email}: {page.url}"


def journey_client(page: Page) -> str:
    """Client applies for a licence; returns the application reference."""
    login(page, CLIENT)
    shot(page, "01-client-home")
    page.goto(f"{BASE}/licensing/applications/new/")
    page.select_option("select[name=parish]", label="St. Catherine")
    page.select_option("select[name=water_source]", "river")
    page.fill("input[name=source_name]", "Rio Cobre (browser journey)")
    page.fill("input[name=daily_volume_requested_m3]", "850")
    page.fill("textarea[name=purpose]", "Irrigation of 12 ha citrus — created by scripts/browser_journeys.py")
    page.fill("textarea[name=applicant_address]", "Bog Walk, St. Catherine")
    page.fill("input[name=applicant_phone]", "876-555-0100")
    shot(page, "02-client-application-form")
    page.click("button.btn-primary")
    page.wait_for_load_state("networkidle")
    m = re.search(r"/applications/([A-Z0-9-]+)/", page.url)
    assert m, f"no application reference in {page.url}"
    ref = m.group(1)
    # upload a small PDF (a minimal valid PDF is enough for the type check)
    with tempfile.NamedTemporaryFile("wb", suffix=".pdf", delete=False) as fh:
        fh.write(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")
        pdf = fh.name
    page.set_input_files("input[type=file]", pdf)
    page.click("form[action$='/upload/'] button")
    page.wait_for_load_state("networkidle")
    shot(page, "03-client-document-uploaded")
    page.click("form[action$='/submit/'] button")
    page.wait_for_load_state("networkidle")
    expect(page.locator("body")).to_contain_text("Under review")
    shot(page, "04-client-submitted")
    page.goto(f"{BASE}/licensing/applications/")
    expect(page.locator("body")).to_contain_text(ref)
    shot(page, "05-client-application-list")
    page.click("form[action$='/logout/'] button")
    return ref


def journey_staff(page: Page, ref: str) -> None:
    """Reviewer finds the application in the queue, comments, and approves it onward."""
    login(page, REVIEWER)
    page.goto(f"{BASE}/workflow/queue/")
    shot(page, "06-staff-queue")
    page.click(f"a:has-text('{ref}')")
    page.wait_for_load_state("networkidle")
    shot(page, "07-staff-workflow-detail")
    # the decision panel posts over HTMX and swaps itself in place; wait for each response
    page.fill("textarea[name=comment]", "Documents complete — passing to hydrogeology. (browser journey)")
    with page.expect_response(lambda r: r.url.endswith("/act/")):
        page.click("button[name=action][value=comment]")
    with page.expect_response(lambda r: r.url.endswith("/act/")):
        page.click("button[name=action][value=approve]")
    page.reload()
    expect(page.locator("body")).to_contain_text("Hydrogeology review")
    expect(page.locator("body")).to_contain_text("passing to hydrogeology")
    shot(page, "08-staff-approved-to-next-stage")


def main() -> int:
    """Run both journeys; print PASS/FAIL per journey and return a shell exit code."""
    with sync_playwright() as p:
        exe = os.environ.get("CHROME_EXECUTABLE") or next(iter(glob.glob("/opt/pw-browsers/chromium*/chrome-linux*/chrome")), None)
        browser = p.chromium.launch(headless=not os.environ.get("HEADED"), executable_path=exe)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900}, ignore_https_errors=True)
        page = ctx.new_page()
        page.set_default_timeout(20_000)
        failures = 0
        t0 = time.time()
        try:
            ref = journey_client(page)
            print(f"PASS journey 1 (client) — application {ref}")
        except Exception as exc:  # noqa: BLE001 — report and continue to the next journey
            failures += 1
            shot(page, "ERR-journey-1")
            print(f"FAIL journey 1 (client): {exc}")
            ref = ""
        if ref:
            try:
                journey_staff(page, ref)
                print("PASS journey 2 (staff review)")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                shot(page, "ERR-journey-2")
                print(f"FAIL journey 2 (staff): {exc}")
        browser.close()
    print(f"{2 - failures}/2 journeys passed in {time.time() - t0:.1f}s — screenshots in {SHOTS}/")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
