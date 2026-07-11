#!/usr/bin/env bash
# Publish a ContainerUp (1/0) metric per expected container to CloudWatch.
# Pairs with the per-container alarms in cloudformation.yaml (the alarms only
# *watch* this metric — this script *produces* it), mirroring the agent/alarms
# split used for the host metrics.
#
# Run every minute from cron:
#   * * * * * /home/ec2-user/claude-analytics/alarms/container-health-metrics.sh >> /var/log/container-health.log 2>&1
#
# IAM: the instance role (claude-analytics-cwagent-role / CloudWatchAgentServerPolicy)
# already grants cloudwatch:PutMetricData — no extra permissions needed.
set -uo pipefail

REGION="us-east-1"
NAMESPACE="ClaudeAnalytics/Containers"

# Instance id via IMDSv2.
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 120")
IID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/instance-id)

# Logical name (alarm/metric dimension) -> actual docker container name.
# Keep in sync with the alarms in cloudformation.yaml.
declare -A CONTAINERS=(
  [prometheus]=prometheus
  [loki]=loki
  [grafana]=grafana
  [otel-collector]=claude-analytics-otel-collector-1
  [billing-exporter]=billing-exporter
  [prompt-lang-exporter]=prompt-lang-exporter
  [prompt-intent-exporter]=prompt-intent-exporter
  [web]=claude-roi-web
)

# Build one PutMetricData batch. We emit an explicit 0 for any expected container
# that is stopped, missing, or unhealthy, so "down" reads as 0 rather than as a
# missing-data gap (the alarms treat genuine gaps — script/box dead — as breaching).
items=()
for logical in "${!CONTAINERS[@]}"; do
  cname="${CONTAINERS[$logical]}"
  state=$(docker inspect -f '{{.State.Running}}{{if .State.Health}}:{{.State.Health.Status}}{{end}}' "$cname" 2>/dev/null)
  case "$state" in
    true|true:healthy|true:starting) up=1 ;;   # running (healthcheck ok or still warming up)
    *)                                up=0 ;;   # stopped, unhealthy, or not found
  esac
  items+=("{\"MetricName\":\"ContainerUp\",\"Dimensions\":[{\"Name\":\"InstanceId\",\"Value\":\"$IID\"},{\"Name\":\"Container\",\"Value\":\"$logical\"}],\"Value\":$up,\"Unit\":\"Count\"}")
done

IFS=,; METRIC_JSON="[${items[*]}]"; unset IFS

aws cloudwatch put-metric-data \
  --region "$REGION" \
  --namespace "$NAMESPACE" \
  --metric-data "$METRIC_JSON"
