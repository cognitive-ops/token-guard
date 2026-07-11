#!/usr/bin/env bash
# UserPromptSubmit hook: record that a prompt happened, tagged with session_id.
# Includes the full prompt text (opt-in change — Loki then holds raw prompt
# content permanently; make sure that's acceptable before deploying fleet-wide).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib.sh"
read_input
line="$(jq -c '{session_id, cwd, prompt: (.prompt // ""), prompt_length: ((.prompt // "") | length)}' <<<"$HOOK_INPUT" 2>/dev/null)" || exit 0
[ -z "$line" ] && exit 0
push_event "prompt" "$line"
exit 0
