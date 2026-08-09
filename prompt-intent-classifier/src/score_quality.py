#!/usr/bin/env python3
"""Score the full labelable set for prompt quality against best practice.

Mirrors label.py's pattern (threaded, checkpointed/resumable, prompt caching
on the system+few-shot prefix). Run from the classifier dir:

    python src/score_quality.py probe      # verify prompt caching engages (~$0.01)
    python src/score_quality.py run        # score everything -> data/processed/quality_scores.jsonl

Config (env): SCORER_MODEL (default claude-sonnet-5), SCORER_EFFORT (low),
SCORER_THINKING (off|adaptive, default off), WORKERS (16),
LABELABLE (data/processed/labelable.jsonl),
QUALITY_OUT (data/processed/quality_scores.jsonl).

Provider: SCORER_PROVIDER=anthropic|openai|auto (default auto). auto picks
Anthropic if ANTHROPIC_API_KEY is set, else falls back to OpenAI if
OPENAI_API_KEY is set (`openai` package required only in that case;
`pip install openai`). SCORER_OPENAI_MODEL (default gpt-4o-mini) selects the
OpenAI model. Needs ANTHROPIC_API_KEY and/or OPENAI_API_KEY (e.g.
`set -a; . ../.env; set +a`).
"""

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quality_rubric as qr  # noqa: E402

LABELABLE = os.environ.get("LABELABLE", "data/processed/labelable.jsonl")
OUT = os.environ.get("QUALITY_OUT", "data/processed/quality_scores.jsonl")
CKPT = os.environ.get("QUALITY_CKPT", OUT.replace(".jsonl", ".checkpoint.jsonl"))
MODEL = os.environ.get("SCORER_MODEL", "claude-sonnet-5")
OPENAI_MODEL = os.environ.get("SCORER_OPENAI_MODEL", "gpt-4o-mini")
EFFORT = os.environ.get("SCORER_EFFORT", "low")
THINKING = os.environ.get("SCORER_THINKING", "off")  # off | adaptive
WORKERS = int(os.environ.get("WORKERS", "16"))
# rough live cost readout; approximate, check current provider pricing pages
PIN, POUT, PCR, PCW = 2.0 / 1e6, 10.0 / 1e6, 0.2 / 1e6, 2.5 / 1e6  # anthropic sonnet
OPENAI_PIN, OPENAI_POUT, OPENAI_PCR = 0.15 / 1e6, 0.60 / 1e6, 0.075 / 1e6  # gpt-4o-mini

lock = threading.Lock()
u = {"in": 0, "out": 0, "cr": 0, "cw": 0}


def resolve_provider():
    p = os.environ.get("SCORER_PROVIDER", "auto")
    if p in ("anthropic", "openai"):
        return p
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    raise RuntimeError(
        "no provider available: set ANTHROPIC_API_KEY or OPENAI_API_KEY "
        "(or SCORER_PROVIDER to force one)"
    )


def get_client(provider):
    if provider == "anthropic":
        import anthropic

        return anthropic.Anthropic()
    import openai

    return openai.OpenAI()


def _fewshot_anthropic():
    """Few-shot with a cache breakpoint on the last turn."""
    msgs = qr.fewshot_messages()
    msgs[-1] = {
        "role": msgs[-1]["role"],
        "content": [
            {"type": "text", "text": msgs[-1]["content"], "cache_control": {"type": "ephemeral"}}
        ],
    }
    return msgs


def _score_anthropic(client, it):
    kw = {
        "model": MODEL,
        "max_tokens": 400,
        "system": qr.SYSTEM,
        "messages": _fewshot_anthropic()
        + [
            {
                "role": "user",
                "content": qr.build_user_content(it["prompt"]),
            }
        ],
        "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": qr.SCHEMA}},
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


def _score_openai(client, it):
    messages = [{"role": "system", "content": qr.SYSTEM}]
    for m in qr.fewshot_messages():
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append(
        {
            "role": "user",
            "content": qr.build_user_content(it["prompt"]),
        }
    )
    r = client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=400,
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "quality_score", "strict": True, "schema": qr.SCHEMA},
        },
    )
    with lock:
        u["in"] += r.usage.prompt_tokens
        u["out"] += r.usage.completion_tokens
        cached = getattr(r.usage, "prompt_tokens_details", None)
        u["cr"] += getattr(cached, "cached_tokens", 0) or 0
    return json.loads(r.choices[0].message.content)


def score(provider, client, it):
    return _score_anthropic(client, it) if provider == "anthropic" else _score_openai(client, it)


def _cost(provider):
    if provider == "anthropic":
        return u["in"] * PIN + u["out"] * POUT + u["cr"] * PCR + u["cw"] * PCW
    return u["in"] * OPENAI_PIN + u["out"] * OPENAI_POUT + u["cr"] * OPENAI_PCR


def probe():
    provider = resolve_provider()
    client = get_client(provider)
    print(f"provider={provider} model={MODEL if provider == 'anthropic' else OPENAI_MODEL}")
    for i, it in enumerate([json.loads(l) for l in open(LABELABLE)][:3]):
        score(provider, client, it)
        print(f"  call {i}: cache_creation={u['cw']} cache_read={u['cr']}")
    print(
        "CACHING ENGAGED"
        if u["cr"] > 0
        else "!! caching NOT engaging (prefix under the token minimum, or provider doesn't report it)"
    )


def run():
    provider = resolve_provider()
    model = MODEL if provider == "anthropic" else OPENAI_MODEL
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
        f"provider={provider} model={model} thinking={THINKING} | "
        f"total={len(items)} done={len(done)} todo={len(todo)}",
        flush=True,
    )
    client = get_client(provider)

    def job(it):
        for attempt in range(5):
            try:
                sc = score(provider, client, it)
                dims = {d: sc[d] for d in qr.DIMENSIONS}
                overall = qr.overall_score(dims)
                return {
                    "prompt_id": it["prompt_id"],
                    "session_id": it.get("session_id"),
                    "user_email": it.get("user_email"),
                    "prompt": it.get("prompt"),
                    "prompt_length": it.get("prompt_length"),
                    "scores": dims,
                    "overall_score": overall,
                    "tier": qr.tier(overall),
                    "top_issue": sc["top_issue"],
                    "suggestion": sc["suggestion"],
                    "confidence": sc["confidence"],
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
                print(f"  {n}/{len(todo)}  ~${_cost(provider):.2f}  cache_read={u['cr']}", flush=True)
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
    print(f"DONE: scored={len(recs)} errors={errs} -> {OUT}")
    print(
        f"SPENT this run: ~${_cost(provider):.2f} (in={u['in']} out={u['out']} cache_read={u['cr']} cache_write={u['cw']})"
    )


if __name__ == "__main__":
    (probe if len(sys.argv) > 1 and sys.argv[1] == "probe" else run)()
