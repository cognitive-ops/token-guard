"""Load the raw corpus, filter non-prompts, and reconstruct session context.

- Drops harness-injected blocks (not user-written).
- Routes slash-commands and bare confirmations to a `control` bucket (no LLM).
- Returns real developer prompts, each with its prior in-session prompts attached
  (ordered by event_sequence) so the labeler can judge sequence-level behaviors.
"""

import json
import re
from collections import defaultdict

RAW = "data/prompts_raw.jsonl"

_INJECTED = (
    "<observed_from_primary_session>",
    "<task-notification>",
    "<system-reminder>",
    "<command-",
)
_CONFIRM = re.compile(
    r"^(y|yes|yep|yeah|ok|okay|sure|no|nope|continue|go|go ahead|do it|proceed|next|stop|"
    r"thanks|thank you|ty|y post|yes post|\d+)\b",
    re.I,
)


_SLASH = re.compile(r"^/([a-zA-Z][\w-]*)")


def extract_command(prompt: str):
    """Slash-command name for a control prompt, else None. Pure regex, no LLM.

    These are first-class usage signals: /plan = planning discipline,
    /verify = verification discipline, /clear = context management.
    """
    m = _SLASH.match((prompt or "").strip())
    return m.group(1).lower() if m else None


def categorize(prompt: str) -> str:
    s = (prompt or "").strip()
    if not s:
        return "empty"
    if s.startswith(_INJECTED):
        return "injected"
    if re.match(r"^/[a-zA-Z]", s):
        return "control"  # slash command
    if len(s) < 15 and _CONFIRM.match(s):
        return "control"  # confirmation / continuation
    return "real"


def load_rows():
    with open(RAW) as f:
        return [json.loads(line) for line in f]


def sessions_in_order(rows):
    """Group rows by session_id, sorted by event_sequence (fallback ts_ns)."""
    by_sess = defaultdict(list)
    for r in rows:
        by_sess[r.get("session_id")].append(r)

    def seq(r):
        try:
            return int(r.get("event_sequence") or 0)
        except (TypeError, ValueError):
            return 0

    for sid in by_sess:
        by_sess[sid].sort(key=lambda r: (seq(r), r.get("ts_ns", 0)))
    return by_sess


def real_prompts_with_context(rows=None):
    """Yield dicts for every REAL prompt, with prior in-session prompt texts.

    prior_prompts includes earlier REAL prompts AND confirmations (they carry
    'still broken' / 'again' signal), but not injected blocks.
    """
    rows = rows if rows is not None else load_rows()
    by_sess = sessions_in_order(rows)
    out = []
    for sid, seq_rows in by_sess.items():
        history = []  # texts of prior non-injected prompts in this session
        for r in seq_rows:
            cat = categorize(r.get("prompt"))
            if cat == "injected" or cat == "empty":
                continue
            if cat == "real":
                out.append(
                    {
                        "prompt_id": r.get("prompt_id"),
                        "session_id": sid,
                        "user_email": r.get("user_email"),
                        "prompt": (r.get("prompt") or "").strip(),
                        "prior_prompts": list(history),
                        "ts_ns": r.get("ts_ns"),
                        "prompt_length": r.get("prompt_length"),
                    }
                )
            # both real prompts and confirmations become history for later prompts
            history.append((r.get("prompt") or "").strip())
    return out


if __name__ == "__main__":
    rows = load_rows()
    from collections import Counter

    cats = Counter(categorize(r.get("prompt")) for r in rows)
    real = real_prompts_with_context(rows)
    with_ctx = sum(1 for r in real if r["prior_prompts"])
    print("categories:", dict(cats))
    print(f"real prompts with context attached: {len(real)} ({with_ctx} have >=1 prior prompt)")
