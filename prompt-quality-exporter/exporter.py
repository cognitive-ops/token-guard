#!/usr/bin/env python3
"""Prompt-quality exporter.

Reads `user_prompt` events from Loki, scores each NEW developer prompt against
the 4-dimension best-practice rubric (clarity / specificity / structure /
robustness, see quality_rubric.py) via an LLM judge (Anthropic or OpenAI —
whichever API key is present), and exposes per-dimension / tier / issue
averages to Prometheus for the "Prompt Quality" Grafana dashboard.

Unlike prompt-intent-exporter (a free local ONNX model), scoring here costs
real money per call, so:
  - results are cached to disk (CACHE_FILE, on a mounted volume) so a container
    restart never re-scores prompts it already paid to score
  - MAX_NEW_PER_POLL caps how many brand-new prompts get scored in one poll, so
    a large backlog (e.g. first run) drains gradually instead of one cost spike
  - a running cost estimate is exposed as a gauge so spend is visible
"""

import json
import logging
import os
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import requests
from prometheus_client import Gauge, start_http_server

import quality_rubric as qr

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("prompt-quality-exporter")

LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "3600"))
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "7"))  # smaller than intent's 29d: cost control
PAGE_LIMIT = int(os.environ.get("PAGE_LIMIT", "5000"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9110"))
CACHE_FILE = os.environ.get("CACHE_FILE", "/cache/quality_cache.jsonl")
MAX_NEW_PER_POLL = int(os.environ.get("MAX_NEW_PER_POLL", "300"))  # cost guard
WORKERS = int(os.environ.get("WORKERS", "8"))
LOKI_QUERY = os.environ.get("LOKI_QUERY", '{service_name="claude-code"} | event_name=`user_prompt`')
WRITE_LOKI = os.environ.get("WRITE_LOKI", "1") == "1"
PUSH_URL = LOKI_URL.rstrip("/") + "/loki/api/v1/push"
S_QUALITY = "claude-code-quality"  # 1 entry/prompt -> {overall_score, tier, top_issue, dims, user_email}

SCORER_MODEL = os.environ.get("SCORER_MODEL", "claude-sonnet-5")
SCORER_OPENAI_MODEL = os.environ.get("SCORER_OPENAI_MODEL", "gpt-4o-mini")
SCORER_EFFORT = os.environ.get("SCORER_EFFORT", "low")
# rough live cost readout; approximate, check current provider pricing pages
PIN, POUT = 2.0 / 1e6, 10.0 / 1e6  # anthropic sonnet
OPENAI_PIN, OPENAI_POUT = 0.15 / 1e6, 0.60 / 1e6  # gpt-4o-mini

# --- metrics (claude_prompt_quality_* namespace, matching prompt-intent-exporter) ---
OVERALL_AVG = Gauge(
    "claude_prompt_quality_overall_avg",
    "Average overall quality score (0-100) over the lookback window, by developer",
    ["user_email"],
)
DIM_AVG = Gauge(
    "claude_prompt_quality_dimension_avg",
    "Average per-dimension score (1-5) over the lookback window, by developer",
    ["dimension", "user_email"],
)
TIER_COUNT = Gauge(
    "claude_prompt_quality_tier_count",
    "Prompts by quality tier over the lookback window, by developer",
    ["tier", "user_email"],
)
TOP_ISSUE_COUNT = Gauge(
    "claude_prompt_quality_top_issue_count",
    "Prompts by top limiting issue over the lookback window, by developer",
    ["top_issue", "user_email"],
)
PROC = Gauge("claude_prompt_quality_prompts_total", "Real prompts scored over the lookback window")
NEW_SCORED = Gauge(
    "claude_prompt_quality_exporter_new_scored_last_poll", "Newly LLM-scored prompts in the last poll"
)
COST_TOTAL = Gauge(
    "claude_prompt_quality_exporter_cost_usd_total",
    "Cumulative estimated USD spent scoring prompts since exporter start",
)
LAST_OK = Gauge("claude_prompt_quality_exporter_last_success_timestamp", "Unix ts of last good poll")
ERRORS = Gauge("claude_prompt_quality_exporter_errors", "1 if last poll failed, else 0")

# --- preprocessing (mirrors prompt-intent-exporter / the classifier's preprocess.py) ---
_INJECTED = (
    "<observed_from_primary_session>",
    "<task-notification>",
    "<system-reminder>",
    "<command-",
)
_CONFIRM = re.compile(
    r"^(y|yes|yep|yeah|ok|okay|sure|no|nope|continue|go|go ahead|do it|proceed|"
    r"next|stop|thanks|thank you|ty|y post|yes post|\d+)\b",
    re.I,
)


def categorize(p):
    s = (p or "").strip()
    if not s:
        return "empty"
    if s.startswith(_INJECTED):
        return "injected"
    if re.match(r"^/[a-zA-Z]", s):
        return "control"
    if len(s) < 15 and _CONFIRM.match(s):
        return "control"
    return "real"


# --- LLM scoring (Anthropic primary, OpenAI fallback — same auto-selection as
# prompt-intent-classifier/src/score_quality.py) ---
_cost_lock = threading.Lock()
_cost_usd = {"total": 0.0}


def resolve_provider():
    p = os.environ.get("SCORER_PROVIDER", "auto")
    if p in ("anthropic", "openai"):
        return p
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    raise RuntimeError("no ANTHROPIC_API_KEY or OPENAI_API_KEY set")


def get_client(provider):
    if provider == "anthropic":
        import anthropic

        return anthropic.Anthropic()
    import openai

    return openai.OpenAI()


def _score_anthropic(client, prompt):
    r = client.messages.create(
        model=SCORER_MODEL,
        max_tokens=400,
        system=qr.SYSTEM,
        messages=qr.fewshot_messages()
        + [{"role": "user", "content": qr.build_user_content(prompt)}],
        thinking={"type": "disabled"},
        output_config={"effort": SCORER_EFFORT, "format": {"type": "json_schema", "schema": qr.SCHEMA}},
    )
    with _cost_lock:
        _cost_usd["total"] += r.usage.input_tokens * PIN + r.usage.output_tokens * POUT
    return json.loads(next(b.text for b in r.content if b.type == "text"))


def _score_openai(client, prompt):
    messages = [{"role": "system", "content": qr.SYSTEM}]
    messages += qr.fewshot_messages()
    messages.append({"role": "user", "content": qr.build_user_content(prompt)})
    r = client.chat.completions.create(
        model=SCORER_OPENAI_MODEL,
        max_tokens=400,
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "quality_score", "strict": True, "schema": qr.SCHEMA},
        },
    )
    with _cost_lock:
        _cost_usd["total"] += r.usage.prompt_tokens * OPENAI_PIN + r.usage.completion_tokens * OPENAI_POUT
    return json.loads(r.choices[0].message.content)


