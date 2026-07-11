# Prompt Explorer (local-only, opt-in)

A throwaway, **local** Grafana for inspecting actual Claude Code **user prompts**. It is
deliberately *not* part of the production stack and is **never** provisioned onto the
shared `grafana.claude-analytics.scopicdev.com` server — prompt text stays on your
machine, only while you have it turned on.

It reads `user_prompt` events from the production Loki over an **SSM port-forward**, so
no data is copied or persisted locally beyond the running container.

## Prerequisites
- AWS access to the analytics instance via the `scopic-ml-development` profile
- `session-manager-plugin` installed
- Docker + Docker Compose

## Turn on / off
```bash
./start.sh    # opens the SSM tunnel to Loki + starts local Grafana
# open http://localhost:3001   (anonymous admin; nothing exposed beyond localhost)
./stop.sh     # stops Grafana + closes the tunnel
```

Override defaults via env if needed:
`AWS_PROFILE`, `SSM_INSTANCE`, `LOKI_LOCAL_PORT`.

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
- The Loki datasource points at `http://host.docker.internal:3100` (the tunnel on the host).
- Loki retention is 720h (30 days), so that's the maximum lookback.
