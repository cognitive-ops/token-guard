# Prompt-quality exporter

Scores each Claude Code developer prompt against a 4-dimension best-practice
rubric — **clarity**, **specificity**, **structure**, **robustness** (see
`quality_rubric.py`) — and exposes per-dimension / tier / issue averages to
Prometheus for the **Prompt Quality** Grafana dashboard.

```mermaid
flowchart LR
    PG1[("Postgres<br/>user_prompts")] --> EX["prompt-quality-exporter"]
    EX --> F{"categorize"}
    F -- "control / injected /<br/>pasted_output" --> SKIP["write NULL-score row<br/>(marks it seen)"]
    F -- real prompt --> LLM["LLM judge<br/>(Anthropic or OpenAI)"]
    LLM --> PG2[("Postgres<br/>prompt_quality_scores")]
    SKIP --> PG2
    PG2 --> AGG["aggregate over lookback window"]
    AGG --> G["claude_prompt_quality_*"]
    G --> PR[("Prometheus")] --> GR["Grafana · Prompt Quality"]
    PG2 -.-> DD["Grafana SQL panel<br/>(joins prompt_text)"]
```

Reads real prompt text from **Postgres** (`user_prompts`, populated by
`prompt-store-exporter` from Loki) rather than Loki directly — Loki's
retention is short and this exporter needs to backfill/catch up over the full
corpus, which Postgres holds (unbounded, per the root `CLAUDE.md` gotcha on
`user_prompts`).

Unlike `prompt-intent-exporter` (a free local ONNX model), scoring here calls a
paid LLM per prompt, so cost is actively managed:

- **`prompt_quality_scores` (Postgres) IS the cache** — a container restart
  never re-scores (re-pays for) a prompt already scored. Non-real prompts
  (control/injected/empty/pasted_output) get a row too, with `NULL` scores, so
  the candidate query never reconsiders them either.
- **`FETCH_BATCH`** caps how many unscored candidates are pulled from Postgres
  per poll; **`MAX_NEW_PER_POLL`** further caps how many of those get an
  actual LLM call — a large backlog (e.g. first run) drains gradually instead
  of one cost spike.
- **`claude_prompt_quality_exporter_cost_usd_total`** gauge tracks cumulative
  estimated spend — resets on restart (it's a live counter, not persisted;
  the Postgres cache is what's persisted).
- Smaller default lookback for the Prometheus aggregates (`LOOKBACK_DAYS=7` vs.
  intent's 29) — this is a scoring cost, not a free aggregation.

## Metrics

| Metric | Labels | Meaning |
|--------|--------|---------|
| `claude_prompt_quality_overall_avg` | `user_email` | avg overall score (0-100) over the lookback window |
| `claude_prompt_quality_dimension_avg` | `dimension`, `user_email` | avg per-dimension score (1-5) |
| `claude_prompt_quality_tier_count` | `tier`, `user_email` | prompt count by tier (poor/fair/good/excellent) |
| `claude_prompt_quality_top_issue_count` | `top_issue`, `user_email` | prompt count by limiting issue |
| `claude_prompt_quality_prompts_total` | — | real prompts in the lookback window with a score |
| `claude_prompt_quality_exporter_new_scored_last_poll` | — | prompts newly LLM-scored last poll (cost driver) |
| `claude_prompt_quality_exporter_cost_usd_total` | — | cumulative estimated USD spent since start |
| `claude_prompt_quality_exporter_last_success_timestamp` | — | last good poll |
| `claude_prompt_quality_exporter_errors` | — | 1 if last poll failed |

## Postgres schema

Creates `prompt_quality_scores` on startup if missing (`prompt_id` PK, joins
1:1 against `user_prompts.prompt_id`):

```sql
CREATE TABLE prompt_quality_scores (
    prompt_id        TEXT PRIMARY KEY,
    user_email       TEXT,
    event_timestamp  TIMESTAMPTZ,
    category         TEXT NOT NULL,  -- real | control | injected | empty | pasted_output
    clarity          SMALLINT,       -- NULL for non-real prompts
    specificity      SMALLINT,
    structure        SMALLINT,
    robustness       SMALLINT,
    overall_score    SMALLINT,
    tier             TEXT,
    top_issue        TEXT,
    suggestion       TEXT,           -- one-line rewrite tip from the judge; empty if top_issue is "none"
    scored_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`pasted_output` (added after real usage showed false positives): multi-line
text that looks like pasted terminal/log output — a log-level marker
(`INFO`/`ERROR`/…), a Prometheus exposition line (`# HELP`/`# TYPE`), or a
piped shell command — rather than an actual developer ask. Heuristic, not
exhaustive; see `categorize()` in `exporter.py`.

The "worst-scoring prompts" drilldown panel on the Grafana dashboard is a
Postgres SQL panel that joins this against `user_prompts` for the actual
prompt text and the `suggestion` — see
`grafana/dashboards/prompt-quality-dashboard.json`.

## Config (env)

| Var | Default | Notes |
|-----|---------|-------|
| `DATABASE_URL` | *(required)* | e.g. `postgresql://user:pass@postgres:5432/tokenguard` |
| `LOOKBACK_DAYS` | `7` | window for the Prometheus aggregate gauges |
| `POLL_INTERVAL_SECONDS` | `300` | Postgres reads are cheap; only new-prompt LLM calls cost money |
| `FETCH_BATCH` | `1000` | unscored candidates pulled from Postgres per poll |
| `MAX_NEW_PER_POLL` | `300` | cap on prompts that actually get an LLM call per poll (cost guard) |
| `WORKERS` | `8` | concurrent LLM calls per poll |
| `SCORER_PROVIDER` | `auto` | `auto` picks Anthropic if `ANTHROPIC_API_KEY` is set, else OpenAI if `OPENAI_API_KEY` is set |
| `SCORER_MODEL` | `claude-sonnet-5` | Anthropic model |
| `SCORER_OPENAI_MODEL` | `gpt-4o-mini` | OpenAI fallback model |
| `SCORER_EFFORT` | `low` | Anthropic `output_config.effort` |

Needs `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY` in the stack's `.env`.

## Rubric

Same rubric as `prompt-intent-classifier/src/quality_rubric.py` (vendored here
so this exporter's Docker build context stays self-contained, same convention
as the other exporters). Keep the two in sync by hand if the rubric changes.
