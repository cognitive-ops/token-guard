"""Opus gold set: independently label a stratified ~200-prompt subset with Opus,
to measure how good Sonnet's labels are (the dataset-quality number).

Samples from the exact prompts submitted in the Sonnet batch (data/label_items.jsonl)
so the comparison is apples-to-apples on the same prompt_ids.

Usage:
  python src/gold_set.py label     # Opus-label the sample -> data/gold.jsonl
  python src/gold_set.py compare    # compare gold vs data/labeled.jsonl (needs batch fetched)
"""

import json
import os
import sys
from collections import Counter, defaultdict

import anthropic

sys.path.insert(0, os.path.dirname(__file__))
import taxonomy

ITEMS_FILE = "data/label_items.jsonl"
GOLD = "data/gold.jsonl"
LABELED = "data/labeled.jsonl"
MODEL = "claude-opus-4-8"
N = int(os.environ.get("GOLD_N", "200"))


def load_items():
    return [json.loads(l) for l in open(ITEMS_FILE)]


def stratified(items, n):
    def L(it):
        try:
            return int(it["prompt_length"] or len(it["prompt"]))
        except (TypeError, ValueError):
            return len(it["prompt"])

    buckets = defaultdict(list)
    for it in items:
        c = L(it)
        b = "short" if c < 40 else "medium" if c < 200 else "long"
        buckets[b].append(it)
    out, per = [], max(1, n // 3)
    # deterministic: take an even stride through each bucket (no RNG — unavailable here)
    for b in buckets.values():
        step = max(1, len(b) // per)
        out.extend(b[::step][:per])
    return out[:n]


def label():
    items = stratified(load_items(), N)
    client = anthropic.Anthropic()
    fewshot = taxonomy.fewshot_messages()
    n_ok = 0
    with open(GOLD, "w") as f:
        for it in items:
            msgs = fewshot + [
                {
                    "role": "user",
                    "content": taxonomy.build_user_content(it["prompt"], it["prior_prompts"]),
                }
            ]
            r = client.messages.create(
                model=MODEL,
                max_tokens=400,
                system=taxonomy.SYSTEM,
                messages=msgs,
                output_config={"format": {"type": "json_schema", "schema": taxonomy.SCHEMA}},
            )
            text = next(b.text for b in r.content if b.type == "text")
            lab = json.loads(text)
            f.write(
                json.dumps(
                    {
                        "prompt_id": it["prompt_id"],
                        "intent": lab["intent"],
                        "behaviors": lab["behaviors"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            n_ok += 1
            if n_ok % 25 == 0:
                print(f"  gold-labeled {n_ok}/{len(items)}")
    print(f"wrote {n_ok} Opus gold labels -> {GOLD}")


def compare():
    gold = {json.loads(l)["prompt_id"]: json.loads(l) for l in open(GOLD)}
    sonnet = {json.loads(l)["prompt_id"]: json.loads(l) for l in open(LABELED)}
    ids = [i for i in gold if i in sonnet]
    print(f"comparing {len(ids)} prompts (Opus gold vs Sonnet)\n")

    # Intent agreement
    agree = sum(1 for i in ids if gold[i]["intent"] == sonnet[i]["intent"])
    print(f"INTENT agreement: {agree}/{len(ids)} = {100 * agree / len(ids):.1f}%")
    conf = Counter()
    for i in ids:
        conf[(gold[i]["intent"], sonnet[i]["intent"])] += 1
    print("  top disagreements (gold -> sonnet):")
    for (g, s), c in conf.most_common():
        if g != s:
            print(f"    {g:11s} -> {s:11s} : {c}")

    # Per-behavior precision/recall (treat Opus as truth)
    print("\nBEHAVIOR precision/recall (Opus=truth):")
    for b in taxonomy.BEHAVIORS:
        tp = sum(1 for i in ids if b in gold[i]["behaviors"] and b in sonnet[i]["behaviors"])
        fp = sum(1 for i in ids if b not in gold[i]["behaviors"] and b in sonnet[i]["behaviors"])
        fn = sum(1 for i in ids if b in gold[i]["behaviors"] and b not in sonnet[i]["behaviors"])
        prec = tp / (tp + fp) if tp + fp else float("nan")
        rec = tp / (tp + fn) if tp + fn else float("nan")
        print(f"  {b:16s} P={prec:.2f} R={rec:.2f}  (tp={tp} fp={fp} fn={fn}, gold_pos={tp + fn})")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "label"
    {"label": label, "compare": compare}[mode]()
