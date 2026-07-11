#!/usr/bin/env bash
# Shared helper for Claude Code metric hooks -> Loki.
#
# Hooks push one structured event per occurrence to Loki (high-cardinality,
# event-shaped data — the right fit, vs. a Prometheus Pushgateway which would
# explode on session_id/commit-SHA labels). Grafana derives metrics with LogQL.
#
# Config via env (set in .claude/settings.json "env" or managed settings):
#   CLAUDE_HOOK_LOKI_URL   Loki base URL          (default http://localhost:3100)
#   CLAUDE_HOOK_LOKI_AUTH  optional auth header   (e.g. "Bearer <token>")
#   CLAUDE_HOOK_DRY_RUN    "1" -> print payload instead of sending (for testing)

push_event() {
  local event="$1" line="$2"
  local url="${CLAUDE_HOOK_LOKI_URL:-http://localhost:3100}"
  # Nanosecond, UNIQUE timestamp (Loki dedupes identical ts+line pairs, which would
  # undercount rapid same-content events). GNU date has %N; on BSD/macOS it doesn't,
  # so fall back to seconds + a random ns component.
  local ts; ts="$(date +%s%N 2>/dev/null)"
  case "$ts" in
    *[!0-9]*|"") ts="$(date +%s)$(printf '%09d' "$(( (RANDOM*32768 + RANDOM) % 1000000000 ))")" ;;
  esac
  local payload
  payload="$(jq -nc --arg ev "$event" --arg ts "$ts" --arg line "$line" \
    '{streams:[{stream:{service_name:"claude-code-hooks",event:$ev},values:[[$ts,$line]]}]}')" || return 0

  if [ "${CLAUDE_HOOK_DRY_RUN:-0}" = "1" ]; then
    printf '%s\n' "$payload"
    return 0
  fi

  local auth=()
  [ -n "${CLAUDE_HOOK_LOKI_AUTH:-}" ] && auth=(-H "Authorization: ${CLAUDE_HOOK_LOKI_AUTH}")

  if [ "${CLAUDE_HOOK_SYNC:-0}" = "1" ]; then
    # Synchronous: reliable delivery (waits for the push), bounded by --max-time so
    # an unreachable Loki can't hang the session beyond a few seconds.
    curl -sS --max-time 3 -H "Content-Type: application/json" "${auth[@]}" \
      -X POST "${url}/loki/api/v1/push" --data-binary "$payload" >/dev/null 2>&1
  else
    # Default: fire-and-forget so a slow/unreachable Loki never blocks the session.
    # Best-effort — events are dropped silently if Loki is down. Set CLAUDE_HOOK_SYNC=1
    # if you need guaranteed delivery and can tolerate up to a few seconds per hook.
    ( setsid curl -sS --max-time 3 -H "Content-Type: application/json" "${auth[@]}" \
        -X POST "${url}/loki/api/v1/push" --data-binary "$payload" >/dev/null 2>&1 & ) >/dev/null 2>&1
  fi
  return 0
}

# Read all of stdin into $HOOK_INPUT (the hook payload JSON).
read_input() { HOOK_INPUT="$(cat)"; }

# jq query against the hook payload; never fails the hook.
hook_field() { jq -r "$1 // \"\"" <<<"$HOOK_INPUT" 2>/dev/null || true; }
