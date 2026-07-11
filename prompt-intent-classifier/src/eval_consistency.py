#!/usr/bin/env python3
"""Measure a labeler's run-to-run self-consistency (does the same prompt get the
same label across K independent samples?). This is how the v2 prompt / thinking-off
config was chosen. No prompt caching (each run must be an independent resample).

    python src/eval_consistency.py sample          # fix a stratified sample once
    python src/eval_consistency.py run  [K]         # label K times -> runs file
    python src/eval_consistency.py score            # agreement metrics

Config (env): LABELER_MODEL (claude-sonnet-5), LABELER_VARIANT (v2),
LABELER_EFFORT (low), LABELER_THINKING (off|adaptive), EVAL_DIR (data/eval),
SAMPLE_N (150), SAMPLE_SEED (17), K (4), WORKERS (8),
LABELABLE (data/processed/labelable.jsonl). Needs ANTHROPIC_API_KEY.
"""

import itertools
import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anthropic  # noqa: E402
import label_prompts  # noqa: E402
import taxonomy  # noqa: E402

LABELABLE = os.environ.get("LABELABLE", "data/processed/labelable.jsonl")
EVAL_DIR = os.environ.get("EVAL_DIR", "data/eval")
MODEL = os.environ.get("LABELER_MODEL", "claude-sonnet-5")
VARIANT = os.environ.get("LABELER_VARIANT", "v2")
EFFORT = os.environ.get("LABELER_EFFORT", "low")
THINKING = os.environ.get("LABELER_THINKING", "off")
N = int(os.environ.get("SAMPLE_N", "150"))
SEED = int(os.environ.get("SAMPLE_SEED", "17"))
WORKERS = int(os.environ.get("WORKERS", "8"))
SAMPLE = os.path.join(EVAL_DIR, "consistency_sample.jsonl")
RUNS = os.path.join(EVAL_DIR, f"consistency_runs_{VARIANT}_{THINKING}.jsonl")
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


def do_sample():
    os.makedirs(EVAL_DIR, exist_ok=True)
    items = [json.loads(l) for l in open(LABELABLE) if json.loads(l).get("prompt")]
    rng = random.Random(SEED)

    def bucket(it):
        c = it.get("prompt_length") or len(it["prompt"])
        try:
            c = int(c)
        except (TypeError, ValueError):
            c = len(it["prompt"])
        return "short" if c < 40 else "medium" if c < 200 else "long"

    by = {}
    for it in items:
        by.setdefault(bucket(it), []).append(it)
    per, picked = N // max(1, len(by)), []
    for lst in by.values():
        rng.shuffle(lst)
        picked += lst[:per]
    rng.shuffle(picked)
    picked = picked[:N]
    with open(SAMPLE, "w") as f:
        for it in picked:
            f.write(
                json.dumps(
                    {
                        k: it.get(k)
                        for k in ("prompt_id", "prompt", "prior_prompts", "prompt_length")
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"wrote {len(picked)} -> {SAMPLE}")


def _label(client, system, extra, replace, it):
    if replace:
        fs = []
        for ex in extra:
            fs.append(
                {
                    "role": "user",
                    "content": taxonomy.build_user_content(ex["prompt"], ex.get("prior", [])),
                }
            )
            fs.append({"role": "assistant", "content": json.dumps(ex["label"])})
    else:
        fs = taxonomy.fewshot_messages()
    kw = {
        "model": MODEL,
        "max_tokens": 400,
        "system": system,
        "messages": fs
        + [
            {
                "role": "user",
                "content": taxonomy.build_user_content(it["prompt"], it["prior_prompts"]),
            }
        ],
        "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
    }
    if THINKING == "off":
        kw["thinking"] = {"type": "disabled"}
    r = client.messages.create(**kw)
    cr = getattr(r.usage, "cache_read_input_tokens", 0) or 0
    return json.loads(next(b.text for b in r.content if b.type == "text")), cr


def do_run(K):
    system, extra, replace = label_prompts.resolve(VARIANT)
    items = [json.loads(l) for l in open(SAMPLE)]
    client = anthropic.Anthropic()
    results, cache_read = {}, 0

    def job(t):
        it, k = t
        for attempt in range(4):
            try:
                lab, cr = _label(client, system, extra, replace, it)
                return it["prompt_id"], k, lab, cr
            except Exception as e:
                if attempt == 3:
                    return it["prompt_id"], k, {"_error": str(e)[:120]}, 0

    tasks = [(it, k) for it in items for k in range(K)]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for fut in as_completed([ex.submit(job, t) for t in tasks]):
            pid, k, lab, cr = fut.result()
            results.setdefault(pid, {})[k] = lab
            cache_read += cr
    with open(RUNS, "w") as f:
        for it in items:
            f.write(
                json.dumps(
                    {
                        "prompt_id": it["prompt_id"],
                        "prompt": it["prompt"],
                        "runs": [results[it["prompt_id"]][k] for k in range(K)],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"CACHE CHECK: cache_read={cache_read} (must be 0 for a valid self-agreement test)")
    print(f"wrote {RUNS}")


def do_score():
    rows = [json.loads(l) for l in open(RUNS)]
    iu = ipn = ipd = bu = n = 0
    bj = bjn = 0.0
    for r in rows:
        runs = [x for x in r["runs"] if "_error" not in x]
        if len(runs) < 2:
            continue
        n += 1
        ints = [x["intent"] for x in runs]
        if len(set(ints)) == 1:
            iu += 1
        for a, b in itertools.combinations(ints, 2):
            ipd += 1
            ipn += a == b
        behs = [frozenset(x["behaviors"]) for x in runs]
        if len(set(behs)) == 1:
            bu += 1
        for a, b in itertools.combinations(behs, 2):
            un = len(a | b)
            bj += len(a & b) / un if un else 1.0
            bjn += 1
    print(f"variant={VARIANT} model={MODEL} thinking={THINKING} N={n}")
    print(f"  INTENT   unanimous={100 * iu / n:.1f}%  pairwise={100 * ipn / ipd:.1f}%")
    print(f"  BEHAVIOR exact-set unanimous={100 * bu / n:.1f}%  mean Jaccard={bj / bjn:.3f}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sample"
    if cmd == "sample":
        do_sample()
    elif cmd == "run":
        do_run(int(sys.argv[2]) if len(sys.argv) > 2 else int(os.environ.get("K", "4")))
    elif cmd == "score":
        do_score()
