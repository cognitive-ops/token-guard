# Claude Code ROI Analytics

Self-hosted analytics for Token Guard's Claude Code usage. Claude Code emits OpenTelemetry
metrics + logs → an OTEL Collector fans them out to **Prometheus** (metrics) and **Loki**
(events/logs) → two dashboard frontends read from those: **Grafana** and a **Next.js** app.

## Repository layout

| Path | What |
|------|------|
| `docker-compose.yml` | The whole stack (collector, Prometheus, Loki, Grafana, exporters). |
| `otel-collector-config.yaml` | OTLP ingest → Prometheus + Loki. |
| `prometheus.yml` | Scrape config + `project_name` relabeling (repo → project). |
| `loki-config.yaml` | Loki single-binary config (retention, query splits, OTLP index labels). |
| `grafana/dashboards/*.json` | Provisioned Grafana dashboards (dashboard-as-code). |
| `web/` | Next.js dashboard app (the going-forward UI). Data layer in `web/src/lib/data/`. |
| `billing-exporter/` | Pulls Anthropic Admin Cost/Usage APIs → real-cost Prometheus gauges. |
| `prompt-lang-exporter/`, `prompt-intent-exporter/` | Classify prompts from Loki → Prometheus gauges (see "Pre-calculated views"). |
| `prompt-quality-exporter/` | Scores prompt clarity/specificity/structure/robustness via an LLM judge (Anthropic or OpenAI). Reads from and writes to **Postgres** (`user_prompts` → `prompt_quality_scores`), not Loki directly — Postgres is the durable full corpus; Loki's retention is short. Also emits Prometheus gauges. Unlike the other exporters this costs real money per new prompt scored — see its README for the cost guards (Postgres-as-cache, per-poll cap). |
| `prompt-store-exporter/` | Writes raw prompt text from Loki into Postgres (`user_prompts` table) — per-developer prompt content, queryable by SQL. |
| `prompt-intent-classifier/` | Training/eval for the ONNX intent model the intent-exporter loads. |
| `prompt-explorer/` | Tooling to view real prod data locally over an SSM tunnel. |
| `alarms/` | CloudWatch container-health alarms (CloudFormation + agent config). |

## Local development

```bash
# Full stack (Grafana :3000, Prometheus :9090, Loki :3100, exporters). Seeded demo data.
docker compose up -d
python tools/seed-demo-data.py        # populate demo metrics/logs

# Next.js app
cd web && npm install
npm run dev                            # :3001, reads PROMETHEUS_URL / LOKI_URL from env
npm run typecheck && npm run lint && npm test && npm run build   # full local gate
```

`web` env (see `web/.env.example`): `PROMETHEUS_URL`, `LOKI_URL`, `QUERY_TIMEOUT_MS`
(default 15s), `REVALIDATE_SECONDS` (default 300 — cross-request cache TTL),
`DEFAULT_RANGE_DAYS` (30), `ADMIN_KEY[_PATH]` (for the API-cost page).

To explore **real production** data locally, run `prompt-explorer/online-tunnels.sh`
(SSM port-forwards prod Prometheus/Loki to localhost + a relay; a gitignored
`docker-compose.override.yml` repoints Grafana's datasources). Relayed data lags `now`,
so validate PromQL with `query_range`, not instant queries at `now`.

## Production deployment

- **Host:** EC2 `<EC2_INSTANCE_ID>`, AWS profile `your-aws-profile`, region
  `us-east-1`, public IP 54.227.49.106. Amazon Linux 2023, **ARM64**, 2 vCPU / ~7.6 GB.
- **Access (read-only ops):** via SSM, no SSH/bastion needed. Interactive:
  `aws ssm start-session --target <EC2_INSTANCE_ID> --profile your-aws-profile`.
  Scripted: `aws ssm send-command --document-name AWS-RunShellScript ...` then
  `get-command-invocation`. Containers reach each other by service name; from the host,
  resolve a container IP with `docker inspect -f '{{...}}' <name>`.
- **Stack dir on box:** `/home/ec2-user/claude-analytics`. **Deploys are MANUAL** — the
  compose files and configs are hand-edited on the box (no git remote/checkout there).
  Any config change in this repo (e.g. `loki-config.yaml`, `otel-collector-config.yaml`)
  must be copied to the box and the affected container restarted; keep the two in sync.
- **Services & ports:** `grafana` (0.0.0.0:3000), `claude-roi-web` (0.0.0.0:3001),
  `otel-collector` (4317/4318 OTLP ingest, 13133 health), `prometheus`/`loki`/exporters
  internal-only. **No on-box reverse proxy/TLS** — HTTPS for
  `grafana.claude-analytics.example.com` / `dashboard.…` / `otel.…` is terminated
  **upstream** (ALB/Cloudflare → instance). Confirm the terminator in AWS/DNS before any
  hostname cutover.
- **Pending deploy:** `postgres` + `prompt-store-exporter` (raw prompt-text store, see
  `prompt-store-exporter/README.md`) and the Grafana **Prompt Explorer** dashboard/card on
  Home only exist in local `docker-compose` so far — not yet copied to the box. Until
  deployed there, the Home page's "Prompt Explorer" card 404s on the shared/production
  Grafana. When deploying: keep `postgres`'s `5432` **internal-only** (no host port
  publish) like `prometheus`/`loki` — it holds unredacted developer prompt text, and unlike
  those two it isn't intended for direct psql access from the internet, only via Grafana's
  proxied datasource. Also copy `POSTGRES_USER/PASSWORD/DB` into the box's `.env`.
