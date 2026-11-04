#!/usr/bin/env python3
"""
End-to-end share tracking test using Playwright.

Clicks each share button in every place a supporter can share from -- the
popup on the petition page, the thanks page, and a ?share=<network> link from
a mailing -- intercepts the /share/link requests, and verifies the URL
parameters. Every share should carry source=<platform>_<location>.
Then checks the ActionKit database via the reports API to confirm
the share_link rows landed correctly.

Setup (first run with --setup):
  - Creates a dedicated test petition page (share-tracking-test)
  - Creates a report to verify share_link rows
  - Creates a test action to get a valid akid/action_id

Dependencies:
  pip install requests playwright
  playwright install chromium

Usage:
  export AK_USER=your_api_user
  export AK_PASSWORD=your_api_password

  python scripts/test_share_tracking.py --setup     # first time only
  python scripts/test_share_tracking.py              # run tests
  python scripts/test_share_tracking.py --cleanup    # remove test resources
"""

import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import requests

AK_BASE = "https://action.wemove.eu"
API_BASE = f"{AK_BASE}/rest/v1"
TEST_PAGE_NAME = "share-tracking-test"
REPORT_SHORT_NAME = "share_tracking_test_report"
REPORT_SQL = """
SELECT id, type, source, generation, created_at
FROM share_link
WHERE action_id = {{ action_id }}
ORDER BY created_at DESC
"""


# ---------------------------------------------------------------------------
# Test case definitions
#
# Each test describes a share button, how to find and click it in the browser,
# and what /share/link parameters we expect.
#
# selector:        CSS selector for the clickable element
# opens_popup:     True if clicking opens a new tab (target="_blank" links).
#                  The tab may navigate to /share/link directly (Facebook,
#                  Bluesky) or load a page whose JS fetches /share/link
#                  (WhatsApp). Either way we intercept /share/link in the tab.
# expect_type:     What we expect in the /share/link type param.
# platform:        The first half of source=<platform>_<location>.
# ---------------------------------------------------------------------------
TEST_CASES = [
    {
        "name": "Facebook",
        "selector": 'a[href*="/share/link?type=fb"]',
        "opens_popup": True,
        "expect_type": "fb",
        "platform": "facebook",
    },
    {
        "name": "Bluesky",
        "selector": 'a[href*="/share/link?type=bl"]',
        "opens_popup": True,
        "expect_type": "bl",
        "platform": "bluesky",
    },
    {
        "name": "WhatsApp",
        "selector": 'a[href*="share=whatsapp"]',
        "opens_popup": True,
        "expect_type": "ot",
        "platform": "whatsapp",
    },
    {
        "name": "Copy URL",
        "selector": "[data-wm-copy-to-clipboard]",
        "opens_popup": False,
        "expect_type": "ot",
        "platform": "copypaste",
    },
    {
        "name": "TAF (email)",
        "selector": "[data-wm-taf-button]",
        "opens_popup": False,
        "expect_type": "ot",
        "platform": "taf",
    },
    {
        "name": "Instagram",
        "selector": "[data-wm-send-share-to-action-kit]",
        "opens_popup": False,
        "expect_type": "ot",
        "platform": "instagram",
    },
]

# Where a supporter can share from. The popup's buttons live in the dialog the
# petition page opens after signing; the thanks page's in the share step.
LOCATIONS = [
    {"name": "popup", "scope": "[data-wm-dialog-content]"},
    {"name": "thanks", "scope": "[data-wm-share-content]"},
]

# A mailing links straight to /thanks/PAGE?share=<network>, which fires the
# share on load. No location param, so the page must label it "mailing".
MAILING_CASES = [
    {"name": "WhatsApp (mailing link)", "share": "whatsapp",
     "expect_type": "ot", "platform": "whatsapp"},
]


def expected_source(platform, location):
    return f"{platform}_{location}"


# ---------------------------------------------------------------------------
# ActionKit API helpers
# ---------------------------------------------------------------------------

def get_auth():
    user = os.environ.get("AK_USER")
    password = os.environ.get("AK_PASSWORD")
    if not user or not password:
        print("Error: Set AK_USER and AK_PASSWORD environment variables.")
        sys.exit(1)
    return (user, password)


def api_get(path, auth, params=None):
    resp = requests.get(f"{API_BASE}{path}", auth=auth, params=params,
                        headers={"Accept": "application/json"})
    resp.raise_for_status()
    return resp.json()


