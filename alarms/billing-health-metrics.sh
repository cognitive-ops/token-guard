#!/usr/bin/env bash
# Publish billing-exporter health signals to CloudWatch so the alarms in
# cloudformation.yaml can catch a stale or silently-wrong cost figure.
#
# Pairs with the 3 billing alarms (they only *watch* these metrics — this
# script *produces* them), mirroring the container-health-metrics.sh split.
#
# The exporter already emits health gauges to Prometheus; this reads them back
# and forwards to CloudWatch (Prometheus is internal-only, so we resolve the
# container IP from the host, per the repo's ops notes).
#
# Run every 5 min from the systemd timer:
#   billing-health-metrics.timer -> this script
#
# IAM: the instance role already grants cloudwatch:PutMetricData (same role the
# container-health producer uses) — no extra permissions needed.
set -uo pipefail

REGION="us-east-1"
NAMESPACE="ClaudeAnalytics/Billing"

# Staleness threshold is enforced by the CloudWatch alarm, not here — this
# script only reports the raw age in seconds.

# Instance id via IMDSv2.
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 120")
IID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/instance-id)

# Prometheus has no published host port; reach it by container IP.
PROM_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' prometheus 2>/dev/null)

# Run an instant PromQL query and print the scalar result (empty on any error).
promq() {
  local q="$1" out
  out=$(curl -s -G "http://${PROM_IP}:9090/api/v1/query" --data-urlencode "query=${q}" 2>/dev/null) || return 1
  printf '%s' "$out" | python3 -c '
import sys, json
try:
    r = json.load(sys.stdin)["data"]["result"]
    print(r[0]["value"][1] if r else "")
except Exception:
    print("")
'
}

# --- Read the three health signals ------------------------------------------
# 1 if the last poll failed, else 0 (missing -> empty -> treated as breaching by
# the alarm's missing-data policy).
errors=$(promq 'claude_billing_exporter_errors')

# Age in seconds since the last successful poll.
staleness=$(promq 'time() - claude_billing_exporter_last_success_timestamp')

# Silent-$0: service cost reads 0 while real workspace spend exists. Compute the
# boolean here so the alarm is a simple >= 1 threshold.
svc=$(promq 'claude_service_billed_cost_total_usd')
ws=$(promq 'sum(claude_workspace_billed_cost_usd)')
silent_zero=$(python3 -c '
import sys
svc, ws = sys.argv[1], sys.argv[2]
try:
    print(1 if float(svc) == 0 and float(ws) > 0 else 0)
except ValueError:
    print("")   # missing data -> let the alarm decide
' "$svc" "$ws")

uncategorized=$(promq 'claude_uncategorized_workspace_count')

# --- Publish (skip any signal we could not read, so a transient Prometheus
# blip becomes a data gap the alarm can treat, not a bogus 0) ----------------
items=()
add() { [ -n "$2" ] && items+=("{\"MetricName\":\"$1\",\"Dimensions\":[{\"Name\":\"InstanceId\",\"Value\":\"$IID\"}],\"Value\":$2,\"Unit\":\"$3\"}"); }
add ExporterErrors          "$errors"        "Count"
add StalenessSeconds        "$staleness"     "Seconds"
add SilentZeroServiceCost   "$silent_zero"   "Count"
add UncategorizedWorkspaces "$uncategorized" "Count"

if [ ${#items[@]} -eq 0 ]; then
  echo "no billing health signals available (Prometheus unreachable?)" >&2
  exit 0
fi

IFS=,; METRIC_JSON="[${items[*]}]"; unset IFS

aws cloudwatch put-metric-data \
  --region "$REGION" \
  --namespace "$NAMESPACE" \
  --metric-data "$METRIC_JSON"
