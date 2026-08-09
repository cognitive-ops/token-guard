#!/usr/bin/env python3
"""Prompt-quality exporter.

Reads real developer prompts from Postgres (`user_prompts`, populated by
prompt-store-exporter from Loki), scores each NEW one against the 4-dimension
best-practice rubric (clarity / specificity / structure / robustness, see
quality_rubric.py) via an LLM judge (Anthropic or OpenAI — whichever API key
is present), writes the result into `prompt_quality_scores`, and exposes
per-dimension / tier / issue averages to Prometheus for the "Prompt Quality"
Grafana dashboard.

Unlike prompt-intent-exporter (a free local ONNX model), scoring here costs
real money per call, so:
  - `prompt_quality_scores` (Postgres, keyed by prompt_id) IS the cache — a
    container restart never re-scores (re-pays for) a prompt already scored.
    Non-real prompts (control/injected/empty) are recorded too, with NULL
    scores, so the candidate query never re-considers them either.
  - FETCH_BATCH caps how many unscored candidates are pulled from Postgres per
    poll, and MAX_NEW_PER_POLL further caps how many of those actually get an
    LLM call — a large backlog (e.g. first run) drains gradually instead of
    one cost spike.
  - a running cost estimate is exposed as a gauge so spend is visible
    (resets on restart — it's a live counter, not persisted).
"""

import json
import logging
import os
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
from prometheus_client import Gauge, start_http_server
from psycopg2.extras import execute_values

import quality_rubric as qr

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("prompt-quality-exporter")

