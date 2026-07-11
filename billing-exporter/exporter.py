#!/usr/bin/env python3
"""Claude Code real-cost exporter.

Bridges the gap between OTEL telemetry (which only reports an *estimated*
API-equivalent cost) and the *real* money spent on Claude Code.

Real cost has two non-overlapping buckets, sourced separately:

  1. Seat developers (Team plan, OAuth login)
       real cost = flat seat fee  +  metered overage
     - seat fee   : from seat-roster.yaml (email -> seat type -> $/month). Flat.
     - overage    : metered usage that spills past the seat allowance. Today $0;
                    detected/attributed via the Usage Report API where it shows
                    up as a non-null `account_id` (per-user). Priced at list rates.

  2. Service / automation API keys
       real cost = metered billing from the Cost Report API, but ONLY for the
       Claude-Code workspace(s) listed in roster `service_workspace_ids`. The Cost
       Report covers the org's ENTIRE Anthropic bill (every workspace / product),
       so it MUST be scoped to Claude Code — never summed whole.

Seat usage is NOT metered and never appears in the Cost Report. The two buckets do
not overlap, so summing the (scoped) service cost with seat fees is safe.

Exposes Prometheus metrics on :9105/metrics. Polls the Admin API on an interval
(billing data lags ~minutes-to-1h, so a slow poll is correct).
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
import yaml
from prometheus_client import Gauge, start_http_server

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("billing-exporter")

API_BASE = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "21600"))  # 6h
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "30"))
ROSTER_PATH = os.environ.get("ROSTER_PATH", "/config/seat-roster.yaml")
KEY_PATH = os.environ.get("ADMIN_KEY_PATH", "/secrets/admin-key")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9105"))
UNCATEGORIZED_SERVICE_BILL_FLOOR_USD = float(
    os.environ.get("UNCATEGORIZED_SERVICE_BILL_FLOOR_USD", "1")
)

# --- Prometheus metrics ------------------------------------------------------
REAL_DEV_COST = Gauge(
    "claude_dev_real_cost_usd",
    "Real monthly cost per developer = seat fee + metered overage",
    ["email", "seat_type"],
)
DEV_SEAT_FEE = Gauge(
    "claude_dev_seat_fee_usd",
    "Flat monthly seat fee per developer",
    ["email", "seat_type"],
)
DEV_EXTRA_USAGE = Gauge(
    "claude_dev_extra_usage_usd",
    "Metered overage (extra usage) attributed to a developer over the lookback window",
    ["email"],
)
SEAT_COUNT = Gauge(
    "claude_seat_count",
    "Number of provisioned seats by type",
    ["seat_type"],
)
WORKSPACE_COST = Gauge(
    "claude_workspace_billed_cost_usd",
    "Anthropic API billed cost by workspace over the lookback window (the org's WHOLE bill). "
    "counted=true means the workspace is attributed to Claude Code (listed in service_workspace_ids).",
    ["workspace_id", "workspace_name", "counted"],
)
SERVICE_COST_TOTAL = Gauge(
    "claude_service_billed_cost_total_usd",
    "Total authoritative metered billing (Cost Report API) over the lookback window",
)
UNCATEGORIZED_WORKSPACE_SPEND = Gauge(
    "claude_uncategorized_workspace_spend_usd",
    "Billed spend of a workspace that is in NEITHER service_workspace_ids NOR "
    "known_product_ids and exceeds the drift floor. Non-empty => a new/unclassified "
    "workspace needs a Claude-Code-vs-product decision (drift guard).",
    ["workspace_id", "workspace_name"],
)
UNCATEGORIZED_WORKSPACE_COUNT = Gauge(
    "claude_uncategorized_workspace_count",
    "Number of workspaces above the drift floor classified as neither Claude Code nor "
    "known product. Alert when > 0: a workspace appeared that no one has classified yet.",
)
ORG_REAL_COST_TOTAL = Gauge(
    "claude_org_real_cost_total_usd",
    "Org real cost = sum(seat fees) + sum(extra usage) + service-key billed cost",
)
UNMAPPED_OVERAGE = Gauge(
    "claude_unmapped_extra_usage_usd",
    "Metered overage carrying an account_id that is not mapped to an email in the roster",
)
LAST_SUCCESS = Gauge(
    "claude_billing_exporter_last_success_timestamp",
    "Unix timestamp of the last successful poll",
)
SCRAPE_ERRORS = Gauge(
    "claude_billing_exporter_errors",
    "1 if the last poll failed, 0 otherwise",
)


def load_key() -> str:
    key = os.environ.get("ANTHROPIC_ADMIN_KEY")
    if key:
        return key.strip()
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH) as f:
            return f.read().strip()
    log.error("No admin key: set ANTHROPIC_ADMIN_KEY or mount %s", KEY_PATH)
    sys.exit(1)


def load_roster() -> dict:
    """Roster schema:

    seat_fees:            {premium: 125, standard: 25}   # $/month, real numbers from the invoice (monthly billing)
    members:              [{email: a@x.com, seat_type: premium}, ...]
    account_map:          {user_01...: a@x.com}           # optional OVERRIDE; auto-built from the Members API
    pricing:              {model: {input: 3.0, output: 15.0, cache_read: 0.3, cache_write: 3.75}}  # $/MTok
    service_workspace_ids: [wrkspc_...]   # ONLY these workspaces count as Claude Code service cost.
                                          # The Cost Report is the org's WHOLE Anthropic bill (all
                                          # products); without this, service cost is $0 (not the whole bill).
    known_product_ids:    [wrkspc_...]    # Workspaces known to be product/client usage (NOT Claude
                                          # Code). Only used by the drift guard: a workspace in neither
                                          # list that bills over the floor is flagged as uncategorized.
    """
    if not os.path.exists(ROSTER_PATH):
        log.warning("Roster %s not found; per-developer metrics will be empty", ROSTER_PATH)
        return {}
    with open(ROSTER_PATH) as f:
        return yaml.safe_load(f) or {}


def api_get(session, path, params, key):
    r = session.get(
        f"{API_BASE}{path}",
        params=params,
        headers={"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def paged(session, path, params, key):
    """Yield every result row across pagination."""
    page = None
    while True:
        p = dict(params)
        if page:
            p["page"] = page
        data = api_get(session, path, p, key)
        for bucket in data.get("data", []):
            yield from bucket.get("results", [])
        if not data.get("has_more"):
            break
        page = data.get("next_page")
        if not page:
            break


def fetch_cost_report(session, key, start_iso, service_workspace_ids):
    """Anthropic billed cost. `amount` is in CENTS (lowest currency unit) as a decimal
    string, currency=USD — per the Admin API reference: `"123.45"` in USD = $1.23. We
    divide by 100 to expose real USD.

    The Cost Report covers the org's ENTIRE Anthropic spend across ALL workspaces — i.e.
    your products too, not just Claude Code. Claude Code seat usage isn't metered at all;
    only Claude-Code *service/automation* keys show up here. So we group by workspace and
    attribute to Claude Code ONLY the workspaces in `service_workspace_ids`. With no
    allowlist configured we attribute $0 (better than counting the whole org bill).

    Returns (by_workspace_all, counted_total)."""
    by_ws = {}
    for row in paged(
        session,
        "/v1/organizations/cost_report",
        {"starting_at": start_iso, "limit": "31", "group_by[]": ["workspace_id"]},
        key,
    ):
        ws = row.get("workspace_id") or "(none)"
        # `amount` is cents → real USD.
        by_ws[ws] = by_ws.get(ws, 0.0) + float(row.get("amount", 0) or 0) / 100.0
    counted_total = sum(v for ws, v in by_ws.items() if ws in service_workspace_ids)
    return by_ws, counted_total


def fetch_workspace_names(session, key):
    """Map workspace_id -> human name (Admin API), so metrics/dashboards can show
    'Gitea PR Reviews' instead of 'wrkspc_01DQU7...'. include_archived covers service
    workspaces that may be archived. Best-effort: on failure the id is used as-is."""
    names = {}
    try:
        data = api_get(
            session,
            "/v1/organizations/workspaces",
            {"limit": 100, "include_archived": "true"},
            key,
        )
        for w in data.get("data", []):
            names[w["id"]] = w.get("name") or w["id"]
    except Exception as e:  # noqa: BLE001 - names are cosmetic; never fail the poll
        log.warning("could not fetch workspace names: %s", e)
    return names


def fetch_account_map(session, key):
    """Map account_id (user_01...) -> email from the Members API, so metered overage
    (which the Usage Report keys by account_id, never by email) can be attributed to a
    person. Self-renewing: rebuilt every poll, so new members are covered automatically.
    Best-effort: on failure return {} and let the roster's manual account_map stand in."""
    emails = {}
    try:
        after_id = None
        while True:
            params = {"limit": 100}
            if after_id:
                params["after_id"] = after_id
            data = api_get(session, "/v1/organizations/users", params, key)
            for u in data.get("data", []):
                uid, email = u.get("id"), u.get("email")
                if uid and email:
                    emails[uid] = email
            if not data.get("has_more"):
                break
            after_id = data.get("last_id")
            if not after_id:
                break
    except Exception as e:  # noqa: BLE001 - never fail the poll over the auto-map
        log.warning("could not fetch account map from /organizations/users: %s", e)
    return emails