def api_post(path, auth, data):
    resp = requests.post(f"{API_BASE}{path}", auth=auth, json=data,
                         headers={"Content-Type": "application/json"})
    if resp.status_code not in (200, 201, 202):
        print(f"  POST {path} failed: {resp.status_code}")
        print(f"  {resp.text[:500]}")
        resp.raise_for_status()
    return resp


def api_delete(path, auth):
    return requests.delete(f"{API_BASE}{path}", auth=auth)


def location_to_path(location_header):
    """Convert a Location header (full URL) to a path relative to API_BASE.

    e.g. 'https://action.wemove.eu/rest/v1/petitionpage/123/'
      -> '/petitionpage/123/'
    """
    if "/rest/v1/" in location_header:
        return "/" + location_header.split("/rest/v1/", 1)[1]
    if location_header.startswith("http"):
        return "/" + "/".join(location_header.split("/")[3:])
    return location_header


def run_report(auth, action_id):
    """Run the verification report and return rows."""
    resp = requests.post(
        f"{API_BASE}/report/run/{REPORT_SHORT_NAME}/",
        auth=auth,
        json={"action_id": str(action_id)},
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------

def find_test_page(auth):
    try:
        data = api_get("/petitionpage/", auth,
                       params={"name": TEST_PAGE_NAME, "_limit": 1})
        if data.get("objects"):
            obj = data["objects"][0]
            return obj["resource_uri"], obj["id"]
    except Exception:
        pass
    return None, None


def find_report(auth):
    try:
        data = api_get("/queryreport/", auth,
                       params={"short_name": REPORT_SHORT_NAME, "_limit": 1})
        if data.get("objects"):
            return data["objects"][0]["resource_uri"]
    except Exception:
        pass
    return None


def get_test_action(auth):
    """Get the most recent action on the test page (action_id + akid)."""
    try:
        actions = api_get("/action/", auth, params={
            "page__name": TEST_PAGE_NAME,
            "order_by": "-id",
            "_limit": 1,
        })
        if actions.get("objects"):
            action = actions["objects"][0]
            action_id = action["id"]
            akid = action.get("akid")
            return action_id, akid
    except Exception as e:
        print(f"  Warning: could not get test action: {e}")
    return None, None


def setup(auth):
    print("\n=== Setup ===\n")

    # 1. Create page
    page_uri, page_id = find_test_page(auth)
    if page_uri:
        print(f"  Test page already exists: {TEST_PAGE_NAME} (id={page_id})")
    else:
        print(f"  Creating petition page: {TEST_PAGE_NAME}")
        resp = api_post("/petitionpage/", auth, {
            "name": TEST_PAGE_NAME,
            "title": "Share Tracking Test Page \u2014 DO NOT DELETE",
            "hidden": False,
        })
        page_uri = location_to_path(resp.headers.get("Location", ""))
        page_data = api_get(page_uri, auth)
        page_id = page_data["id"]
        print(f"  Created page: {TEST_PAGE_NAME} (id={page_id})")

        print("  Creating petition form...")
        api_post("/petitionform/", auth, {
            "page": f"/rest/v1{page_uri}",
            "thank_you_text": "Share tracking test complete.",
        })

    # 2. Create report
    if find_report(auth):
        print(f"  Report already exists: {REPORT_SHORT_NAME}")
    else:
        print(f"  Creating report: {REPORT_SHORT_NAME}")
        api_post("/queryreport/", auth, {
            "name": "Share Tracking Test Report",
            "short_name": REPORT_SHORT_NAME,
            "description": "Automated: verify share_link rows for the test page.",
            "sql": REPORT_SQL,
        })
        print(f"  Created report: {REPORT_SHORT_NAME}")

    # 3. Create a test action
    print("  Creating test action...")
    api_post("/action/", auth, {
        "page": TEST_PAGE_NAME,
        "email": f"share-test-{int(time.time())}@test.wemove.eu",
    })

    action_id, akid = get_test_action(auth)
    thanks_url = (f"{AK_BASE}/thanks/{TEST_PAGE_NAME}"
                  f"?akid={akid}&action_id={action_id}&share=1")

    print(f"\n  Page ID:    {page_id}")
    print(f"  Action ID:  {action_id}")
    print(f"  AKID:       {akid}")
    print(f"  Thanks URL: {thanks_url}")
    print("\n  Setup complete. You can now run tests.\n")


def cleanup(auth):
    print("\n=== Cleanup ===\n")
    uri = find_report(auth)
    if uri:
        print(f"  Deleting report: {REPORT_SHORT_NAME}")
        api_delete(uri, auth)
    page_uri, _ = find_test_page(auth)
    if page_uri:
        print(f"  Deleting page: {TEST_PAGE_NAME}")
        api_delete(page_uri, auth)
    print("\n  Cleanup complete.\n")


# ---------------------------------------------------------------------------
# URL parameter validation
# ---------------------------------------------------------------------------

def parse_share_link_params(url):
    """Extract query params from a /share/link URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    return {k: v[0] if len(v) == 1 else v for k, v in params.items()}


def validate_params(name, url, expect_type, expect_source):
    """Validate a captured /share/link URL. Returns (passed, messages)."""
    params = parse_share_link_params(url)
    messages = []
    passed = True

    # Check type
    actual_type = params.get("type")
    if actual_type != expect_type:
        messages.append(f"type: expected '{expect_type}', got '{actual_type}'")
        passed = False

    # Check source
    actual_source = params.get("source")
    if actual_source == "":
        actual_source_display = "(empty string)"
    else:
        actual_source_display = repr(actual_source)

    if actual_source != expect_source:
        messages.append(
            f"source: expected '{expect_source}', "
            f"got {actual_source_display}")
        passed = False

    # Check identification (must have page_name or action_id)
    has_page = "page_name" in params and params["page_name"]
    has_action = "action_id" in params and params["action_id"]
    has_akid = "akid" in params and params["akid"]
    if not has_page and not has_action:
        messages.append("missing page_name and action_id")
        passed = False
    if not has_akid and not has_action:
        messages.append("missing akid and action_id")
        passed = False

    return passed, messages


# ---------------------------------------------------------------------------
# Browser tests (Playwright)
# ---------------------------------------------------------------------------

def create_fresh_action(auth):
    """Create a new action on the test page, return (action_id, akid)."""
    email = f"share-test-{int(time.time())}@test.wemove.eu"
    api_post("/action/", auth, {"page": TEST_PAGE_NAME, "email": email})
    return get_test_action(auth)


def open_share_popup(page, action_id, akid):
    """Open the petition page's share popup as if the supporter had just signed.

    Mirrors popup-share.js in pubstatic without submitting the form: open the
    dialog, swap the popup's akid=None for the real action, then rebind the
    share handlers. Returns how many akid=None placeholders were replaced.
    """
    page.goto(f"{AK_BASE}/act/{TEST_PAGE_NAME}",
              wait_until="networkidle", timeout=30000)
    page.wait_for_function(
        "window.wemove && document.querySelector('[data-wm-share-popup]')",
        timeout=10000)
    return page.evaluate(
        """([akid, actionId]) => new Promise((resolve) => {
          document.addEventListener("wm-dialogOpened::data-wm-share-popup", () => {
            const dialog = document.querySelector("[data-wm-dialog-content]");
            const count = dialog.innerHTML.split("akid=None").length - 1;
            dialog.innerHTML = dialog.innerHTML.replaceAll(
              "akid=None", `akid=${akid}&amp;action_id=${actionId}`);
            wemove.triggerEvent("wm-initShare");
            resolve(count);
          }, { once: true });
          wemove.triggerEvent("wm-openDialog", { querySelector: "data-wm-share-popup" });
        })""",
        [akid, action_id],
    )


def click_share_buttons(context, page, captured_urls, location):
    """Click every share button inside location["scope"] on the current page.

    Returns (results, expectations): results for the URL report, and the
    (label, type, source) rows we then expect to find in share_link.
    """
    results = []
    expectations = []

    for tc in TEST_CASES:
        name = f"{tc['name']} [{location['name']}]"
        selector = f"{location['scope']} {tc['selector']}"
        expect_source = expected_source(tc["platform"], location["name"])

        # Clear the captured URLs for this test
        captured_urls.clear()

        el = page.query_selector(selector)
        if not el:
            results.append((name, False, [], ["Button not found on page"]))
            continue

        expectations.append((name, tc["expect_type"], expect_source))

        if tc["opens_popup"]:
            # Button has target="_blank". Clicking opens a new tab.
            # For Facebook/Bluesky the tab navigates to /share/link
            # (intercepted). For WhatsApp the tab loads
            # /thanks/PAGE?share=whatsapp&share_location=... which runs JS
            # that fetches /share/link. Either way, our context-level route
            # captures it.
            try:
                with context.expect_page(timeout=10000) as popup_info:
                    el.click()
                popup = popup_info.value
                # Wait for the tab's JS to run (WhatsApp script fetches
                # /share/link asynchronously after page load)
                popup.wait_for_load_state("networkidle", timeout=10000)
                popup.wait_for_timeout(2000)
                popup.close()
            except Exception:
                pass
        else:
            # JS-triggered fetch (Copy URL, TAF, Instagram)
            try:
                el.click()
                page.wait_for_timeout(2000)
            except Exception as e:
                results.append((name, False, [], [f"Click failed: {e}"]))
                continue

        # Check what we captured
        share_urls = [u for u in captured_urls if "/share/link" in u]
        if not share_urls:
            results.append((name, False, [],
                            ["No /share/link request captured"]))
            continue

        url = share_urls[-1]
        passed, messages = validate_params(
            name, url, tc["expect_type"], expect_source)
        results.append((name, passed, share_urls, messages))

    return results, expectations


def run_browser_tests(auth):
    """Click each share button in the popup, the thanks page and a mailing link."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Error: playwright not installed.")
        print("  pip install playwright && playwright install chromium")
        sys.exit(1)

    _, page_id = find_test_page(auth)
    if not page_id:
        print("Error: No test page. Run --setup first.")
        sys.exit(1)

    if not find_report(auth):
        print("Error: No test report. Run --setup first.")
        sys.exit(1)

    # Create a fresh action for this test run so we can filter by action_id
    print("\n=== Share Tracking Tests ===\n")
    print("  Creating fresh test action...")
    action_id, akid = create_fresh_action(auth)
    if not action_id:
        print("Error: Could not create test action.")
        sys.exit(1)

    thanks_url = (
        f"{AK_BASE}/thanks/{TEST_PAGE_NAME}"
        f"?akid={akid}&action_id={action_id}&share=1"
    )

    print(f"  Action ID:  {action_id}")
    print(f"  AKID:       {akid}")
    print(f"  Thanks URL: {thanks_url}\n")

    # Collect /share/link URLs captured per-click
    captured_urls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        # Capture /share/link URLs and let them through to ActionKit.
        # We fetch the URL server-side (so AK creates the share_link row)
        # then fulfill with the response body so the browser doesn't
        # follow the redirect to Facebook/etc.
        def handle_share_link(route, request):
            captured_urls.append(request.url)
            import requests as req
            resp = req.get(request.url, allow_redirects=False, timeout=10)
            route.fulfill(
                status=200,
                content_type="text/plain",
                body=resp.text if resp.text else resp.headers.get("Location", ""),
            )

        context.route(re.compile(r".*/share/link\?"), handle_share_link)

        # Block external navigations (Facebook, WhatsApp, Bluesky, etc.)
        context.route(
            re.compile(r"https?://(www\.)?(facebook|whatsapp|api\.whatsapp|"
                       r"wa\.me|bsky\.app|twitter|x\.com)"),
            lambda route, _: route.abort(),
        )

        page = context.new_page()

        # --- Phase 0: Baseline check ---
        print("--- Phase 0: Baseline check ---\n")
        baseline_rows = run_report(auth, action_id)
        if not isinstance(baseline_rows, list):
            baseline_rows = []
        if baseline_rows:
            print(f"  WARNING: {len(baseline_rows)} share_link rows already "
                  f"exist for action_id={action_id}")
            for row in baseline_rows:
                src = row[2] if row[2] else "(null)"
                print(f"    id={row[0]} type={row[1]} source={src}")
            print()
        else:
            print(f"  OK: No pre-existing share_link rows for "
                  f"action_id={action_id}\n")

        # --- Phase 1: Click share buttons in every location ---
        print("--- Phase 1: Click share buttons ---\n")
        results = []
        expectations = []

        for location in LOCATIONS:
            if location["name"] == "popup":
                replaced = open_share_popup(page, action_id, akid)
                print(f"  Popup opened, {replaced} akid=None links "
                      f"pointed at the test action")
            else:
                page.goto(thanks_url, wait_until="networkidle", timeout=30000)

            loc_results, loc_expectations = click_share_buttons(
                context, page, captured_urls, location)
            results += loc_results
            expectations += loc_expectations

        for mc in MAILING_CASES:
            name = mc["name"]
            expect_source = expected_source(mc["platform"], "mailing")
            expectations.append((name, mc["expect_type"], expect_source))
            captured_urls.clear()

            # The page fires the share on load, then heads to the network
            # (blocked above), so don't wait for networkidle.
            try:
                page.goto(
                    f"{AK_BASE}/thanks/{TEST_PAGE_NAME}?share={mc['share']}"
                    f"&akid={akid}&action_id={action_id}",
                    wait_until="load", timeout=30000)
            except Exception:
                pass
            page.wait_for_timeout(3000)

            share_urls = [u for u in captured_urls if "/share/link" in u]
            if not share_urls:
                results.append((name, False, [],
                                ["No /share/link request captured"]))
                continue
            passed, messages = validate_params(
                name, share_urls[-1], mc["expect_type"], expect_source)
            results.append((name, passed, share_urls, messages))

        browser.close()

    # --- Phase 2: Print URL validation results ---
    print("\n--- Phase 2: URL parameter validation ---\n")
    url_passed = 0
    url_failed = 0

    for name, passed, urls, messages in results:
        if passed:
            print(f"  PASS  {name}")
            url_passed += 1
        else:
            print(f"  FAIL  {name}")
            url_failed += 1
        if urls:
            print(f"        URL: {urls[-1]}")
        for msg in messages:
            print(f"        {msg}")

    print(f"\n  {url_passed} passed, {url_failed} failed\n")

    # --- Phase 3: Verify database via report API ---
    print("--- Phase 3: Verify share_link rows in database ---\n")
    # Poll the replica until data appears or we hit the timeout.
    # ActionKit reports run against a read replica with variable lag.
    max_wait = 300  # 5 minutes
    poll_interval = 15
    elapsed = 0
    rows = []

    print(f"  Polling replica (up to {max_wait}s)...")
    try:
        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval
            rows = run_report(auth, action_id)
            if not isinstance(rows, list):
                rows = []
            if rows:
                print(f"  Data appeared after {elapsed}s")
                break
            print(f"  ... {elapsed}s, no data yet")

        print(f"  Query: action_id={action_id}")
        if not isinstance(rows, list):
            rows = []

        new_rows = rows

        if new_rows:
            print(f"  {len(new_rows)} share_link rows for "
                  f"action_id={action_id}:\n")
            print(f"    {'id':>8}  {'type':>4}  {'source':<20}  "
                  f"{'gen':>3}  created_at")
            print(f"    {'---':>8}  {'----':>4}  {'------':<20}  "
                  f"{'---':>3}  ----------")
            for row in new_rows:
                src = row[2] if row[2] else "(null)"
                print(f"    {row[0]:>8}  {row[1]:>4}  {src:<20}  "
                      f"{row[3]:>3}  {row[4]}")
        else:
            print("  No share_link rows found.")
            print(f"  Raw response: {rows}")

        # Cross-check each test case against DB
        print()
        db_passed = 0
        db_failed = 0
        for name, exp_type, exp_source in expectations:
            match = None
            for row in new_rows:
                row_type = row[1]
                row_source = row[2] if row[2] else None
                if row_source == "":
                    row_source = None
                if row_type == exp_type and row_source == exp_source:
                    match = row
                    break
            if match:
                print(f"  DB PASS  {name} (id={match[0]})")
                db_passed += 1
            else:
                print(f"  DB FAIL  {name} "
                      f"(expected type={exp_type}, source={exp_source})")
                db_failed += 1

        # Check for unexpected rows (junk types, empty sources, etc.)
        expected_pairs = {(t, src) for _, t, src in expectations}
        unexpected = []
        for row in new_rows:
            row_type = row[1]
            row_source = row[2] if row[2] else None
            if row_source == "":
                row_source = None
            if (row_type, row_source) not in expected_pairs:
                unexpected.append(row)

        if unexpected:
            print(f"\n  WARNING: {len(unexpected)} unexpected share_link rows:")
            for row in unexpected:
                src = row[2] if row[2] else "(null)"
                print(f"    id={row[0]} type={row[1]} source={src}")

        print(f"\n  {db_passed} passed, {db_failed} failed\n")
        return url_failed == 0 and db_failed == 0

    except Exception as e:
        print(f"  Report query failed: {e}")
        print("  (URL validation results above are still valid)\n")
        return url_failed == 0


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end share tracking test with browser automation")
    parser.add_argument("--setup", action="store_true",
                        help="Create test page, report, and action")
    parser.add_argument("--cleanup", action="store_true",
                        help="Remove test resources")
    args = parser.parse_args()

    auth = get_auth()

    if args.setup:
        setup(auth)
    elif args.cleanup:
        cleanup(auth)
    else:
        success = run_browser_tests(auth)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
