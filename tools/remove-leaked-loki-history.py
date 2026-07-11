#!/usr/bin/env python3
"""Find and delete already-ingested secrets from Loki's claude-code stream.

Loki can't modify a stored entry: chunks are immutable (no edit-in-place), and
re-inserting a cleaned copy at the original timestamp is rejected as
`too_far_behind` (out-of-order window ~max_chunk_age). So the only lever on
historical secrets is to DELETE the whole matching entry (prompt/command and
all). Going-forward redaction happens at the collector, before ingest.

Workflow:
  --export PATH      read-only: dump every match to CSV for true/false-positive
                     review (one row per matched secret). The file contains real
                     secrets — handle accordingly.
  --delete-one TS    delete a single secret-bearing entry by ns timestamp (test).
  --delete-all       delete every secret-bearing entry (the ~real-leak set).

delete-* require --yes and queue Loki delete requests (processed after the grace
window; cancel within it via DELETE /loki/api/v1/delete?request_id=<id>).

Only `service_name` and `user_email` are indexed stream labels here; the secret
content lives in structured metadata (prompt, tool_input, tool_parameters), which
the secret filter matches. Run on/near the box (point --loki-url at the loki
container IP) or over an SSM tunnel (default http://localhost:3100).

Reminder: a *live* credential must be ROTATED — deleting the log copy is not
enough; anyone who already read Loki still has it.
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

# Same secret set as the collector's redaction processor (otel-collector-config.yaml).
PATTERNS = [
    r"(?i)(password|passwd|secret|webhook[_-]?secret|client[_-]?secret|private[_-]?token|auth[_-]?token|token|api[_-]?key|access[_-]?key|credentials?)\s*[:=]\s*['\x22]?[A-Za-z0-9+/_\-]{20,}={0,2}",
    r"(?i)(bearer|token)\s+[A-Za-z0-9._\-/+=]{16,}",
    r"AKIA[0-9A-Z]{16}",
    r"sk-[A-Za-z0-9_\-]{20,}",
    # GitLab: only real token prefixes (glpat-, gloas-, …), not any gl??- — the
    # loose form matched names in paths like /Users/dindagladis/…/gladis-…
    r"gl(pat|oas|rt|cbt|dt|soat|imt|agent|ptt)-[A-Za-z0-9_\-]{20,}",
    r"gh[posu]_[A-Za-z0-9]{36,}",
    r"github_pat_[A-Za-z0-9_]{40,}",
    r"1000\.[A-Za-z0-9]{20,}\.[A-Za-z0-9]{20,}",
    r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+",
    r"[A-Za-z0-9+/]{86}==",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
]
COMPILED = [re.compile(p) for p in PATTERNS]

LABELS = ("service_name", "user_email")  # the only indexed labels
CONTENT_FIELDS = ("prompt", "tool_input", "tool_parameters")
# The delete/read filter regex; anchored matchers need .* wrapping (added at use).
FILTER_RX = "|".join(p.replace(r"\.", "[.]").replace("(?i)", "") for p in PATTERNS)


def matches(text):
    return [m.group(0) for rx in COMPILED for m in rx.finditer(text or "")]


# --- Loki HTTP helpers ---------------------------------------------------------
def _req(url, data=None, method="GET", tenant="fake"):
    headers = {"X-Scope-OrgID": tenant}
    if data is not None:
        data = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(r, timeout=120) as resp:
        return resp.status, resp.read().decode()


def query_range(base, field, days, limit):
    q = f'{{service_name="claude-code"}} | {field}=~`.*({FILTER_RX}).*`'
    now = int(time.time())
    params = urllib.parse.urlencode(
        {
            "query": q,
            "start": (now - days * 86400) * 1_000_000_000,
            "end": now * 1_000_000_000,
            "limit": limit,
        }
    )
    _, body = _req(f"{base}/loki/api/v1/query_range?{params}")
    return json.loads(body)["data"]["result"]


def parse_entry(stream_result):
    """Split a Loki streams result into a normalized entry dict."""
    sm = dict(stream_result["stream"])
    ts, line = stream_result["values"][0][0], stream_result["values"][0][1]
    if len(stream_result["values"][0]) > 2:  # metadata in the value slot
        sm.update(stream_result["values"][0][2])
    return {
        "ts": ts,
        "line": line,
        "labels": {k: sm[k] for k in LABELS if k in sm},
        "meta": {k: v for k, v in sm.items() if k not in LABELS},
    }


def delete(base, field, start_s, end_s, tenant, user=None):
    scope = f',user_email="{user}"' if user else ""
    sel = f'{{service_name="claude-code"{scope}}}'
    q = f"{sel} | {field}=~`.*({FILTER_RX}).*`"
    params = urllib.parse.urlencode({"query": q, "start": start_s, "end": end_s})
    status, body = _req(f"{base}/loki/api/v1/delete?{params}", method="POST", tenant=tenant)
    if status != 204:
        raise RuntimeError(f"delete failed {status}: {body}")


# --- modes ---------------------------------------------------------------------
def do_export(base, fields, days, limit, path):
    """Read-only: write every match to a CSV for manual review — one row per
    matched secret (field, user, ts, the secret, context). Contains real secrets."""
    import csv

    rows = 0
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["field", "user_email", "ts", "secret", "context"])
        for field in fields:
            for r in query_range(base, field, days, limit):
                e = parse_entry(r)
                val = e["meta"].get(field, "")
                for rx in COMPILED:
                    for m in rx.finditer(val):
                        ctx = val[max(0, m.start() - 30) : m.end() + 30].replace("\n", " ")
                        w.writerow(
                            [field, e["labels"].get("user_email", "?"), e["ts"], m.group(0), ctx]
                        )
                        rows += 1
    print(f"exported {rows} matches to {path}")


def do_delete_one(base, fields, ts, days, limit, tenant):
    """Delete a single secret-bearing entry by ts (tight window + user scope)."""
    for field in fields:
        for r in query_range(base, field, days, limit):
            e = parse_entry(r)
            if e["ts"] != ts:
                continue
            user = e["labels"].get("user_email")
            s = int(int(ts) // 1_000_000_000)
            delete(base, field, s, s + 1, tenant, user=user)
            print(f"  delete queued: ts={ts} user={user} field={field}.")
            return
    print(f"ts {ts} not found in {fields}.", file=sys.stderr)
    sys.exit(1)


def do_delete_all(base, fields, days, tenant):
    """Delete every secret-bearing entry. Removes the whole matching entry (Loki
    can't strip just the secret). Queued; cancel within the grace window via
    DELETE /loki/api/v1/delete?request_id=<id>."""
    now = int(time.time())
    for field in fields:
        n = len(query_range(base, field, days, 5000))
        print(f"  {field}: ~{n} matching entries → queuing delete")
        delete(base, field, now - days * 86400, now, tenant)
        print(f"    delete request queued (secret-filtered, last {days}d).")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--loki-url", default="http://localhost:3100")
    ap.add_argument("--tenant", default="fake")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--limit", type=int, default=5000)
    ap.add_argument("--field", default="all", choices=["all", *CONTENT_FIELDS])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--export", metavar="PATH", help="dump matches to CSV (read-only)")
    g.add_argument("--delete-one", metavar="TS", help="delete one entry by ts")
    g.add_argument("--delete-all", action="store_true", help="delete all matches")
    ap.add_argument("--yes", action="store_true", help="confirm deletes")
    a = ap.parse_args()

    base = a.loki_url.rstrip("/")
    fields = list(CONTENT_FIELDS) if a.field == "all" else [a.field]

    if a.export:
        do_export(base, fields, a.days, a.limit, a.export)
    elif not a.yes:
        print("refusing to delete without --yes", file=sys.stderr)
        sys.exit(2)
    elif a.delete_one:
        do_delete_one(base, fields, a.delete_one, a.days, a.limit, a.tenant)
    else:
        do_delete_all(base, fields, a.days, a.tenant)


if __name__ == "__main__":
    main()
