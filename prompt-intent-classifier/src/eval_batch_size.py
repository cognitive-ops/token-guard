#!/usr/bin/env python3
"""Does packing N prompts per call degrade labels vs 1/call? Compares self-
consistency and cross-mode agreement (N/call consensus vs 1/call consensus).
This is what showed 15/call degrading quality, so we kept 1/call + caching.

    python src/eval_batch_size.py        # run 1/call and N/call, K each, then score

Config (env): LABELER_MODEL (claude-sonnet-5), LABELER_VARIANT (v2),
LABELER_EFFORT (low), LABELER_THINKING (off|adaptive), BATCH_SIZE (15), K (3),
EVAL_DIR (data/eval), SAMPLE (data/eval/consistency_sample.jsonl — run
eval_consistency.py sample first), WORKERS (10). Needs ANTHROPIC_API_KEY.
"""

import itertools
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

EVAL_DIR = os.environ.get("EVAL_DIR", "data/eval")
SAMPLE = os.environ.get("SAMPLE", os.path.join(EVAL_DIR, "consistency_sample.jsonl"))
CKPT = os.path.join(EVAL_DIR, "batch_size.jsonl")
MODEL = os.environ.get("LABELER_MODEL", "claude-sonnet-5")
VARIANT = os.environ.get("LABELER_VARIANT", "v2")
EFFORT = os.environ.get("LABELER_EFFORT", "low")
THINKING = os.environ.get("LABELER_THINKING", "off")
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "15"))
K = int(os.environ.get("K", "3"))
WORKERS = int(os.environ.get("WORKERS", "10"))
SYSTEM, _E, _R = label_prompts.resolve(VARIANT)
_LBL = {
    "intent": {"type": "string", "enum": taxonomy.INTENTS},
    "behaviors": {"type": "array", "items": {"type": "string", "enum": taxonomy.BEHAVIORS}},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
}
SCHEMA_1 = {
    "type": "object",
    "properties": _LBL,
    "required": list(_LBL),
    "additionalProperties": False,
}
SCHEMA_N = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, **_LBL},
                "required": ["id", *list(_LBL)],
                "additionalProperties": False,
            },
        }
    },
    "required": ["labels"],
    "additionalProperties": False,
}
lock = threading.Lock()


def _prior(pp):
    return "\n".join(f"  {i + 1}. {p[:300]}" for i, p in enumerate(pp[-5:])) or "  (none)"


def _batch_content(chunk):
    parts = [
        f"Label EACH of the {len(chunk)} items below independently. Return one object "
        f"per item in `labels`, using the item's exact id. Use an item's PRIOR PROMPTS "
        f"only for the sequence-level behaviors."
    ]
    for it in chunk:
        parts.append(
            f"\n===== ITEM id={it['prompt_id']} =====\nPRIOR PROMPTS:\n{_prior(it['prior_prompts'])}\n"
            f"PROMPT TO LABEL:\n{it['prompt'][:4000]}"
        )
    return "\n".join(parts)


def _call(client, msgs, schema):
    kw = {
        "model": MODEL,
        "max_tokens": 3000,
        "system": SYSTEM,
        "messages": msgs,
        "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": schema}},
    }
    if THINKING == "off":
        kw["thinking"] = {"type": "disabled"}
    r = client.messages.create(**kw)
    return json.loads(next(b.text for b in r.content if b.type == "text"))


def run_and_score():
    os.makedirs(EVAL_DIR, exist_ok=True)
    items = [json.loads(l) for l in open(SAMPLE)]
    fs = taxonomy.fewshot_messages()
    client = anthropic.Anthropic()
    open(CKPT, "w").close()
    tasks = []
    for k in range(K):
        for it in items:
            tasks.append(("single", k, [it]))
        for i in range(0, len(items), BATCH_SIZE):
            tasks.append(("batch", k, items[i : i + BATCH_SIZE]))

    def job(t):
        mode, k, chunk = t
        try:
            if mode == "single":
                it = chunk[0]
                lab = _call(
                    client,
                    fs
                    + [
                        {
                            "role": "user",
                            "content": taxonomy.build_user_content(
                                it["prompt"], it["prior_prompts"]
                            ),
                        }
                    ],
                    SCHEMA_1,
                )
                return [
                    {
                        "mode": mode,
                        "k": k,
                        "pid": it["prompt_id"],
                        **{x: lab[x] for x in ("intent", "behaviors")},
                    }
                ]
            obj = _call(client, fs + [{"role": "user", "content": _batch_content(chunk)}], SCHEMA_N)
            by = {x["id"]: x for x in obj.get("labels", [])}
            return [
                {
                    "mode": mode,
                    "k": k,
                    "pid": it["prompt_id"],
                    **{x: by[it["prompt_id"]][x] for x in ("intent", "behaviors")},
                }
                for it in chunk
                if it["prompt_id"] in by
            ]
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=WORKERS) as ex, open(CKPT, "a") as ck:
        for fut in as_completed([ex.submit(job, t) for t in tasks]):
            with lock:
                for rec in fut.result():
                    ck.write(json.dumps(rec, ensure_ascii=False) + "\n")

    by = {}
    for l in open(CKPT):
        r = json.loads(l)
        by.setdefault(r["mode"], {}).setdefault(r["pid"], []).append(r)

    def selfcons(mode):
        d = by.get(mode, {})
        ipn = ipd = bset = n = 0
        for labs in d.values():
            if len(labs) < 2:
                continue
            n += 1
            ii = [x["intent"] for x in labs]
            for a, b in itertools.combinations(ii, 2):
                ipd += 1
                ipn += a == b
            bb = [frozenset(x["behaviors"]) for x in labs]
            bset += len(set(bb)) == 1
        return n, 100 * ipn / ipd if ipd else 0, 100 * bset / n if n else 0

    for m in ("single", "batch"):
        n, ip, bs = selfcons(m)
        print(
            f"  {m:6s}(size={1 if m == 'single' else BATCH_SIZE}) N={n} intent_pairwise={ip:.1f}% behavior_exact={bs:.1f}%"
        )

    def consensus(labs):
        mi = Counter(x["intent"] for x in labs).most_common(1)[0][0]
        c = Counter(b for x in labs for b in set(x["behaviors"]))
        return mi, frozenset(b for b, v in c.items() if v * 2 >= len(labs))

    s, b = by.get("single", {}), by.get("batch", {})
    ids = [p for p in s if p in b and len(s[p]) >= 2 and len(b[p]) >= 2]
    im = bm = 0
    for p in ids:
        si, sb = consensus(s[p])
        bi, bb = consensus(b[p])
        im += si == bi
        bm += sb == bb
    if ids:
        print(
            f"CROSS-MODE ({BATCH_SIZE}/call vs 1/call, {len(ids)} prompts): "
            f"intent_agree={100 * im / len(ids):.1f}% behavior_exact_agree={100 * bm / len(ids):.1f}%"
        )


if __name__ == "__main__":
    run_and_score()
