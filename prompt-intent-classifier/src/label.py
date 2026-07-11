#!/usr/bin/env python3
"""Label the full labelable set with a teacher model (default Sonnet 5, v2 prompt).

Expensive + non-deterministic, so it's a manual step (not an auto-`dvc repro`
stage). Prompt caching on the system+few-shot prefix keeps cost low; the run is
checkpointed and resumable. Run from the classifier dir:

    python src/label.py probe      # verify prompt caching engages (~$0.01)
    python src/label.py run        # label everything -> data/processed/labeled.jsonl

Then version the result:  dvc add data/processed/labeled.jsonl && dvc push

Config (env): LABELER_MODEL (default claude-sonnet-5), LABELER_VARIANT (v2),
LABELER_EFFORT (low), LABELER_THINKING (off|adaptive, default off), WORKERS (16),
LABELABLE (data/processed/labelable.jsonl), LABELED_OUT (data/processed/labeled.jsonl).
Needs ANTHROPIC_API_KEY (e.g. `set -a; . ../.env; set +a`).
"""

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anthropic  # noqa: E402
import label_prompts  # noqa: E402
import taxonomy  # noqa: E402

LABELABLE = os.environ.get("LABELABLE", "data/processed/labelable.jsonl")
OUT = os.environ.get("LABELED_OUT", "data/processed/labeled.jsonl")
CKPT = os.environ.get("LABELED_CKPT", OUT.replace(".jsonl", ".checkpoint.jsonl"))
MODEL = os.environ.get("LABELER_MODEL", "claude-sonnet-5")
VARIANT = os.environ.get("LABELER_VARIANT", "v2")
EFFORT = os.environ.get("LABELER_EFFORT", "low")
THINKING = os.environ.get("LABELER_THINKING", "off")  # off | adaptive
WORKERS = int(os.environ.get("WORKERS", "16"))
PIN, POUT, PCR, PCW = 2.0 / 1e6, 10.0 / 1e6, 0.2 / 1e6, 2.5 / 1e6  # for a rough live cost readout

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

_SYSTEM, _EXTRA_FEWSHOT, _REPLACE = label_prompts.resolve(VARIANT)
lock = threading.Lock()
u = {"in": 0, "out": 0, "cr": 0, "cw": 0}


def _fewshot():
    """Base (or variant-replacement) few-shot, with a cache breakpoint on the last turn."""
    if _REPLACE:
        msgs = []
        for ex in _EXTRA_FEWSHOT:
            msgs.append(
                {
                    "role": "user",
                    "content": taxonomy.build_user_content(ex["prompt"], ex.get("prior", [])),
                }
            )
            msgs.append({"role": "assistant", "content": json.dumps(ex["label"])})
    else:
        msgs = taxonomy.fewshot_messages()
        for ex in _EXTRA_FEWSHOT:
            msgs.append(
                {
                    "role": "user",
                    "content": taxonomy.build_user_content(ex["prompt"], ex.get("prior", [])),
                }
            )
            msgs.append({"role": "assistant", "content": json.dumps(ex["label"])})
    msgs[-1] = {
        "role": msgs[-1]["role"],
        "content": [
            {"type": "text", "text": msgs[-1]["content"], "cache_control": {"type": "ephemeral"}}
        ],
    }
    return msgs


def label(client, it):
    kw = {
        "model": MODEL,
        "max_tokens": 400,
        "system": _SYSTEM,
        "messages": _fewshot()
        + [
            {
                "role": "user",
                "content": taxonomy.build_user_content(it["prompt"], it.get("prior_prompts", [])),
            }
        ],
        "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
    }
    if THINKING == "off":
        kw["thinking"] = {"type": "disabled"}
    r = client.messages.create(**kw)
    with lock:
        u["in"] += r.usage.input_tokens
        u["out"] += r.usage.output_tokens
        u["cr"] += getattr(r.usage, "cache_read_input_tokens", 0) or 0
        u["cw"] += getattr(r.usage, "cache_creation_input_tokens", 0) or 0
    return json.loads(next(b.text for b in r.content if b.type == "text"))


def _cost():
    return u["in"] * PIN + u["out"] * POUT + u["cr"] * PCR + u["cw"] * PCW


def probe():
    client = anthropic.Anthropic()
    for i, it in enumerate([json.loads(l) for l in open(LABELABLE)][:3]):
        label(client, it)
        print(f"  call {i}: cache_creation={u['cw']} cache_read={u['cr']}")
    print(
        "CACHING ENGAGED"
        if u["cr"] > 0
        else "!! caching NOT engaging (prefix under the token minimum)"
    )


def run():
    items = [json.loads(l) for l in open(LABELABLE)]
    done = set()
    if os.path.exists(CKPT):
        for line in open(CKPT):
            try:
                done.add(json.loads(line)["prompt_id"])
            except Exception:
                pass
    todo = [it for it in items if it["prompt_id"] not in done]
    print(
        f"model={MODEL} variant={VARIANT} thinking={THINKING} | total={len(items)} done={len(done)} todo={len(todo)}",
        flush=True,
    )
    client = anthropic.Anthropic()

    def job(it):
        for attempt in range(5):
            try:
                lab = label(client, it)
                return {
                    "prompt_id": it["prompt_id"],
                    "session_id": it.get("session_id"),
                    "user_email": it.get("user_email"),
                    "prompt": it.get("prompt"),
                    "prompt_length": it.get("prompt_length"),
                    "intent": lab["intent"],
                    "behaviors": lab["behaviors"],
                    "confidence": lab["confidence"],
                }
            except Exception as e:
                if attempt == 4:
                    return {"prompt_id": it["prompt_id"], "_error": str(e)[:120]}

    n = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex, open(CKPT, "a") as ck:
        for fut in as_completed([ex.submit(job, it) for it in todo]):
            with lock:
                ck.write(json.dumps(fut.result(), ensure_ascii=False) + "\n")
                ck.flush()
            n += 1
            if n % 500 == 0:
                print(f"  {n}/{len(todo)}  ~${_cost():.2f}  cache_read={u['cr']}", flush=True)
    recs = {}
    for line in open(CKPT):
        r = json.loads(line)
        if not r.get("_error"):
            recs[r["prompt_id"]] = r
    with open(OUT, "w") as f:
        for it in items:
            if it["prompt_id"] in recs:
                f.write(json.dumps(recs[it["prompt_id"]], ensure_ascii=False) + "\n")
    errs = sum(1 for line in open(CKPT) if json.loads(line).get("_error"))
    print(f"DONE: labeled={len(recs)} errors={errs} -> {OUT}")
    print(
        f"SPENT this run: ~${_cost():.2f} (in={u['in']} out={u['out']} cache_read={u['cr']} cache_write={u['cw']})"
    )


if __name__ == "__main__":
    (probe if len(sys.argv) > 1 and sys.argv[1] == "probe" else run)()
