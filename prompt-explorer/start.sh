#!/usr/bin/env bash
# Turn ON the local Prompt Explorer:
#   1) open an SSM port-forward to the Loki container (localhost:3100)
#   2) start a local, localhost-only Grafana that loads only the Prompt Explorer dashboard
#
# Nothing here touches the shared grafana.claude-analytics server.
set -euo pipefail
cd "$(dirname "$0")" || exit 1

PROFILE="${AWS_PROFILE:-scopic-ml-development}"
INSTANCE="${SSM_INSTANCE:-i-0fe9d2092e0ab25cd}"
LOCAL_PORT="${LOKI_LOCAL_PORT:-3100}"

command -v session-manager-plugin >/dev/null || { echo "ERROR: session-manager-plugin not installed"; exit 1; }

echo "==> Resolving Loki container IP on $INSTANCE ..."
CID=$(aws ssm send-command --profile "$PROFILE" --instance-ids "$INSTANCE" \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["docker inspect loki --format \"{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}\""]' \
  --query "Command.CommandId" --output text)
for _ in $(seq 1 15); do
  ST=$(aws ssm get-command-invocation --profile "$PROFILE" --command-id "$CID" --instance-id "$INSTANCE" --query Status --output text 2>/dev/null || true)
  [ "$ST" = "Success" ] || [ "$ST" = "Failed" ] && break; sleep 2
done
LOKI_IP=$(aws ssm get-command-invocation --profile "$PROFILE" --command-id "$CID" --instance-id "$INSTANCE" --query StandardOutputContent --output text | tr -d '\n' | awk '{print $1}')
[ -n "$LOKI_IP" ] || { echo "ERROR: could not resolve Loki IP"; exit 1; }
echo "    Loki at $LOKI_IP:3100"

echo "==> Opening SSM port-forward localhost:$LOCAL_PORT -> $LOKI_IP:3100 ..."
nohup aws ssm start-session --profile "$PROFILE" --target "$INSTANCE" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$LOKI_IP\"],\"portNumber\":[\"3100\"],\"localPortNumber\":[\"$LOCAL_PORT\"]}" \
  >/tmp/prompt-explorer-tunnel.log 2>&1 &
echo $! > .tunnel.pid

echo "==> Waiting for the tunnel ..."
for _ in $(seq 1 20); do
  curl -sf --max-time 3 "http://localhost:$LOCAL_PORT/loki/api/v1/labels" >/dev/null 2>&1 && break; sleep 1
done

echo "==> Starting local Grafana ..."
docker compose up -d

echo
echo "Prompt Explorer is UP:  http://localhost:3001   (anonymous admin)"
echo "When done:              ./stop.sh"
