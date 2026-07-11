#!/usr/bin/env python3
"""Stage 2 (clean): merge raw prompt dumps -> a clean, deduped labelable set.

Reads every JSONL in RAW_DIR (the Loki pull + any restored backups), merges &
dedups by prompt_id, drops rows with scrambled Loki labels, keeps only "real"
prompts (routes out injected blocks / slash-commands / confirmations) with prior
in-session context, strips noise (punctuation-only, <3 chars, multilingual
confirmations), and dedups by (normalized text + prior context).

OUTPUT MAY STILL CONTAIN SECRETS -> feeds scrub_secrets.py. This artifact is
marked `cache: false` in dvc.yaml and must never reach a DVC remote.
"""

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from preprocess import real_prompts_with_context  # noqa: E402

RAW_DIR = os.environ.get("RAW_DIR", "data/raw")
OUT = os.environ.get("CLEAN_OUT", "data/interim/clean.jsonl")

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
_ALNUM = re.compile(r"[0-9A-Za-zÀ-￿]")
# high-confidence multilingual confirmations / greetings (exact, casefolded)
_CONFIRM = {
    "oui",
    "non",
    "si",
    "sí",
    "ja",
    "nein",
    "да",
    "нет",
    "давай",
    "ок",
    "ok",
    "sim",
    "não",
    "ага",
    "угу",
    "yep",
    "nope",
    "voila",
    "voilà",
    "merci",
    "gracias",
    "spasibo",
    "спасибо",
    "claro",
    "oké",
    "okay",
    "d'accord",
    "daccord",
}


def _junk_key(k):
    return k.startswith(("key_", "toolu_", "_")) or k in {"arm64", "SessionStart_clear"}


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def _is_noise(t):
    if not _ALNUM.search(t):
        return True  # punctuation / symbols only
    if len(t) < 3:
        return True  # single/double-char tokens
    return t.casefold() in _CONFIRM


def load_merged():
    by = {}
    for path in sorted(glob.glob(os.path.join(RAW_DIR, "*.jsonl"))):
        with open(path) as f:
            for line in f:
                d = json.loads(line)
                for k in list(d):
                    if _junk_key(k):
                        d.pop(k)  # drop scrambled-stream junk labels
                pid = d.get("prompt_id")
                if not pid:
                    continue
                if pid not in by or len(d) > len(by[pid]):
                    by[pid] = d  # prefer the richer-metadata copy
    # drop scrambled rows (event_timestamp not a real ISO timestamp)
    return [
        d
        for d in by.values()
        if isinstance(d.get("event_timestamp"), str)
        and _ISO.match(d["event_timestamp"])
        and isinstance(d.get("prompt"), str)
    ]


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rows = load_merged()
    real = real_prompts_with_context(rows=rows)
    seen, out, n_noise, n_dup = set(), [], 0, 0
    for it in real:
        t = _norm(it["prompt"])
        if _is_noise(t):
            n_noise += 1
            continue
        key = (t, tuple(_norm(p) for p in it["prior_prompts"][-5:]))
        if key in seen:
            n_dup += 1
            continue
        seen.add(key)
        it["prior_prompts"] = it["prior_prompts"][-5:]  # trim history bloat (label uses last 5)
        out.append(it)
    with open(OUT, "w") as f:
        for it in out:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(
        f"merged_rows={len(rows)} real={len(real)} noise-={n_noise} dup-={n_dup} "
        f"-> {len(out)} clean -> {OUT}"
    )


if __name__ == "__main__":
    main()