def score(provider, client, prompt):
    return _score_anthropic(client, prompt) if provider == "anthropic" else _score_openai(client, prompt)


# --- cache (disk-persisted so restarts never re-spend on prompts already scored) ---
def load_cache(path):
    cache = {}
    if os.path.exists(path):
        for line in open(path):
            try:
                r = json.loads(line)
                cache[r["prompt_id"]] = r
            except Exception:
                pass
    log.info("loaded %d cached quality scores from %s", len(cache), path)
    return cache


def append_cache(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def loki_prompts(session, end_ns, start_ns):
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
            timeout=290,
        )
        r.raise_for_status()
        result = r.json().get("data", {}).get("result", [])
        page_n, max_ts = 0, nxt
        for stream in result:
            labels = stream.get("stream", {})
            for ts, _line in stream.get("values", []):
                page_n += 1
                ts = int(ts)
                if ts > max_ts:
                    max_ts = ts
                yield ts, labels
        if page_n < PAGE_LIMIT or max_ts <= nxt:
            break
        nxt = max_ts + 1


PUSH_CHUNK = int(os.environ.get("PUSH_CHUNK", "1000"))


def push_loki(session, values):
    if not values:
        return 0
    values = sorted(values, key=lambda v: int(v[0]))
    total = 0
    for i in range(0, len(values), PUSH_CHUNK):
        chunk = values[i : i + PUSH_CHUNK]
        r = session.post(
            PUSH_URL,
            json={"streams": [{"stream": {"service_name": S_QUALITY}, "values": chunk}]},
            timeout=60,
        )
        r.raise_for_status()
        total += len(chunk)
    return total


