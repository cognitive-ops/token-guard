# Developer Client Setup — Pushing Metrics to the EC2 Collector

How a developer's local machine sends Claude Code telemetry to the production
OTEL Collector on EC2.

## 1. Env vars (per-developer)

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp
export OTEL_LOGS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
export OTEL_EXPORTER_OTLP_ENDPOINT=https://otel.claude-analytics.example.com:443
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer <OTEL_AUTH_TOKEN>"

# optional: capture raw prompt text into Loki (needed for prompt-intent /
# prompt-quality / prompt-store exporters)
export OTEL_LOG_USER_PROMPTS=1
```

Verify locally before rolling out (console exporter, no network needed):
```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=console
export OTEL_METRIC_EXPORT_INTERVAL=1000
claude -p "hello world"
```

## 2. Org-wide rollout: `managed-settings.json`

Push via MDM so every developer is configured consistently and can't disable
telemetry:

```json
{
  "telemetry": {
    "enabled": true,
    "endpoint": "https://otel.claude-analytics.example.com:443",
    "headers": {
      "Authorization": "Bearer ${OTEL_TOKEN}"
    }
  },
  "exporters": {
    "metrics": "otlp",
    "logs": "otlp"
  }
}
```

## 3. Endpoint: use the hostname, not the raw EC2 IP

The collector itself has **no TLS** (`otel-collector-config.yaml` receivers
are plain `grpc`/`http`). HTTPS for `otel.claude-analytics.example.com` is
terminated **upstream** (ALB/Cloudflare) in front of the EC2 instance. Point
clients at that hostname, never at `<public-ip>:4317` directly — otherwise
the bearer token and prompt content travel unencrypted over the internet.

**Before rolling this out to developers, confirm the upstream TLS terminator
for the `otel.…` hostname is actually provisioned** — it is not guaranteed by
the app config alone; check AWS/DNS.

## 4. Auth token

The collector's `bearertokenauth` extension (`otel-collector-config.yaml`)
requires `Authorization: Bearer <OTEL_AUTH_TOKEN>` on both the gRPC (4317)
and HTTP (4318) receivers — request is rejected otherwise. The token is
`OTEL_AUTH_TOKEN` in the box's `.env` (gitignored, generated with
`openssl rand -hex 32`, see `.env.example`).

Distribute it to developers out-of-band (secrets manager / password manager),
never via commit, chat message, or unencrypted MDM payload. Server and every
client must use the same value.

## 5. Firewall / network path

The EC2 security group should only need to admit traffic from the upstream
terminator (ALB/Cloudflare edge), not directly from developer IPs — connections
should route through the TLS-terminating hostname, not straight to the
instance's `4317`/`4318`. If no terminator is live yet, that blocks any
client rollout: don't expose the raw ports directly to developer machines.

## See also

- `docs/troubleshooting.md` — telemetry not appearing, hangs, etc.
- `docs/claude-code-roi-full.md` — full metrics/queries reference.
- Root `CLAUDE.md` — EC2 host details, stack layout, deploy process.
