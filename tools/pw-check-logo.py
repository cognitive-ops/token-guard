#!/usr/bin/env python3
"""Inspect Grafana's logo/branding with a clean (cache-less) browser via Playwright."""

import os

from playwright.sync_api import sync_playwright

USER = os.environ["DASHBOARD_USERNAME"]
PW = os.environ["DASHBOARD_PASSWORD"]
BASE = "http://localhost:3000"

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"])
    ctx = b.new_context()  # fresh context = no favicon/asset cache
    pg = ctx.new_page()

    # --- login page ---
    pg.goto(f"{BASE}/login", wait_until="networkidle")
    pg.screenshot(path="/tmp/grafana_login.png", full_page=True)
    print("=== LOGIN PAGE images/svgs ===")
    for el in pg.query_selector_all("img"):
        print("  img src=", el.get_attribute("src"))
    for el in pg.query_selector_all("svg"):
        cls = el.get_attribute("class") or ""
        if "brand" in cls.lower() or "logo" in cls.lower():
            print("  svg.class=", cls)
    print("  <title>=", pg.title())

    # --- log in ---
    pg.wait_for_selector('input[name="user"]')
    pg.fill('input[name="user"]', USER)
    pg.fill('input[name="password"]', PW)
    pg.click('button[type="submit"]')
    try:
        pg.wait_for_url(lambda u: "/login" not in u, timeout=20000)
    except Exception:
        pass
    pg.wait_for_timeout(1500)

    # --- a dashboard (open the Token Guard working dashboard, 24h range) ---
    pg.goto(f"{BASE}/d/claude-code-working?from=now-24h&to=now", wait_until="networkidle")
    pg.wait_for_timeout(4000)
    pg.screenshot(path="/tmp/grafana_dash.png", full_page=False)
    print("\n=== APP CHROME (nav) logo candidates ===")
    for sel in [
        'a[aria-label*="Home"] img',
        'a[href="/"] img',
        "[class*=brand] img",
        'img[src*="grafana_icon"]',
        'img[src*="brand"]',
        "header img",
        "nav img",
    ]:
        for el in pg.query_selector_all(sel):
            print(f"  {sel}: src={el.get_attribute('src')}")
    print("  dashboard tab <title>=", pg.title())
    # any inline grafana logo svg in the chrome
    n_svg = pg.eval_on_selector_all("svg", "els => els.length")
    print("  total svg elements on page:", n_svg)
    b.close()
print("screenshots: /tmp/grafana_login.png, /tmp/grafana_dash.png")
