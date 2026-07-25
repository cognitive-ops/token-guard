#!/usr/bin/env bash
# Pipe ONLINE production data into the local Grafana (localhost:3000), resiliently.
#
#   online Loki       -> host 127.0.0.1:3200  -> relay $RELAY_BIND:3201
#   online Prometheus -> host 127.0.0.1:3202  -> relay $RELAY_BIND:3203
# docker-compose.override.yml points Grafana's datasources at :3201 / :3203.
#
# SSM port-forward sessions drop periodically (idle/network). This script is a
# WATCHDOG: it re-establishes any tunnel or the relay within seconds of it dropping.
# Run it in a terminal and leave it open; Ctrl-C tears everything down.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
PROFILE="${AWS_PROFILE:-your-aws-profile}"
INSTANCE="${SSM_INSTANCE:-<EC2_INSTANCE_ID>}"

# The relay carries production Loki (raw user prompts) + Prometheus with NO auth, so it
# must bind a PRIVATE interface the Grafana container can reach but the LAN cannot, never 0.0.0.0.
if [ -n "${RELAY_BIND:-}" ]; then
  :
elif [ "$(uname -s)" = "Darwin" ]; then
  RELAY_BIND="127.0.0.1"
else
  RELAY_BIND="$(docker network inspect bridge -f '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null)"
  RELAY_BIND="${RELAY_BIND:-127.0.0.1}"
fi
export RELAY_BIND

command -v session-manager-plugin >/dev/null || { echo "ERROR: session-manager-plugin not installed"; exit 1; }

resolve() { # $1 container -> IP on the docker network
  local cid st
  cid=$(aws ssm send-command --profile "$PROFILE" --instance-ids "$INSTANCE" \
    --document-name AWS-RunShellScript \
    --parameters "commands=[\"docker inspect $1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}'\"]" \
    --query Command.CommandId --output text 2>/dev/null) || return 1
  for _ in $(seq 1 15); do
    st=$(aws ssm get-command-invocation --profile "$PROFILE" --command-id "$cid" --instance-id "$INSTANCE" --query Status --output text 2>/dev/null || true)
    [ "$st" = Success ] || [ "$st" = Failed ] && break; sleep 2
  done
  aws ssm get-command-invocation --profile "$PROFILE" --command-id "$cid" --instance-id "$INSTANCE" \
    --query StandardOutputContent --output text 2>/dev/null | tr -d '\n' | awk '{print $1}'
}

listening() { ss -ltn 2>/dev/null | grep -q "127.0.0.1:$1"; }

start_tunnel() { # $1 container  $2 remote_port  $3 local_port
  local ip; ip=$(resolve "$1")
  [ -n "$ip" ] || { echo "  ! could not resolve $1"; return 1; }
  echo "  + tunnel $1($ip):$2 -> 127.0.0.1:$3"
  nohup aws ssm start-session --profile "$PROFILE" --target "$INSTANCE" \
    --document-name AWS-StartPortForwardingSessionToRemoteHost \
    --parameters "{\"host\":[\"$ip\"],\"portNumber\":[\"$2\"],\"localPortNumber\":[\"$3\"]}" \
    >/dev/null 2>&1 &
}

cleanup() {
  echo; echo "stopping tunnels + relay ..."
  pkill -f "online-relay.py" 2>/dev/null || true
  pkill -f "AWS-StartPortForwardingSessionToRemoteHost" 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

echo "Starting resilient online pipe (Ctrl-C to stop). Grafana: http://localhost:3000"
while true; do
  listening 3200 || start_tunnel loki 3100 3200
  listening 3202 || start_tunnel prometheus 9090 3202
  if ! pgrep -f "online-relay.py" >/dev/null; then
    echo "  + relay ${RELAY_BIND}:3201->3200, ${RELAY_BIND}:3203->3202"
    nohup python3 online-relay.py >/tmp/online-relay.log 2>&1 &
  fi
  sleep 15
done
