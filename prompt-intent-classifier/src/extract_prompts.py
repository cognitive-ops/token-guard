#!/usr/bin/env python3
"""Extract all user_prompt events from Loki into a JSONL corpus.

Real Claude Code telemetry stores prompt text + identity as Loki *structured
metadata* (stream labels), with the log-line body just "claude_code.user_prompt".
We paginate forward through the retention window and keep the fields we need for
classification and for reconstructing sessions (sequence-level tags).

Output: data/prompts_raw.jsonl  (one event per line)
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests

LOKI_URL = os.environ.get("LOKI_URL", "http://localhost:3100")
QUERY = os.environ.get("LOKI_QUERY", '{service_name="claude-code"} | event_name=`user_prompt`')
# Loki rejects ranges > 30d1h; stay just under.
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "29"))
PAGE_LIMIT = int(os.environ.get("PAGE_LIMIT", "5000"))
OUT = os.environ.get("OUT", "data/prompts_raw.jsonl")

KEEP = [
    "prompt",
    "prompt_id",
    "prompt_length",
    "user_email",
    "user_account_id",
    "session_id",
    "event_sequence",
    "event_timestamp",
    "os_type",
    "service_name",
    "service_version",
]


def main():
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)
    next_start = int(start.timestamp() * 1e9)
    end_ns = int(end.timestamp() * 1e9)
    session = requests.Session()

    seen = set()
    n = 0
    with open(OUT, "w") as f:
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
                timeout=60,
            )
            r.raise_for_status()
            result = r.json().get("data", {}).get("result", [])
            page_n = 0
            max_ts = next_start
            for stream in result:
                labels = stream.get("stream", {})
                for ts, _line in stream.get("values", []):
                    page_n += 1
                    ts = int(ts)
                    if ts > max_ts:
                        max_ts = ts
                    pid = (
                        labels.get("prompt_id")
                        or f"{labels.get('session_id')}:{labels.get('event_sequence')}:{ts}"
                    )
                    if pid in seen:
                        continue
                    seen.add(pid)
                    rec = {k: labels.get(k) for k in KEEP}
                    rec["ts_ns"] = ts
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n += 1
            if page_n < PAGE_LIMIT or max_ts <= next_start:
                break
            next_start = max_ts + 1
            time.sleep(0.05)
    print(f"wrote {n} unique prompts -> {OUT}")


if __name__ == "__main__":
    main()
