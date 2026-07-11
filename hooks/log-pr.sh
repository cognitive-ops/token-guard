#!/usr/bin/env bash
# PostToolUse hook (matcher Bash, if Bash(gh pr create *)): record a PR creation
# tagged with session_id, so prompts/PR can be computed.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib.sh"
read_input

cmd="$(hook_field '.tool_input.command')"
case "$cmd" in *"gh pr create"*) : ;; *) exit 0 ;; esac

sid="$(hook_field '.session_id')"
cwd="$(hook_field '.cwd')"
# best-effort PR URL from the tool result, if present
pr_url="$(jq -r '.tool_result.output // .tool_result // ""' <<<"$HOOK_INPUT" 2>/dev/null \
  | grep -oE 'https://[^ ]*/pull/[0-9]+' | head -1 || true)"

line="$(jq -nc --arg s "$sid" --arg cwd "$cwd" --arg url "$pr_url" \
  '{session_id:$s, cwd:$cwd, pr_url:$url}')" || exit 0
push_event "pr" "$line"
exit 0
