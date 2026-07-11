#!/usr/bin/env python3
"""Comprehensive Playwright test of the Token Guard-branded Grafana stack (clean browser)."""

import os

from playwright.sync_api import sync_playwright

USER = os.environ["DASHBOARD_USERNAME"]
PW = os.environ["DASHBOARD_PASSWORD"]
BASE = "http://localhost:3000"
DASH = [
    ("claude-code-working", "Token Guard AI Usage Analytics"),
    ("claude-real-cost", "Real Cost"),
    ("claude-hooks-metrics", "Engineering Metrics"),
]

results = []
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"])
    ctx = b.new_context()  # fresh = no cache (proves server-side state)
    pg = ctx.new_page()

    # ---- LOGIN PAGE ----
    pg.goto(f"{BASE}/login", wait_until="networkidle")
    pg.wait_for_timeout(1000)
    pg.screenshot(path="/tmp/t_login.png", full_page=True)
    body = pg.inner_text("body")
    logo_src = pg.get_attribute("img[src*=grafana_icon]", "src")
    logo_body = ctx.request.get(f"{BASE}/{logo_src}").text() if logo_src else ""
    print("=== LOGIN PAGE ===")
    print("  tab title         :", pg.title())
    print("  logo asset         :", logo_src)
    print("  logo is Token Guard:", "data:image/png;base64" in logo_body)
    print("  'Welcome to Token Guard':", "Welcome to Token Guard" in body)
    print("  'Grafana' visible  :", "Grafana" in body, "(footer links still link to grafana.com)")
    print("  version string     :", "shown" if "Grafana v" in body else "hidden")

    # ---- LOGIN ----
    pg.fill('input[name="user"]', USER)
    pg.fill('input[name="password"]', PW)
    pg.click('button[type="submit"]')
    try:
        pg.wait_for_url(lambda u: "/login" not in u, timeout=20000)
        logged_in = True
    except Exception:
        logged_in = False
    print("\n=== LOGIN with .env creds:", "OK" if logged_in else "FAILED", "===")

    # ---- DASHBOARDS ----
    print("\n=== DASHBOARDS (now-24h) ===")
    for uid, name in DASH:
        pg.goto(f"{BASE}/d/{uid}?from=now-24h&to=now", wait_until="networkidle")
        pg.wait_for_timeout(4500)
        pg.screenshot(path=f"/tmp/t_{uid}.png")
        nodata = pg.get_by_text("No data", exact=True).count()
        title = pg.title()
        results.append((name, uid, nodata, title))
        print(f"  {name:28} | 'No data' panels: {nodata} | tab: {title[:40]}")
    b.close()

print("\nScreenshots: /tmp/t_login.png, " + ", ".join(f"/tmp/t_{u}.png" for u, _ in DASH))
