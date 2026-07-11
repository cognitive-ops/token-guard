# Claude Code Analytics — Alarms

CloudWatch monitoring for the Claude Code Analytics stack (Prometheus / Grafana /
Loki / otel) running on EC2 instance `i-0fe9d2092e0ab25cd` behind `scopic-ai-dev-alb`.

Account: **scopic-ml-development** (`320963574916`) · Region: **us-east-1**

## Files

| File | What it is |
|------|------------|
| `amazon-cloudwatch-agent.json` | CloudWatch Agent config for the EC2 host. Produces the host-level metrics (`mem_used_percent`, `swap_used_percent`, `disk_used_percent`) that three of the alarms watch. Without the agent emitting these, those alarms sit in `INSUFFICIENT_DATA`. |
| `cloudformation.yaml` | CloudFormation template defining 16 CloudWatch alarms (5 host/ALB + 8 per-container "down" + 3 billing-exporter health) + an SNS topic and email subscription. The alarms only *watch* metrics — they don't produce them. |
| `container-health-metrics.sh` | Host script that publishes `ContainerUp` (1/0) per container to the `ClaudeAnalytics/Containers` namespace — the metric the 8 container-down alarms watch. Emits an explicit `0` for a stopped/missing/unhealthy container so "down" reads as 0, not a data gap. |
| `container-health-metrics.service` / `.timer` | systemd unit + timer that run the script every minute (the box has **no cron** — `crond` isn't installed on this AL2023 host). |
| `billing-health-metrics.sh` | Host script that reads the billing exporter's health gauges back from Prometheus and publishes them to the `ClaudeAnalytics/Billing` namespace — the metrics the 3 billing-health alarms watch (`ExporterErrors`, `StalenessSeconds`, `SilentZeroServiceCost`). Catches a stale or silently-wrong cost figure. |
| `billing-health-metrics.service` / `.timer` | systemd unit + timer that run the billing-health script every 5 minutes. |

The two halves are complementary: the agent **produces** the host metrics; the
CloudFormation stack **alarms on** them. ALB-based alarms (slow response, unhealthy
target) need no agent — AWS emits those automatically.

## Prerequisite: IAM

The instance needs a role that allows publishing metrics. Already set up:

- Role `claude-analytics-cwagent-role` with managed policy `CloudWatchAgentServerPolicy`
- Instance profile `claude-analytics-cwagent-profile`, associated with `i-0fe9d2092e0ab25cd`

Without this the agent runs but every `PutMetricData` returns `AccessDenied`.

## Deploy 1 — CloudWatch Agent (on the EC2 instance)

Amazon Linux 2023 / aarch64.

```bash
# Install (AL2023 ships it in the repos)
sudo dnf install -y amazon-cloudwatch-agent

# Copy this config into place (e.g. via scp, then):
sudo cp amazon-cloudwatch-agent.json \
  /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json

# Load config + start (also enables the systemd service)
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json

# Verify
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a status
```

Confirm metrics arrive (~2 min after start):

```bash
aws cloudwatch list-metrics --namespace CWAgent --region us-east-1 \
  --dimensions Name=InstanceId,Value=i-0fe9d2092e0ab25cd
```

> **Disk dimensions:** `disk_used_percent` is emitted with dimensions
> `InstanceId`, `path=/`, and `fstype=xfs` (the `device` dimension is dropped via
> `"drop_device": true`). The disk alarm in `cloudformation.yaml` must match this
> exact set, or it won't bind to the metric. If the root filesystem type ever
> changes, update the alarm's `fstype` value.

## Deploy 2 — Alarms stack (CloudFormation)

```bash
aws cloudformation create-stack --region us-east-1 \
  --stack-name claude-analytics-alarms \
  --template-body file://cloudformation.yaml
```

Then **confirm the SNS subscription**: the email in the `AlertEmail` parameter
(`wayan.w@scopicsoftware.com`) receives a confirmation link. Until it's clicked,
the subscription stays `PendingConfirmation` and no alerts are delivered.

Watch it come up:

```bash
aws cloudformation describe-stack-events --region us-east-1 \
  --stack-name claude-analytics-alarms
```

Update later with `update-stack`; tear down with
`aws cloudformation delete-stack --stack-name claude-analytics-alarms`.

## Deploy 3 — Container health producer (on the EC2 instance)

The box has no cron, so a **systemd timer** runs the publisher every minute.

```bash
# from /home/ec2-user/claude-analytics/alarms
chmod +x container-health-metrics.sh
sudo cp container-health-metrics.service container-health-metrics.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now container-health-metrics.timer

# verify
systemctl list-timers container-health-metrics.timer --no-pager
journalctl -u container-health-metrics -n 20 --no-pager
aws cloudwatch list-metrics --region us-east-1 --namespace ClaudeAnalytics/Containers
```

To add/remove a monitored container: edit the `CONTAINERS` map in the script **and**
the matching alarm in `cloudformation.yaml`, then redeploy both.

## Deploy 4 — Billing health producer (on the EC2 instance)

Same pattern as Deploy 3: a systemd timer runs the billing-health publisher every
5 minutes. It reads the exporter's health gauges from Prometheus (internal-only, so
it resolves the container IP from the host) and forwards them to CloudWatch. Needs
`python3` on the host (ships with AL2023) for JSON parsing.

