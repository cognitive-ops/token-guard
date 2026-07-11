#!/usr/bin/env bash
# Turn OFF the local Prompt Explorer: stop Grafana and close the SSM tunnel.
set -uo pipefail
cd "$(dirname "$0")" || exit 1

echo "==> Stopping local Grafana ..."
docker compose down

if [ -f .tunnel.pid ]; then
  PID="$(cat .tunnel.pid)"
  echo "==> Closing SSM tunnel (pid $PID) ..."
  kill "$PID" 2>/dev/null || true
  rm -f .tunnel.pid
fi
# Belt-and-suspenders: clean any stray plugin process holding the local port.
pkill -f "session-manager-plugin" 2>/dev/null || true

echo "Prompt Explorer is DOWN. Prompt text is no longer reachable locally."
