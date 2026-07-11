"""Synchronous smoke test of the Haiku labeler on a small stratified sample.

Run this BEFORE the full batch to eyeball whether the rubric produces sane
labels. Stratifies across length buckets and prefers prompts that have prior
context (to exercise the sequence-level behaviors).
"""

import json
import os
import sys

import anthropic

sys.path.insert(0, os.path.dirname(__file__))
import taxonomy
from preprocess import real_prompts_with_context

MODEL = "claude-haiku-4-5"


def label_one(client, item):
    msgs = taxonomy.fewshot_messages() + [
        {
            "role": "user",
            "content": taxonomy.build_user_content(item["prompt"], item["prior_prompts"]),
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
    return json.loads(text), r.usage


def stratified_sample(items, n=18):
    def L(it):
        try:
            return int(it["prompt_length"] or len(it["prompt"]))
        except (TypeError, ValueError):
            return len(it["prompt"])

    buckets = {"short": [], "medium": [], "long": []}
    for it in items:
        c = L(it)
        buckets["short" if c < 40 else "medium" if c < 200 else "long"].append(it)
    # prefer items with prior context so sequence tags get exercised
    for b in buckets.values():
        b.sort(key=lambda it: len(it["prior_prompts"]), reverse=True)
    out, per = [], max(1, n // 3)
    for b in buckets.values():
        out.extend(b[:per])
    return out


def main():
    items = real_prompts_with_context()
    sample = stratified_sample(items, n=18)
    client = anthropic.Anthropic()
    tot_in = tot_out = 0
    for it in sample:
        label, usage = label_one(client, it)
        tot_in += usage.input_tokens
        tot_out += usage.output_tokens
        ctx = f"(ctx:{len(it['prior_prompts'])})"
        print(f"\n[{it['prompt_length']:>4}c {ctx:>8}] {it['prompt'][:110].replace(chr(10), ' ')}")
        print(
            f"   -> intent={label['intent']:11s} behaviors={label['behaviors']} "
            f"conf={label['confidence']}"
        )
        print(f"      {label['rationale']}")
    n = len(sample)
    # Haiku 4.5: $1/1M in, $5/1M out
    cost = tot_in / 1e6 * 1.0 + tot_out / 1e6 * 5.0
    print(
        f"\n--- {n} prompts | tokens in={tot_in} out={tot_out} | ${cost:.4f} "
        f"(~${cost / n * 1000:.2f}/1k prompts synchronous; batch is 50% off) ---"
    )


if __name__ == "__main__":
    main()