- **Auth:** Grafana uses Keycloak OIDC (`auth.example.com`, realm `YourCompany`,
  client `claude-code-analytics`; roles `grafana-admin`→Admin, `grafana-viewer`→Viewer).
  The web app has its own login (`WEB_AUTH_ENABLED`, `WEB_LOCAL_LOGIN_ENABLED`). Secrets
  live in the box's `.env` (`OTEL_AUTH_TOKEN`, `KEYCLOAK_*`, `DASHBOARD_*`) and
  `.secrets/admin-key` — never commit these.

## Data architecture

- **OTEL Collector** authenticates OTLP (bearer token) and exports:
  - **metrics → Prometheus** (`resource_to_telemetry_conversion` on, so `user.email`,
    `model`, `terminal.type`, etc. become metric labels). `user_email` cardinality is low
    (~47) so per-developer PromQL is sub-millisecond.
  - **logs/events → Loki**. Claude Code sends `user.email`, `session.id`, `event.name`,
    `prompt.id`, … as **log-record attributes** (→ Loki structured metadata); only
    `service.name` (claude-code, -intent, -behavior, -command, -desktop) is a resource
    attr → stream label. `groupbyattrs/loki` lifts `user.email` to a resource attr so Loki
    can index it as a stream label (see `loki-config.yaml` `otlp_config`).
- **Prometheus** = numeric usage (cost estimate, tokens, LOC, commits, sessions, active
  time). 10y retention / 15 GB cap. **OTEL cost is an ESTIMATE** (tokens × list price), not
  the bill — real cost comes from the billing-exporter.
- **Loki** = raw events: `user_prompt` (prompt text + metadata), `tool_result`, plus the
  exporter-written `claude-code-{intent,behavior,command}` streams. 90d retention; the
  whole `claude-code` stream is ~580k entries / ~240 MB per 30d.

## Pre-calculated views (why per-developer queries are fast)

Filtering Loki by a structured-metadata `user_email` scans the whole `claude-code` stream
(~2–5 s on this box). The fix is **materialized views**: the exporters poll Loki hourly and
pre-compute counts into Prometheus gauges, read in <1 ms:

- `claude_prompt_count{user_email}`, `claude_prompt_length_{sum,max}{user_email}`,
  `claude_prompt_count_by_{terminal,os}` (prompt-lang-exporter)
- `claude_prompt_language_count{language,user_email}` (prompt-lang-exporter)
- `claude_prompt_{intent,behavior,command}_count{…,user_email}` (prompt-intent-exporter)
- `claude_prompt_quality_{overall_avg,dimension_avg,tier_count,top_issue_count}{…,user_email}`
  (prompt-quality-exporter) — LLM-judged, so this snapshot only grows on new prompts up to
  `MAX_NEW_PER_POLL`/poll, not the full lookback window every time (cost control)

These gauges are a **fixed ~30-day snapshot**, so they don't honor an arbitrary time
picker. Both frontends therefore use a **hybrid**: the fast Prometheus gauge for ~30-day
(default) windows, falling back to the time-accurate Loki `count_over_time` for shorter
windows.
- Next.js: `web/src/lib/data/common.ts` → `isSnapshotWindow` / `snapshotScalar` /
  `snapshotByLabel` (28-day floor); used across `developer.ts`, `overview.ts`,
  `usage-patterns.ts`, `real-cost.ts`.
- Grafana: snapshot-style panels (org breakdowns, leaderboards, behavior rates, total
  prompts) read the gauges directly and are labelled "~30-day snapshot"; only true
  time-series (prompts-over-time, prompt-length-over-time) and `tool_result` (no gauge yet)
  stay on Loki.

Loki itself is also tuned: `split_queries_by_interval` +
`split_instant_metric_queries_by_interval` (24h) + result caching so the remaining Loki
scans parallelize and reuse per-day results.

**Extending this:** the `tool_result` and prompts/length-over-time panels still hit Loki
live. To pre-calculate them too, add a materializing exporter (same pattern) or Prometheus
recording rules; that's the path to making every panel snapshot-fast.

## Gotchas

- Cost-report `amount` from the Admin API is in **cents** (decimal string) — divide by 100.
  Seat developers' real cost is the flat seat fee, not the OTEL estimate.
- Loki client clamps query windows to 30d (a 90d pick silently returns 30d of events).
- Exporters `GAUGE.clear()` then repopulate each hourly poll; a scrape in that millisecond
  window briefly sees missing series.
- `prompt-lang-exporter` is memory-tight (holds the 30d prompt corpus while polling).
- `user_prompts` (Postgres) has no retention/cleanup job — it grows unbounded and holds
  raw, unredacted prompt text. Restrict DB access; add a `DELETE ... WHERE event_timestamp
  < ...` cron if you need retention.
