#!/usr/bin/env python3
"""Extract ALL retained user_prompt events from Loki, with ALL metadata.

Differs from extract_prompts.py in two ways:
  1. Full history: walks backward in sub-30-day windows (Loki rejects a single
     range > 30d1h) until a window comes back empty or MAX_LOOKBACK_DAYS is hit,
     so we capture everything Loki still retains (~90d), not just the last 29d.
  2. All metadata: keeps every stream label / structured-metadata field on each
     event (plus any per-entry structured metadata), not a fixed KEEP subset.

Output: data/prompts_raw.jsonl  (one event per line, deduped on prompt_id)
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests

LOKI_URL = os.environ.get("LOKI_URL", "http://localhost:3100")
QUERY = os.environ.get("LOKI_QUERY", '{service_name="claude-code"} | event_name=`user_prompt`')
WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "29"))  # < 30d1h per-query cap
MAX_LOOKBACK_DAYS = int(os.environ.get("MAX_LOOKBACK_DAYS", "400"))  # safety bound
PAGE_LIMIT = int(os.environ.get("PAGE_LIMIT", "5000"))
OUT = os.environ.get("OUT", "data/raw/loki_prompts.jsonl")


def fetch_window(session, start_ns, end_ns, seen, f):
    """Forward-paginate one <30d window; write new events; return count written."""
    next_start = start_ns
    written = 0
    while True:
        r = session.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={
                "query": QUERY,
                "start": str(next_start),
                "end": str(end_ns),
                "limit": str(PAGE_LIMIT),
                "direction": "forward",
            },
            timeout=120,
        )
        r.raise_for_status()
        result = r.json().get("data", {}).get("result", [])
        page_n = 0
        max_ts = next_start
        for stream in result:
            labels = stream.get("stream", {})
            for entry in stream.get("values", []):
                page_n += 1
                ts = int(entry[0])
                if ts > max_ts:
                    max_ts = ts
                # entry may be [ts, line] or [ts, line, {structured_metadata}]
                meta = entry[2] if len(entry) > 2 and isinstance(entry[2], dict) else {}
                pid = (
                    labels.get("prompt_id")
                    or meta.get("prompt_id")
                    or f"{labels.get('session_id')}:{labels.get('event_sequence')}:{ts}"
                )
                if pid in seen:
                    continue
                seen.add(pid)
                rec = dict(labels)  # all stream labels
                rec.update(meta)  # + any per-entry structured metadata
                rec["ts_ns"] = ts
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written += 1
        if page_n < PAGE_LIMIT or max_ts <= next_start:
            break
        next_start = max_ts + 1
        time.sleep(0.05)
    return written


def main():
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    session = requests.Session()
    seen = set()
    total = 0
    now = datetime.now(timezone.utc)
    w_end = now
    days_back = 0
    with open(OUT, "w") as f:
        while days_back < MAX_LOOKBACK_DAYS:
            w_start = w_end - timedelta(days=WINDOW_DAYS)
            got = fetch_window(
                session,
                int(w_start.timestamp() * 1e9),
                int(w_end.timestamp() * 1e9),
                seen,
                f,
            )
            total += got
            print(
                f"  window {w_start.date()} .. {w_end.date()}: +{got} new (total {total})",
                flush=True,
            )
            if got == 0:
                print("  empty window -> reached start of retained data")
                break
            w_end = w_start
            days_back += WINDOW_DAYS
            time.sleep(0.1)
    print(f"wrote {total} unique prompts -> {OUT}")


if __name__ == "__main__":
    main()
