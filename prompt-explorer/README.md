# Prompt Explorer (local-only, opt-in)

A throwaway, **local** Grafana for inspecting Claude Code **user prompts**. It is
deliberately *not* part of the production stack and is **never** provisioned onto the
shared `grafana.claude-analytics.example.com` server — prompt text stays on your
machine, only while you have it turned on.

By default it reads from a **local Loki** — the repo-root docker-compose `loki`
service — no AWS access needed. (An "online · prod via SSM" datasource option still
exists in the dropdown if you set up your own SSM port-forward later, but it's not
required.)

## Prerequisites
- Docker + Docker Compose
- The repo-root `loki` service running, with some data in it:
  ```bash
  cd ..                                  # token-guard root
  docker compose up -d loki
  python tools/seed-demo-data.py loki    # or your own hooks/log-prompt.sh events
  ```

## Turn on / off
```bash
./start.sh    # checks local Loki is reachable + starts local Grafana
# open http://localhost:3001   (anonymous admin; nothing exposed beyond localhost)
./stop.sh     # stops Grafana
```

Override defaults via env if needed: `LOKI_LOCAL_PORT` (start.sh's reachability
check), `LOCAL_LOKI_URL` (the URL Grafana's container itself uses — same port, but
via `host.docker.internal`).

## What you get
- **Prompts (newest first)** — each prompt rendered as a readable line; expand a row for
  `user_email`, `session_id`, `prompt_id`, `repository_fullname`, terminal/OS.
- **Filters** — `User (email contains)` and `Prompt contains` (both case-insensitive regex).
- **Prompts by user** — per-user counts over the selected range.
- **Prompts over time** and **active users** KPIs.

## Why local-only
`user_prompt` events contain raw prompt text — source snippets, file paths, sometimes
secrets devs pasted. Keeping the viewer local + opt-in means full prompt content is never
published to the team-wide dashboard or stored anywhere new. Aggregate/derived analytics
that don't expose content (prompt language, length, volume) belong on the shared server
instead — see the `prompt-lang-exporter`.

## Notes
- The local Loki datasource points at `http://host.docker.internal:3100` (the root
  compose's `loki` service, reached from this container via the Docker host gateway).
- Loki retention is set by the root `loki-config.yaml` (currently 10y for the local
  stack; prod may differ) — that's the maximum lookback.
