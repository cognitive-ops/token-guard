#!/usr/bin/env bash
# UserPromptSubmit hook: record that a prompt happened (count + length only — NOT
# the prompt text, to avoid storing sensitive content here), tagged with session_id.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib.sh"
read_input
line="$(jq -c '{session_id, cwd, prompt_length: ((.prompt // "") | length)}' <<<"$HOOK_INPUT" 2>/dev/null)" || exit 0
[ -z "$line" ] && exit 0
push_event "prompt" "$line"
exit 0
