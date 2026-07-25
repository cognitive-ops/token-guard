#!/usr/bin/env python3
"""Prompt-refactor exporter.

Reads claude-code-hooks/prompt_lint events (pushed by hooks/lint-prompt.sh),
pairs consecutive same-session prompts that improved enough to count as a
"rephrase", and exposes per-developer score/savings gauges to Prometheus.

Hook-pushed events only carry {service_name, event} as Loki STREAM labels
(see hooks/lib.sh push_event()) — everything else (session_id, scores,
user_email) lives in the JSON-encoded LOG LINE body, unlike OTEL-sourced
`claude-code` events where attributes are promoted to labels by the collector.
So this exporter parses the line itself (json.loads), not stream labels.

$ saved is deliberately NOT computed here: this process only talks to Loki
and has no access to the org's blended cost-per-token (that needs the live
Anthropic Admin API, only reachable from the Next.js app). This exporter
emits a token-count delta only; the Next.js data layer converts that to a
dollar estimate using its own blendedPerMtok helper.
"""
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests
from prometheus_client import Gauge, start_http_server

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("prompt-refactor-exporter")

LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "3600"))
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "29"))  # Loki rejects ranges > 30d1h
PAGE_LIMIT = int(os.environ.get("PAGE_LIMIT", "5000"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9109"))
QUERY_TIMEOUT = int(os.environ.get("QUERY_TIMEOUT_SECONDS", "290"))

# Max gap between two same-session prompts to treat the second as a rephrase
# of the first, rather than an unrelated later prompt.
REPHRASE_WINDOW_SECONDS = int(os.environ.get("REPHRASE_WINDOW_SECONDS", "300"))
# Minimum overall-score delta (0-100 scale) to count as "meaningfully better" —
# filters out noise-level rewordings.
MIN_IMPROVEMENT = float(os.environ.get("MIN_IMPROVEMENT", "10"))
# Rough Claude streaming-throughput estimate used only to turn a token delta
# into a latency-saved estimate. NOT measured — this stack emits no latency
# metric at all; this is a labeled-as-such approximation, tune to taste.
TOKENS_PER_SECOND = float(os.environ.get("TOKENS_PER_SECOND", "60"))
# chars-per-token approximation (no tokenizer dependency in this exporter).
CHARS_PER_TOKEN = float(os.environ.get("CHARS_PER_TOKEN", "4"))

LOKI_QUERY = os.environ.get(
    "LOKI_QUERY", '{service_name="claude-code-hooks", event="prompt_lint"}'
)

AXES = ("clarity", "specificity", "context_efficiency", "overall")

SCORE = Gauge(
    "claude_prompt_refactor_score",
    "Average prompt-lint score by axis and developer (0-100)",
    ["axis", "user_email"],
)
PAIRS = Gauge(
    "claude_prompt_refactor_pairs_total",
    "Same-session rephrase pairs detected (score improved >= MIN_IMPROVEMENT within REPHRASE_WINDOW_SECONDS)",
    ["user_email"],
)
TOKENS_SAVED = Gauge(
    "claude_prompt_refactor_tokens_saved",
    "Estimated tokens saved from rephrasing (char-count delta / CHARS_PER_TOKEN); not a real token count",
    ["user_email"],
)
SAVED_SECONDS = Gauge(
    "claude_prompt_refactor_saved_seconds",
    "Estimated latency saved (s) from rephrasing, derived from TOKENS_PER_SECOND; not measured",
    ["user_email"],
)
LAST_SUCCESS = Gauge(
    "claude_prompt_refactor_exporter_last_success_timestamp", "Unix ts of last good poll"
)
SCRAPE_ERRORS = Gauge("claude_prompt_refactor_exporter_errors", "1 if last poll failed, else 0")


def loki_prompt_lints(session, start_ns, end_ns):
    """Yield (ts_ns, body_dict) for every prompt_lint event in the window (paginated).

    Hook-pushed events carry no useful stream labels — every field we need
    (session_id, user_email, scores, counts) is inside the JSON log line, so
    each line is parsed individually.
    """
    nxt = start_ns
    while True:
        r = session.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={
                "query": LOKI_QUERY,
                "start": str(nxt),
                "end": str(end_ns),
                "limit": str(PAGE_LIMIT),
                "direction": "forward",
            },
            timeout=(10, QUERY_TIMEOUT),
        )
        r.raise_for_status()
        result = r.json().get("data", {}).get("result", [])
        page_n, max_ts = 0, nxt
        for stream in result:
            for ts, line in stream.get("values", []):
                page_n += 1
                ts = int(ts)
                if ts > max_ts:
                    max_ts = ts
                try:
                    body = json.loads(line)
                except (ValueError, TypeError):
                    continue
                yield ts, body
        if page_n < PAGE_LIMIT or max_ts <= nxt:
            break
        nxt = max_ts + 1


def poll_once(session):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)
    end_ns, start_ns = int(end.timestamp() * 1e9), int(start.timestamp() * 1e9)

    by_sess = defaultdict(list)
    n_events = 0
    for ts, body in loki_prompt_lints(session, start_ns, end_ns):
        sid = body.get("session_id")
        if not sid:
            continue
        by_sess[sid].append((ts, body))
        n_events += 1

    # axis -> email -> [sum, n]
    score_sum = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))
    pairs_count = defaultdict(int)
    tokens_saved = defaultdict(float)
    seconds_saved = defaultdict(float)

    for evs in by_sess.values():
        evs.sort(key=lambda e: e[0])
        prev = None
        for ts, body in evs:
            email = body.get("user_email") or "unknown"
            for axis in AXES:
                try:
                    v = float(body.get(axis, 0))
                except (TypeError, ValueError):
                    continue
                bucket = score_sum[axis][email]
                bucket[0] += v
                bucket[1] += 1

            if prev is not None:
                prev_ts, prev_body = prev
                gap_s = (ts - prev_ts) / 1e9
                try:
                    delta = float(body.get("overall", 0)) - float(prev_body.get("overall", 0))
                except (TypeError, ValueError):
                    delta = 0
                if 0 < gap_s <= REPHRASE_WINDOW_SECONDS and delta >= MIN_IMPROVEMENT:
                    before_chars = float(prev_body.get("char_count", 0) or 0)
                    after_chars = float(body.get("char_count", 0) or 0)
                    token_delta = max(before_chars - after_chars, 0) / CHARS_PER_TOKEN
                    tokens_saved[email] += token_delta
                    seconds_saved[email] += token_delta / TOKENS_PER_SECOND
                    pairs_count[email] += 1
            prev = (ts, body)

    SCORE.clear()
    for axis, byemail in score_sum.items():
        for email, (s, n) in byemail.items():
            if n:
                SCORE.labels(axis=axis, user_email=email).set(s / n)

    PAIRS.clear()
    for email, n in pairs_count.items():
        PAIRS.labels(user_email=email).set(n)

    TOKENS_SAVED.clear()
    for email, v in tokens_saved.items():
        TOKENS_SAVED.labels(user_email=email).set(v)

    SAVED_SECONDS.clear()
    for email, v in seconds_saved.items():
        SAVED_SECONDS.labels(user_email=email).set(v)

    return n_events, len(by_sess), sum(pairs_count.values())


def poll():
    try:
        log.info(f"Polling Loki for {LOOKBACK_DAYS}d of prompt_lint events...")
        session = requests.Session()
        n_events, n_sessions, n_pairs = poll_once(session)
        LAST_SUCCESS.set_to_current_time()
        SCRAPE_ERRORS.set(0)
        log.info(
            f"Poll successful: {n_events} events, {n_sessions} sessions, {n_pairs} rephrase pairs"
        )
    except Exception as e:
        log.error(f"Poll failed: {e}")
        SCRAPE_ERRORS.set(1)


def main():
    start_http_server(LISTEN_PORT)
    log.info(f"Listening on port {LISTEN_PORT}")
    poll()
    while True:
        time.sleep(POLL_INTERVAL)
        poll()


if __name__ == "__main__":
    main()
