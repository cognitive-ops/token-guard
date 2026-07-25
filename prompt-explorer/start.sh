#!/usr/bin/env bash
# Turn ON the local Prompt Explorer, pointed at a LOCAL Loki (no AWS/SSM):
#   1) check the local Loki (token-guard root docker-compose `loki` service) is reachable
#   2) start a local, localhost-only Grafana that loads only the Prompt Explorer dashboard
#
# Nothing here touches the shared grafana.claude-analytics server or AWS.
set -euo pipefail
cd "$(dirname "$0")" || exit 1

LOCAL_PORT="${LOKI_LOCAL_PORT:-3100}"

echo "==> Checking local Loki at localhost:$LOCAL_PORT ..."
if ! curl -sf --max-time 3 "http://localhost:$LOCAL_PORT/loki/api/v1/labels" >/dev/null 2>&1; then
  echo "ERROR: no Loki reachable at localhost:$LOCAL_PORT"
  echo "       Start it first from the repo root:  docker compose up -d loki"
  echo "       Then seed sample prompts:            python tools/seed-demo-data.py loki"
  exit 1
fi

echo "==> Starting local Grafana ..."
docker compose up -d

echo
echo "Prompt Explorer is UP:  http://localhost:3001   (anonymous admin)"
echo "Data source dropdown defaults to 'Loki (local)'."
echo "When done:              ./stop.sh"
