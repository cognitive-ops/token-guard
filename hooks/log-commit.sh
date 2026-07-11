#!/usr/bin/env bash
# PostToolUse hook (matcher Bash, if Bash(git commit *)): capture the resulting
# commit SHA + session_id + repo, so commits can be linked to Claude sessions.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib.sh"
read_input

cmd="$(hook_field '.tool_input.command')"
case "$cmd" in *"git commit"*) : ;; *) exit 0 ;; esac   # safety: only real git commits

cwd="$(hook_field '.cwd')"; [ -z "$cwd" ] && cwd="."
sid="$(hook_field '.session_id')"
sha="$(git -C "$cwd" rev-parse HEAD 2>/dev/null || true)"
[ -z "$sha" ] && exit 0   # commit may have failed; nothing to record
repo="$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null | xargs -r basename || true)"

line="$(jq -nc --arg s "$sid" --arg sha "$sha" --arg cwd "$cwd" --arg repo "$repo" \
  '{session_id:$s, commit_sha:$sha, cwd:$cwd, repo:$repo}')" || exit 0
push_event "commit" "$line"
exit 0
