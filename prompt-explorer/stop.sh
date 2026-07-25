#!/usr/bin/env bash
# Turn OFF the local Prompt Explorer.
set -uo pipefail
cd "$(dirname "$0")" || exit 1

echo "==> Stopping local Grafana ..."
docker compose down

echo "Prompt Explorer is DOWN. Prompt text is no longer reachable locally."