def fetch_overage(session, key, start_iso, pricing):
    """Detect & price per-account metered overage (seat usage that spilled to
    metered billing). Returns {account_id: usd}. Today this is expected empty;
    when seat overage occurs it carries a non-null account_id (per-user)."""
    by_account = {}
    for row in paged(
        session,
        "/v1/organizations/usage_report/messages",
        {
            "starting_at": start_iso,
            "bucket_width": "1d",
            "group_by[]": ["account_id", "model"],
            "limit": "31",
        },
        key,
    ):
        acct = row.get("account_id")
        if acct is None:
            continue  # null account_id == service API key usage, not seat overage
        model = row.get("model") or "default"
        price = pricing.get(model, pricing.get("default", {}))
        cc = row.get("cache_creation") or {}
        # coerce None->0: the API may return keys present-but-null
        usd = (
            (row.get("uncached_input_tokens") or 0) / 1e6 * price.get("input", 0)
            + (row.get("output_tokens") or 0) / 1e6 * price.get("output", 0)
            + (row.get("cache_read_input_tokens") or 0) / 1e6 * price.get("cache_read", 0)
            + (
                (cc.get("ephemeral_5m_input_tokens") or 0)
                + (cc.get("ephemeral_1h_input_tokens") or 0)
            )
            / 1e6
            * price.get("cache_write", 0)
        )
        by_account[acct] = by_account.get(acct, 0.0) + usd
    return by_account


