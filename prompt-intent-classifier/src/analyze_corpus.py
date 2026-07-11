#!/usr/bin/env python3
"""Profile the raw prompt corpus before we design labels.

Answers: how long are prompts, how many per user/session, how big are sessions
(matters for sequence-level tags), what do prompts at each length look like, and
some cheap heuristic intent signals to sanity-check the taxonomy against reality.
"""

import json
import re
import statistics
from collections import Counter, defaultdict

RAW = "data/prompts_raw.jsonl"


def load():
    rows = []
    with open(RAW) as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def pct(vals, p):
    vals = sorted(vals)
    if not vals:
        return 0
    k = int(round((len(vals) - 1) * p / 100))
    return vals[k]


HEURISTICS = {
    "debug": r"\b(error|fix|bug|broken|fail|crash|not work|doesn'?t work|exception|traceback|why is|debug)\b",
    "understand": r"\b(how (does|do|is)|what (is|does|are)|where (is|does)|explain|understand|why does|check if|is it|does it)\b",
    "feature": r"\b(add|create|implement|build|make|write|new |support for|generate)\b",
    "refactor": r"\b(refactor|clean ?up|rename|move|extract|simplify|reorganize|restructure)\b",
    "test": r"\b(test|unit test|coverage|pytest|jest|spec|assert)\b",
    "ops": r"\b(deploy|docker|ci|pipeline|build|env|config|kubernetes|k8s|nginx|compose|workflow)\b",
    "review": r"\b(review|look at|check the|pr #|pull request|comments before)\b",
}


def main():
    rows = load()
    n = len(rows)
    lens = []
    for r in rows:
        try:
            lens.append(int(r.get("prompt_length") or len(r.get("prompt") or "")))
        except (TypeError, ValueError):
            lens.append(len(r.get("prompt") or ""))

    print(f"=== CORPUS: {n} prompts ===\n")
    print("Prompt length (chars):")
    print(
        f"  min={min(lens)} p10={pct(lens, 10)} p25={pct(lens, 25)} median={pct(lens, 50)} "
        f"p75={pct(lens, 75)} p90={pct(lens, 90)} p99={pct(lens, 99)} max={max(lens)} mean={statistics.mean(lens):.0f}"
    )

    buckets = Counter()
    for L in lens:
        if L < 15:
            buckets["<15 (ultra-short)"] += 1
        elif L < 40:
            buckets["15-39 (short)"] += 1
        elif L < 120:
            buckets["40-119 (medium)"] += 1
        elif L < 400:
            buckets["120-399 (long)"] += 1
        else:
            buckets["400+ (very long)"] += 1
    print("\nLength buckets:")
    for k in [
        "<15 (ultra-short)",
        "15-39 (short)",
        "40-119 (medium)",
        "120-399 (long)",
        "400+ (very long)",
    ]:
        print(f"  {k:22s} {buckets[k]:6d}  ({100 * buckets[k] / n:.1f}%)")

    users = Counter(r.get("user_email") or "unknown" for r in rows)
    print(f"\nUsers: {len(users)} distinct")
    print("  top 10 by prompt volume:")
    for u, c in users.most_common(10):
        print(f"    {c:5d}  {u}")
    uvals = list(users.values())
    print(f"  per-user volume: median={pct(uvals, 50)} p90={pct(uvals, 90)} max={max(uvals)}")

    sess = defaultdict(int)
    for r in rows:
        sess[r.get("session_id")] += 1
    svals = list(sess.values())
    print(f"\nSessions: {len(sess)} distinct")
    print(
        f"  prompts/session: median={pct(svals, 50)} p75={pct(svals, 75)} p90={pct(svals, 90)} max={max(svals)}"
    )
    multi = sum(1 for v in svals if v >= 2)
    print(
        f"  sessions with >=2 prompts: {multi} ({100 * multi / len(sess):.1f}%)  "
        f"<- sequence-level tags (stuck/scope) apply here"
    )

    print("\nHeuristic intent hits (regex, non-exclusive — sanity check only):")
    hits = Counter()
    for r in rows:
        p = (r.get("prompt") or "").lower()
        for intent, pat in HEURISTICS.items():
            if re.search(pat, p):
                hits[intent] += 1
    for intent, c in hits.most_common():
        print(f"  {intent:12s} {c:6d}  ({100 * c / n:.1f}%)")

    # non-ascii (language signal)
    nonascii = sum(1 for r in rows if any(ord(ch) > 127 for ch in (r.get("prompt") or "")))
    print(f"\nPrompts with non-ASCII chars: {nonascii} ({100 * nonascii / n:.1f}%)")

    print("\n=== SAMPLES BY LENGTH BUCKET ===")
    for lo, hi, name in [
        (0, 15, "ultra-short"),
        (15, 40, "short"),
        (40, 120, "medium"),
        (120, 400, "long"),
        (400, 10**9, "very-long"),
    ]:
        sel = [r for r, L in zip(rows, lens, strict=False) if lo <= L < hi]
        print(f"\n--- {name} ({lo}-{hi}) : {len(sel)} prompts, 8 samples ---")
        step = max(1, len(sel) // 8)
        for r in sel[::step][:8]:
            p = (r.get("prompt") or "").replace("\n", " ")
            print(f"  [{r.get('prompt_length'):>4}] {p[:140]}")


if __name__ == "__main__":
    main()
