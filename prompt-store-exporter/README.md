# Prompt-store exporter

Writes raw `user_prompt` events from Loki into Postgres, one row per prompt, so
prompt **content** can be queried per-developer with plain SQL — psql, DBeaver,
or a Grafana SQL panel — instead of LogQL against Loki.

```mermaid
flowchart LR
    LK[("Loki<br/>user_prompt events")] --> EX["prompt-store-exporter<br/>(poll every 60s, 20min lookback)"]
    EX -- "UPSERT ON CONFLICT(prompt_id)" --> PG[("Postgres<br/>user_prompts")]
    PG --> Q["psql / DBeaver / Grafana SQL panel"]
```

- **Source:** `user_prompt` events in Loki (requires `OTEL_LOG_USER_PROMPTS=1` so
  the prompt *text* is logged, not just the count — same prerequisite as
  `prompt-lang-exporter`).
- **Why poll instead of a Loki sink directly:** keeps this exporter stateless and
  restart-safe — no checkpoint to persist. A short, overlapping lookback window
  polled frequently, deduped by `prompt_id` via `ON CONFLICT DO NOTHING`, gets new
  prompts into Postgres within about a minute without ever double-counting.

## Schema

```sql
CREATE TABLE user_prompts (
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
```

Query example — a developer's last 50 prompts:

```sql
SELECT event_timestamp, terminal_type, prompt_text
FROM user_prompts
WHERE user_email = 'someone@example.com'
ORDER BY event_timestamp DESC
LIMIT 50;
```

## Config (env)

| Var | Default | Notes |
|-----|---------|-------|
| `LOKI_URL` | `http://loki:3100` | |
| `DATABASE_URL` | *(required)* | `postgresql://user:pass@postgres:5432/db` |
| `POLL_INTERVAL_SECONDS` | `60` | |
| `LOOKBACK_MINUTES` | `20` | must exceed `POLL_INTERVAL_SECONDS`; covers restarts/backlog |
| `LOKI_QUERY` | `{service_name="claude-code"} \| event_name="user_prompt"` | |

## Metrics (`:9110`)

| Metric | Meaning |
|--------|---------|
| `claude_prompt_store_rows_seen_last_poll` | user_prompt events read from Loki last poll |
| `claude_prompt_store_rows_inserted_last_poll` | new rows actually written (post-dedup) |
| `claude_prompt_store_exporter_last_success_timestamp` | last good poll |
| `claude_prompt_store_exporter_errors` | 1 if last poll failed |

## Privacy note

This stores full prompt text per developer, indefinitely (no retention job —
add one, e.g. a periodic `DELETE ... WHERE event_timestamp < now() - interval`,
if you need one). Treat `user_prompts` as sensitive: it's raw, unredacted
developer input, potentially including secrets pasted into a prompt. Restrict
DB access accordingly.
