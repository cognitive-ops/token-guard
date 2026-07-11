#!/usr/bin/env python3
"""Accuracy check: label the gold prompts with a variant and compare vs the gold
set (intent agreement + per-behavior precision/recall, gold = truth).

    python src/eval_accuracy.py        # label gold prompts (1/call) + score

Config (env): LABELER_MODEL (claude-sonnet-5), LABELER_VARIANT (v2),
LABELER_EFFORT (low), LABELER_THINKING (off|adaptive), GOLD (data/gold.jsonl),
ITEMS (data/label_items.jsonl — carries prompt text/context for gold ids),
EVAL_DIR (data/eval), WORKERS (10). Needs ANTHROPIC_API_KEY.

Note: if the gold was labeled under a different rubric than the variant, intent
is the clean signal and behavior P/R is looser (rubric mismatch).
"""

import json
import os
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anthropic  # noqa: E402
import label_prompts  # noqa: E402
import taxonomy  # noqa: E402

GOLD = os.environ.get("GOLD", "data/gold.jsonl")
ITEMS = os.environ.get("ITEMS", "data/label_items.jsonl")
EVAL_DIR = os.environ.get("EVAL_DIR", "data/eval")
MODEL = os.environ.get("LABELER_MODEL", "claude-sonnet-5")
VARIANT = os.environ.get("LABELER_VARIANT", "v2")
EFFORT = os.environ.get("LABELER_EFFORT", "low")
THINKING = os.environ.get("LABELER_THINKING", "off")
WORKERS = int(os.environ.get("WORKERS", "10"))
CKPT = os.path.join(EVAL_DIR, f"accuracy_{VARIANT}.jsonl")
SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": taxonomy.INTENTS},
        "behaviors": {"type": "array", "items": {"type": "string", "enum": taxonomy.BEHAVIORS}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["intent", "behaviors", "confidence"],
    "additionalProperties": False,
}
lock = threading.Lock()


def run_and_score():
    os.makedirs(EVAL_DIR, exist_ok=True)
    system, extra, replace = label_prompts.resolve(VARIANT)
    gold = {json.loads(l)["prompt_id"]: json.loads(l) for l in open(GOLD)}
    items = {}
    for l in open(ITEMS):
        d = json.loads(l)
        if d.get("prompt_id") in gold:
            items[d["prompt_id"]] = d
    ids = [p for p in gold if p in items]
    print(f"gold={len(gold)} matched_with_text={len(ids)}")
    fs = (
        taxonomy.fewshot_messages()
        if not replace
        else [
            m
            for ex in extra
            for m in (
                {
                    "role": "user",
                    "content": taxonomy.build_user_content(ex["prompt"], ex.get("prior", [])),
                },
                {"role": "assistant", "content": json.dumps(ex["label"])},
            )
        ]
    )
    client = anthropic.Anthropic()
    open(CKPT, "w").close()

    def job(pid):
        it = items[pid]
        try:
            kw = {
                "model": MODEL,
                "max_tokens": 400,
                "system": system,
                "messages": fs
                + [
                    {
                        "role": "user",
                        "content": taxonomy.build_user_content(
                            it["prompt"], it.get("prior_prompts", [])
                        ),
                    }
                ],
                "output_config": {
                    "effort": EFFORT,
                    "format": {"type": "json_schema", "schema": SCHEMA},
                },
            }
            if THINKING == "off":
                kw["thinking"] = {"type": "disabled"}
            r = client.messages.create(**kw)
            lab = json.loads(next(b.text for b in r.content if b.type == "text"))
            return {"prompt_id": pid, "intent": lab["intent"], "behaviors": lab["behaviors"]}
        except Exception as e:
            return {"prompt_id": pid, "_error": str(e)[:120]}

    with ThreadPoolExecutor(max_workers=WORKERS) as ex, open(CKPT, "a") as ck:
        for fut in as_completed([ex.submit(job, p) for p in ids]):
            with lock:
                ck.write(json.dumps(fut.result(), ensure_ascii=False) + "\n")
    pred = {}
    for l in open(CKPT):
        r = json.loads(l)
        if not r.get("_error"):
            pred[r["prompt_id"]] = r
    ids = [i for i in gold if i in pred]
    agree = sum(1 for i in ids if gold[i]["intent"] == pred[i]["intent"])
    print(
        f"\nINTENT agreement ({VARIANT} vs gold): {agree}/{len(ids)} = {100 * agree / len(ids):.1f}%"
    )
    conf = Counter((gold[i]["intent"], pred[i]["intent"]) for i in ids)
    for (g, s), c in conf.most_common():
        if g != s and c >= 2:
            print(f"    {g:11s} -> {s:11s} : {c}")
    print("BEHAVIOR precision/recall (gold=truth):")
    for b in taxonomy.BEHAVIORS:
        tp = sum(1 for i in ids if b in gold[i]["behaviors"] and b in pred[i]["behaviors"])
        fp = sum(1 for i in ids if b not in gold[i]["behaviors"] and b in pred[i]["behaviors"])
        fn = sum(1 for i in ids if b in gold[i]["behaviors"] and b not in pred[i]["behaviors"])
        P = tp / (tp + fp) if tp + fp else float("nan")
        R = tp / (tp + fn) if tp + fn else float("nan")
        print(f"  {b:16s} P={P:.2f} R={R:.2f} (gold_pos={tp + fn})")


if __name__ == "__main__":
    run_and_score()