```bash
# from /home/ec2-user/claude-analytics/alarms
chmod +x billing-health-metrics.sh
sudo cp billing-health-metrics.service billing-health-metrics.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now billing-health-metrics.timer

# verify
systemctl list-timers billing-health-metrics.timer --no-pager
journalctl -u billing-health-metrics -n 20 --no-pager
aws cloudwatch list-metrics --region us-east-1 --namespace ClaudeAnalytics/Billing
```

## The alarms

**Host / ALB (5):**

| # | Alarm | Source | Needs agent? |
|---|-------|--------|--------------|
| 1 | High memory (> 85%, 5 min) | `CWAgent` `mem_used_percent` | Yes |
| 2 | Swap pressure (> 50%, 10 min) | `CWAgent` `swap_used_percent` | Yes |
| 3 | Grafana slow response (p95 > 3s, 3 of 5 periods) | ALB `TargetResponseTime` | No |
| 4 | Grafana target unhealthy (≥ 1, 3 min) | ALB `UnHealthyHostCount` | No |
| 5 | Root disk filling (> 85%) | `CWAgent` `disk_used_percent` | Yes |

**Per-container down (8):** one alarm each for `prometheus`, `loki`, `grafana`,
`otel-collector`, `billing-exporter`, `prompt-lang-exporter`,
`prompt-intent-exporter`, `web` — fires when `ContainerUp < 1` for 3 consecutive
minutes (rides through normal `docker-compose up -d` restarts). `TreatMissingData:
breaching`, so if the producer script or the whole box dies, the resulting data gap
also alarms. Source: `ClaudeAnalytics/Containers` `ContainerUp` (needs Deploy 3).

**Billing-exporter health (3):** the cost pipeline can fail *silently* — the
dashboard keeps showing a plausible-but-wrong number. These watch the signals from
Deploy 4 (`ClaudeAnalytics/Billing`):

| # | Alarm | Fires when | Missing data |
|---|-------|-----------|--------------|
| 14 | Billing exporter error | `ExporterErrors >= 1` for 3×5 min | breaching |
| 15 | Billing exporter stale | `StalenessSeconds > 86400` (no good poll in 24h; poll interval is 6h) | breaching |
| 16 | Billing silent $0 | `SilentZeroServiceCost >= 1` for 30 min — service cost reads $0 while real workspace spend exists (the failure from #15) | notBreaching |

All alarms route to the `claude-analytics-alerts` SNS topic on both ALARM and OK.
