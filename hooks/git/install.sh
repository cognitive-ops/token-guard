#!/usr/bin/env bash
# Install the native post-commit hook into the current git repo, without disrupting
# any existing post-commit hook (it gets chained, not replaced).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/post-commit"
HOOKDIR="$(git rev-parse --git-path hooks 2>/dev/null)" || { echo "Not a git repository." >&2; exit 1; }
mkdir -p "$HOOKDIR"
TARGET="$HOOKDIR/post-commit"
MARKER="claude-code-roi-analytics post-commit shim"

if [ -e "$TARGET" ] && ! grep -q "$MARKER" "$TARGET" 2>/dev/null; then
  mv "$TARGET" "$TARGET.local"
  echo "Preserved existing hook → $(basename "$TARGET").local (it will still run)."
fi

cat > "$TARGET" <<EOF
#!/usr/bin/env bash
# $MARKER — do not edit; regenerate via hooks/git/install.sh
[ -x "$TARGET.local" ] && "$TARGET.local" "\$@"   # chain any pre-existing hook first
"$SRC" "\$@"
exit 0
EOF
chmod +x "$TARGET"

echo "Installed post-commit → $SRC"
echo "Set CLAUDE_HOOK_LOKI_URL (and CLAUDE_HOOK_LOKI_AUTH if needed) in your environment."
if git config --get core.hooksPath >/dev/null 2>&1; then
  echo "WARNING: core.hooksPath is set ($(git config --get core.hooksPath)); git may use that"
  echo "         dir instead of $HOOKDIR. Install there, or unset core.hooksPath."
fi