DATABASE_URL = os.environ["DATABASE_URL"]
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "7"))  # window for the Prometheus aggregates
FETCH_BATCH = int(os.environ.get("FETCH_BATCH", "1000"))  # unscored candidates pulled per poll
MAX_NEW_PER_POLL = int(os.environ.get("MAX_NEW_PER_POLL", "300"))  # LLM calls per poll (cost guard)
WORKERS = int(os.environ.get("WORKERS", "8"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9110"))

SCORER_MODEL = os.environ.get("SCORER_MODEL", "claude-sonnet-5")
SCORER_OPENAI_MODEL = os.environ.get("SCORER_OPENAI_MODEL", "gpt-4o-mini")
SCORER_EFFORT = os.environ.get("SCORER_EFFORT", "low")
# rough live cost readout; approximate, check current provider pricing pages
PIN, POUT = 2.0 / 1e6, 10.0 / 1e6  # anthropic sonnet
OPENAI_PIN, OPENAI_POUT = 0.15 / 1e6, 0.60 / 1e6  # gpt-4o-mini

DDL = """
CREATE TABLE IF NOT EXISTS prompt_quality_scores (
    prompt_id        TEXT PRIMARY KEY,
    user_email       TEXT,
    event_timestamp  TIMESTAMPTZ,
    category         TEXT NOT NULL,  -- real | control | injected | empty
    clarity          SMALLINT,
    specificity      SMALLINT,
    structure        SMALLINT,
    robustness       SMALLINT,
    overall_score    SMALLINT,
    tier             TEXT,
    top_issue        TEXT,
    suggestion       TEXT,
    scored_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pqs_email_ts ON prompt_quality_scores (user_email, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pqs_ts ON prompt_quality_scores (event_timestamp DESC);
ALTER TABLE prompt_quality_scores ADD COLUMN IF NOT EXISTS suggestion TEXT;
"""

CANDIDATES_SQL = """
SELECT up.prompt_id, up.user_email, up.prompt_text, up.event_timestamp
FROM user_prompts up
LEFT JOIN prompt_quality_scores pqs ON pqs.prompt_id = up.prompt_id
WHERE pqs.prompt_id IS NULL
ORDER BY up.event_timestamp ASC
LIMIT %s
"""

UPSERT_SQL = """
INSERT INTO prompt_quality_scores (
    prompt_id, user_email, event_timestamp, category,
    clarity, specificity, structure, robustness, overall_score, tier, top_issue, suggestion
) VALUES %s
ON CONFLICT (prompt_id) DO NOTHING
"""

AGGREGATE_SQL = """
SELECT user_email, clarity, specificity, structure, robustness, overall_score, tier, top_issue
FROM prompt_quality_scores
WHERE category = 'real' AND event_timestamp > now() - (%s || ' days')::interval
"""

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
# Pasted terminal/log output mistaken for a real ask (multi-line + looks like a
# log line, a Prometheus exposition line, or shell-command output). Heuristic,
# not exhaustive — found by inspecting actual "poor"-tier false positives.
_LOG_MARKERS = re.compile(r"\b(INFO|WARN(?:ING)?|ERROR|DEBUG|HTTP/1\.\d|Traceback \(most recent call last\))\b")
_EXPOSITION = re.compile(r"^#\s*(HELP|TYPE)\b", re.M)
_SHELL_CMD = re.compile(r"^\s*(docker|kubectl|curl|wget|git|npm|pip|python|ls|cat|grep|systemctl|journalctl)\b")


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
    if "\n" in s and (
        _LOG_MARKERS.search(s) or _EXPOSITION.search(s) or (_SHELL_CMD.match(s) and "|" in s)
    ):
        return "pasted_output"
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


def ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def poll_once(conn, provider, client):
    with conn.cursor() as cur:
        cur.execute(CANDIDATES_SQL, (FETCH_BATCH,))
        candidates = cur.fetchall()  # [(prompt_id, user_email, prompt_text, event_timestamp), ...]

    to_score, rows = [], []
    for pid, email, text, ts in candidates:
        cat = categorize(text)
        if cat == "real":
            if len(to_score) < MAX_NEW_PER_POLL:
                to_score.append((pid, email, text, ts))
            # else: leave uncategorized for next poll (don't burn a "seen" row on a
            # real prompt we didn't actually score, so it's retried)
        else:
            rows.append((pid, email, ts, cat, None, None, None, None, None, None, None, None))

    def job(item):
        pid, email, text, ts = item
        for attempt in range(3):
            try:
                sc = score(provider, client, text)
                dims = {d: int(sc[d]) for d in qr.DIMENSIONS}
                overall = qr.overall_score(dims)
                return (
                    pid,
                    email,
                    ts,
                    "real",
                    dims["clarity"],
                    dims["specificity"],
                    dims["structure"],
                    dims["robustness"],
                    overall,
                    qr.tier(overall),
                    sc["top_issue"],
                    sc["suggestion"],
                )
            except Exception as e:
                if attempt == 2:
                    log.warning("score failed for %s: %s", pid, str(e)[:200])
                    return None

    n_new = 0
    if to_score:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for fut in as_completed([ex.submit(job, it) for it in to_score]):
                rec = fut.result()
                if rec is not None:
                    rows.append(rec)
                    n_new += 1

    if rows:
        with conn.cursor() as cur:
            execute_values(cur, UPSERT_SQL, rows)
        conn.commit()

    # aggregate gauges over the lookback window (reads back from Postgres — the
    # source of truth — not an in-memory cache, so gauges are correct across restarts)
    with conn.cursor() as cur:
        cur.execute(AGGREGATE_SQL, (str(LOOKBACK_DAYS),))
        agg_rows = cur.fetchall()

    dim_sum = defaultdict(lambda: defaultdict(float))
    dim_n = defaultdict(lambda: defaultdict(int))
    overall_sum = defaultdict(float)
    overall_n = defaultdict(int)
    tier_count = defaultdict(lambda: defaultdict(int))
    issue_count = defaultdict(lambda: defaultdict(int))

    for email, clarity, specificity, structure, robustness, overall, tier, top_issue in agg_rows:
        email = email or "unknown"
        overall_sum[email] += overall
        overall_n[email] += 1
        for d, v in zip(qr.DIMENSIONS, (clarity, specificity, structure, robustness)):
            dim_sum[d][email] += v
            dim_n[d][email] += 1
        tier_count[tier][email] += 1
        issue_count[top_issue][email] += 1

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
    PROC.set(len(agg_rows))
    NEW_SCORED.set(n_new)
    COST_TOTAL.set(_cost_usd["total"])
    log.info(
        "poll ok: %d candidates fetched, %d newly scored (~$%.4f this run), %d real prompts in "
        "%dd window",
        len(candidates),
        n_new,
        _cost_usd["total"],
        len(agg_rows),
        LOOKBACK_DAYS,
    )


def main():
    provider = resolve_provider()
    model = SCORER_MODEL if provider == "anthropic" else SCORER_OPENAI_MODEL
    log.info(
        "prompt-quality-exporter on :%d (Postgres source, lookback %dd, poll %ds, provider=%s "
        "model=%s, fetch_batch=%d, max_new_per_poll=%d)",
        LISTEN_PORT,
        LOOKBACK_DAYS,
        POLL_INTERVAL,
        provider,
        model,
        FETCH_BATCH,
        MAX_NEW_PER_POLL,
    )
    start_http_server(LISTEN_PORT)
    client = get_client(provider)

    conn = psycopg2.connect(DATABASE_URL)
    ensure_schema(conn)

    while True:
        try:
            if conn.closed:
                conn = psycopg2.connect(DATABASE_URL)
            poll_once(conn, provider, client)
            LAST_OK.set(time.time())
            ERRORS.set(0)
        except Exception as e:  # noqa: BLE001
            ERRORS.set(1)
            log.exception("poll failed: %s", e)
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