def poll_once(session, roster):
    key = load_key()
    start_iso = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime(
        "%Y-%m-%dT00:00:00Z"
    )

    seat_fees = roster.get("seat_fees", {"premium": 125, "standard": 25})
    members = roster.get("members", [])
    # account_id (user_01...) -> email, needed because the Usage Report keys overage by
    # account_id and never by email. Auto-built from the Members API each poll (self-
    # renewing), with the roster's manual account_map layered on top as an override.
    account_map = {**fetch_account_map(session, key), **roster.get("account_map", {})}
    pricing = roster.get("pricing", {})
    # Manual extra-usage from claude.ai -> Admin -> Billing, for the lookback window.
    # Seat overage may never appear in the Usage/Cost API (subscription billing is an
    # API blind spot), so this is the authoritative fallback. {email: usd}
    manual_extra = roster.get("manual_extra_usage", {})
    # Which workspaces are Claude Code service/automation usage (vs the org's products).
    service_workspace_ids = set(roster.get("service_workspace_ids", []))
    # Workspaces known to be metered product/client usage (NOT Claude Code), deliberately
    # excluded. Kept so the drift guard can tell "already classified as product" apart from
    # "brand new, nobody has looked at it yet".
    known_product_ids = set(roster.get("known_product_ids", []))

    # 1) Service-key billed cost — scoped to Claude Code workspaces only
    by_ws, service_total = fetch_cost_report(session, key, start_iso, service_workspace_ids)
    ws_names = fetch_workspace_names(session, key)
    WORKSPACE_COST.clear()
    for ws, amt in by_ws.items():
        WORKSPACE_COST.labels(
            workspace_id=ws,
            workspace_name=ws_names.get(ws, ws),
            counted=str(ws in service_workspace_ids).lower(),
        ).set(amt)
    SERVICE_COST_TOTAL.set(service_total)
    if not service_workspace_ids:
        log.warning(
            "service_workspace_ids not set -> Claude Code service cost counted as $0 "
            "(org-wide bill is $%.2f across %d workspaces). Identify the Claude Code "
            "workspace(s) from claude_workspace_billed_cost_usd and add them to the roster.",
            sum(by_ws.values()),
            len(by_ws),
        )

    # 1b) Drift guard — flag workspaces classified as neither Claude Code nor known
    # product. New workspaces can appear at any time and can't be predicted, so this
    # check runs every poll; classifying each one is a one-time human decision (add its
    # id to service_workspace_ids or known_product_ids). Only spend above the floor
    # flags, so a few cents of noise stays quiet.
    UNCATEGORIZED_WORKSPACE_SPEND.clear()
    uncategorized = 0
    for ws, amt in by_ws.items():
        if ws == "(none)" or ws in service_workspace_ids or ws in known_product_ids:
            continue
        if amt <= UNCATEGORIZED_SERVICE_BILL_FLOOR_USD:
            continue
        UNCATEGORIZED_WORKSPACE_SPEND.labels(
            workspace_id=ws, workspace_name=ws_names.get(ws, ws)
        ).set(amt)
        uncategorized += 1
        log.warning(
            "uncategorized workspace %s (%s) billed $%.2f over lookback — classify it as "
            "Claude Code (service_workspace_ids) or product (known_product_ids)",
            ws_names.get(ws, ws),
            ws,
            amt,
        )
    UNCATEGORIZED_WORKSPACE_COUNT.set(uncategorized)

    # 2) Per-account metered overage (extra usage), priced
    overage = fetch_overage(session, key, start_iso, pricing)
    mapped_email_overage = {}
    unmapped = 0.0
    for acct, usd in overage.items():
        email = account_map.get(acct)
        if email:
            mapped_email_overage[email] = mapped_email_overage.get(email, 0.0) + usd
        else:
            unmapped += usd
    UNMAPPED_OVERAGE.set(unmapped)

    # 3) Per-developer real cost = seat fee + extra usage
    REAL_DEV_COST.clear()
    DEV_SEAT_FEE.clear()
    DEV_EXTRA_USAGE.clear()
    counts = {}
    seat_fee_sum = 0.0
    extra_sum = 0.0
    for m in members:
        email = m["email"]
        seat = m.get("seat_type", "standard")
        fee = float(seat_fees.get(seat, 0))
        # extra usage = metered overage. Prefer the API-detected value; fall back to the
        # manual claude.ai billing entry only when the API reports none (avoids double-count).
        api_over = float(mapped_email_overage.get(email, 0.0))
        extra = api_over if api_over > 0 else float(manual_extra.get(email, 0.0))
        DEV_SEAT_FEE.labels(email=email, seat_type=seat).set(fee)
        DEV_EXTRA_USAGE.labels(email=email).set(extra)
        REAL_DEV_COST.labels(email=email, seat_type=seat).set(fee + extra)
        counts[seat] = counts.get(seat, 0) + 1
        seat_fee_sum += fee
        extra_sum += extra

    SEAT_COUNT.clear()
    for seat, n in counts.items():
        SEAT_COUNT.labels(seat_type=seat).set(n)

    ORG_REAL_COST_TOTAL.set(seat_fee_sum + extra_sum + unmapped + service_total)

    log.info(
        "poll ok: %d members, seat_fees=$%.2f, extra=$%.2f (unmapped $%.2f), "
        "service=$%.2f, org_real=$%.2f",
        len(members),
        seat_fee_sum,
        extra_sum,
        unmapped,
        service_total,
        seat_fee_sum + extra_sum + unmapped + service_total,
    )


def main():
    log.info(
        "billing-exporter starting on :%d (poll every %ds, lookback %dd)",
        LISTEN_PORT,
        POLL_INTERVAL,
        LOOKBACK_DAYS,
    )
    start_http_server(LISTEN_PORT)
    session = requests.Session()
    while True:
        try:
            roster = load_roster()  # reloaded each cycle so edits take effect
            poll_once(session, roster)
            LAST_SUCCESS.set(time.time())
            SCRAPE_ERRORS.set(0)
        except Exception as e:  # noqa: BLE001 - keep the exporter alive
            SCRAPE_ERRORS.set(1)
            log.exception("poll failed: %s", e)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
