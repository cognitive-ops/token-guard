#!/usr/bin/env bash
# SessionEnd hook: mark the end of a session (boundary for per-session rollups).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib.sh"
read_input
line="$(jq -c '{session_id, cwd, reason: (.reason // .source // "")}' <<<"$HOOK_INPUT" 2>/dev/null)" || exit 0
[ -z "$line" ] && exit 0
push_event "session_end" "$line"
exit 0
