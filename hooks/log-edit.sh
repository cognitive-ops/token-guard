#!/usr/bin/env bash
# PostToolUse hook (matcher Edit|Write|MultiEdit): record a file Claude edited,
# tagged with session_id (partial AI-vs-human attribution signal).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib.sh"
read_input

fp="$(jq -r '.tool_input.file_path // empty' <<<"$HOOK_INPUT" 2>/dev/null || true)"
[ -z "$fp" ] && exit 0
sid="$(hook_field '.session_id')"
tool="$(hook_field '.tool_name')"

line="$(jq -nc --arg s "$sid" --arg fp "$fp" --arg t "$tool" \
  '{session_id:$s, file:$fp, tool:$t}')" || exit 0
push_event "edit" "$line"
exit 0
