#!/usr/bin/env python3
"""Prompt-store exporter.

Tails `user_prompt` events from Loki and writes the raw prompt text into
Postgres, keyed by `prompt_id`, so prompt content can be queried per-developer
with plain SQL (Grafana SQL panels, psql, DBeaver, ...) instead of Loki's
LogQL. Loki remains the source of truth / long-tail retention; this is a
queryable projection of it, same spirit as the other exporters' Prometheus
gauges but row-shaped instead of aggregated.

Polls a short, overlapping lookback window frequently (rather than the other
exporters' "recompute the whole 30d window hourly" pattern) so new prompts
show up in Postgres within roughly a minute; `ON CONFLICT (prompt_id) DO
NOTHING` makes the overlap idempotent and safe across restarts.
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone

import psycopg2
import requests
from prometheus_client import Gauge, start_http_server
from psycopg2.extras import execute_values

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("prompt-store-exporter")

LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
DATABASE_URL = os.environ["DATABASE_URL"]
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))
LOOKBACK_MINUTES = int(os.environ.get("LOOKBACK_MINUTES", "20"))  # > POLL_INTERVAL: covers restarts/backlog
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9110"))
PAGE_LIMIT = int(os.environ.get("PAGE_LIMIT", "5000"))
LOKI_QUERY = os.environ.get("LOKI_QUERY", '{service_name="claude-code"} | event_name="user_prompt"')

ROWS_INSERTED = Gauge(
    "claude_prompt_store_rows_inserted_last_poll", "New prompt rows inserted in the last poll"
)
ROWS_SEEN = Gauge(
    "claude_prompt_store_rows_seen_last_poll", "user_prompt events read from Loki in the last poll"
)
LAST_SUCCESS = Gauge(
    "claude_prompt_store_exporter_last_success_timestamp", "Unix timestamp of the last successful poll"
)
SCRAPE_ERRORS = Gauge("claude_prompt_store_exporter_errors", "1 if the last poll failed, 0 otherwise")

DDL = """
CREATE TABLE IF NOT EXISTS user_prompts (
    prompt_id            TEXT PRIMARY KEY,
    session_id           TEXT,
    user_email           TEXT NOT NULL,
    prompt_text          TEXT NOT NULL,
    prompt_length        INTEGER,
    terminal_type        TEXT,
    os_type              TEXT,
    repository_fullname  TEXT,
    event_timestamp      TIMESTAMPTZ NOT NULL,
    ingested_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_prompts_email_ts ON user_prompts (user_email, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_user_prompts_ts ON user_prompts (event_timestamp DESC);
"""

UPSERT = """
INSERT INTO user_prompts (
    prompt_id, session_id, user_email, prompt_text, prompt_length,
    terminal_type, os_type, repository_fullname, event_timestamp
) VALUES %s
ON CONFLICT (prompt_id) DO NOTHING
"""


def ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def fetch_prompts(session, start, end):
    """Yield Loki stream-label dicts for every user_prompt event in [start, end)."""
    next_start_ns = int(start.timestamp() * 1e9)
    end_ns = int(end.timestamp() * 1e9)
    while True:
        r = session.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={
                "query": LOKI_QUERY,
                "start": str(next_start_ns),
                "end": str(end_ns),
                "limit": str(PAGE_LIMIT),
                "direction": "forward",
            },
            timeout=60,
        )
        r.raise_for_status()
        result = r.json().get("data", {}).get("result", [])
        max_ts = next_start_ns
        n = 0
        for stream in result:
            labels = stream.get("stream", {})
            for ts, _line in stream.get("values", []):
                n += 1
                ts = int(ts)
                if ts > max_ts:
                    max_ts = ts
                yield ts, labels
        if n < PAGE_LIMIT or max_ts <= next_start_ns:
            return
        next_start_ns = max_ts + 1  # paginate forward past the last entry


def to_row(ts_ns, labels):
    prompt_id = labels.get("prompt_id")
    prompt_text = labels.get("prompt")
    user_email = labels.get("user_email")
    if not prompt_id or not prompt_text or not user_email:
        return None
    try:
        prompt_length = int(labels.get("prompt_length") or len(prompt_text))
    except (TypeError, ValueError):
        prompt_length = len(prompt_text)
    event_ts = labels.get("event_timestamp")
    ts = (
        datetime.fromisoformat(event_ts.replace("Z", "+00:00"))
        if event_ts
        else datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc)
    )
    return (
        prompt_id,
        labels.get("session_id"),
        user_email,
        prompt_text,
        prompt_length,
        labels.get("terminal_type"),
        labels.get("os_type"),
        labels.get("repository_fullname"),
        ts,
    )


def poll_once(session, conn):
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=LOOKBACK_MINUTES)
    rows, seen = [], 0
    for ts_ns, labels in fetch_prompts(session, start, end):
        seen += 1
        row = to_row(ts_ns, labels)
        if row:
            rows.append(row)

    inserted = 0
    if rows:
        with conn.cursor() as cur:
            execute_values(cur, UPSERT, rows)
            inserted = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        conn.commit()

    ROWS_SEEN.set(seen)
    ROWS_INSERTED.set(inserted)
    log.info("poll ok: %d user_prompt events seen, %d new rows", seen, inserted)


def main():
    log.info(
        "prompt-store-exporter on :%d (Loki=%s, lookback %dmin, poll %ds)",
        LISTEN_PORT,
        LOKI_URL,
        LOOKBACK_MINUTES,
        POLL_INTERVAL,
    )
    start_http_server(LISTEN_PORT)

    conn = psycopg2.connect(DATABASE_URL)
    ensure_schema(conn)

    session = requests.Session()
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session.mount(
        "http://",
        HTTPAdapter(max_retries=Retry(total=5, connect=5, read=5, backoff_factor=1.5)),
    )

    while True:
        try:
            if conn.closed:
                conn = psycopg2.connect(DATABASE_URL)
            poll_once(session, conn)
            LAST_SUCCESS.set(time.time())
            SCRAPE_ERRORS.set(0)
        except Exception as e:  # noqa: BLE001
            SCRAPE_ERRORS.set(1)
            log.exception("poll failed: %s", e)
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