def poll_once(session, provider, client, cache):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)
    end_ns, start_ns = int(end.timestamp() * 1e9), int(start.timestamp() * 1e9)

    window = []  # (pid, ts, email) real prompts seen in this window
    todo = []  # (pid, ts, email, text) not yet in cache
    for ts, lb in loki_prompts(session, start_ns=start_ns, end_ns=end_ns):
        text = (lb.get("prompt") or "").strip()
        if categorize(text) != "real":
            continue
        pid = lb.get("prompt_id")
        email = lb.get("user_email") or "unknown"
        if not pid:
            continue
        window.append((pid, ts, email))
        if pid not in cache and len(todo) < MAX_NEW_PER_POLL:
            todo.append((pid, ts, email, text))

    new_streams = []

    def job(item):
        pid, ts, email, text = item
        for attempt in range(3):
            try:
                sc = score(provider, client, text)
                dims = {d: sc[d] for d in qr.DIMENSIONS}
                overall = qr.overall_score(dims)
                return {
                    "prompt_id": pid,
                    "ts": ts,
                    "user_email": email,
                    "scores": dims,
                    "overall_score": overall,
                    "tier": qr.tier(overall),
                    "top_issue": sc["top_issue"],
                }
            except Exception as e:
                if attempt == 2:
                    log.warning("score failed for %s: %s", pid, str(e)[:200])
                    return None

    if todo:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for fut in as_completed([ex.submit(job, it) for it in todo]):
                rec = fut.result()
                if rec is None:
                    continue
                cache[rec["prompt_id"]] = rec
                append_cache(CACHE_FILE, rec)
                if WRITE_LOKI:
                    meta = {
                        "user_email": rec["user_email"],
                        "overall_score": str(rec["overall_score"]),
                        "tier": rec["tier"],
                        "top_issue": rec["top_issue"],
                        **{f"dim_{d}": v for d, v in rec["scores"].items()},
                    }
                    new_streams.append([str(rec["ts"]), rec["prompt_id"], meta])

    if WRITE_LOKI and new_streams:
        pushed_n = push_loki(session, new_streams)
        log.info("wrote %d new quality scores back to Loki", pushed_n)

    # aggregate gauges over everything in the lookback window (cached + freshly scored)
    dim_sum = defaultdict(lambda: defaultdict(float))  # dimension -> email -> sum
    dim_n = defaultdict(lambda: defaultdict(int))
    overall_sum = defaultdict(float)
    overall_n = defaultdict(int)
    tier_count = defaultdict(lambda: defaultdict(int))
    issue_count = defaultdict(lambda: defaultdict(int))
    total = 0

    for pid, ts, email in window:
        rec = cache.get(pid)
        if not rec:
            continue  # not yet scored (backlog beyond MAX_NEW_PER_POLL); picked up next poll
        total += 1
        overall_sum[email] += rec["overall_score"]
        overall_n[email] += 1
        for d, v in rec["scores"].items():
            dim_sum[d][email] += int(v)
            dim_n[d][email] += 1
        tier_count[rec["tier"]][email] += 1
        issue_count[rec["top_issue"]][email] += 1

    OVERALL_AVG.clear()
    DIM_AVG.clear()
    TIER_COUNT.clear()
    TOP_ISSUE_COUNT.clear()
    for email, s in overall_sum.items():
        OVERALL_AVG.labels(user_email=email).set(s / overall_n[email])
    for d, by in dim_sum.items():
        for email, s in by.items():
            DIM_AVG.labels(dimension=d, user_email=email).set(s / dim_n[d][email])
    for t, by in tier_count.items():
        for email, n in by.items():
            TIER_COUNT.labels(tier=t, user_email=email).set(n)
    for iss, by in issue_count.items():
        for email, n in by.items():
            TOP_ISSUE_COUNT.labels(top_issue=iss, user_email=email).set(n)
    PROC.set(total)
    NEW_SCORED.set(len(new_streams))
    COST_TOTAL.set(_cost_usd["total"])
    log.info(
        "poll ok: %d real prompts in window, %d newly scored (~$%.4f this run), cache=%d",
        total,
        len(new_streams),
        _cost_usd["total"],
        len(cache),
    )


def main():
    provider = resolve_provider()
    model = SCORER_MODEL if provider == "anthropic" else SCORER_OPENAI_MODEL
    log.info(
        "prompt-quality-exporter on :%d (Loki=%s, lookback %dd, poll %ds, provider=%s model=%s, "
        "max_new_per_poll=%d)",
        LISTEN_PORT,
        LOKI_URL,
        LOOKBACK_DAYS,
        POLL_INTERVAL,
        provider,
        model,
        MAX_NEW_PER_POLL,
    )
    start_http_server(LISTEN_PORT)
    client = get_client(provider)
    cache = load_cache(CACHE_FILE)

    session = requests.Session()
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session.mount(
        "http://", HTTPAdapter(max_retries=Retry(total=5, connect=5, read=5, backoff_factor=1.5))
    )
    while True:
        try:
            poll_once(session, provider, client, cache)
            LAST_OK.set(time.time())
            ERRORS.set(0)
        except Exception as e:  # noqa: BLE001
            ERRORS.set(1)
            log.exception("poll failed: %s", e)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
