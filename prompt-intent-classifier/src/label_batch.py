"""Label the full corpus of real prompts with Sonnet 4.6 via the Batch API (50% off).

Usage:
  python src/label_batch.py submit   # build + submit the batch, save its id
  python src/label_batch.py fetch     # retrieve results -> data/labeled.jsonl

Each request is forced through the structured-output schema, so results parse
without repair. custom_id = prompt_id, so we can join labels back to the corpus.
"""

import json
import os
import sys

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

sys.path.insert(0, os.path.dirname(__file__))
import taxonomy
from preprocess import real_prompts_with_context

MODEL = os.environ.get("LABELER_MODEL", "claude-sonnet-4-6")
BATCH_ID_FILE = "data/batch_id.txt"
OUT = "data/labeled.jsonl"
ITEMS_FILE = "data/label_items.jsonl"  # snapshot of what we submitted (for join)


def build_requests(items):
    fewshot = taxonomy.fewshot_messages()
    reqs = []
    for it in items:
        msgs = fewshot + [
            {
                "role": "user",
                "content": taxonomy.build_user_content(it["prompt"], it["prior_prompts"]),
            }
        ]
        reqs.append(
            Request(
                custom_id=it["prompt_id"],
                params=MessageCreateParamsNonStreaming(
                    model=MODEL,
                    max_tokens=400,
                    system=taxonomy.SYSTEM,
                    messages=msgs,
                    output_config={
                        "effort": "low",
                        "format": {"type": "json_schema", "schema": taxonomy.SCHEMA},
                    },
                ),
            )
        )
    return reqs


def submit():
    items = real_prompts_with_context()
    # dedupe by prompt_id (custom_id must be unique within a batch)
    seen, uniq = set(), []
    for it in items:
        if it["prompt_id"] and it["prompt_id"] not in seen:
            seen.add(it["prompt_id"])
            uniq.append(it)
    with open(ITEMS_FILE, "w") as f:
        for it in uniq:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    reqs = build_requests(uniq)
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=reqs)
    with open(BATCH_ID_FILE, "w") as f:
        f.write(batch.id)
    print(f"submitted batch {batch.id} with {len(reqs)} requests (model={MODEL})")
    print(f"status: {batch.processing_status}")


def fetch():
    client = anthropic.Anthropic()
    batch_id = open(BATCH_ID_FILE).read().strip()
    batch = client.messages.batches.retrieve(batch_id)
    print(f"batch {batch_id}: {batch.processing_status} counts={batch.request_counts}")
    if batch.processing_status != "ended":
        print("not finished yet; re-run fetch later.")
        return
    items = {json.loads(l)["prompt_id"]: json.loads(l) for l in open(ITEMS_FILE)}
    n_ok = n_err = 0
    with open(OUT, "w") as out:
        for res in client.messages.batches.results(batch_id):
            if res.result.type != "succeeded":
                n_err += 1
                continue
            msg = res.result.message
            text = next((b.text for b in msg.content if b.type == "text"), None)
            if not text:
                n_err += 1
                continue
            try:
                label = json.loads(text)
            except json.JSONDecodeError:
                n_err += 1
                continue
            it = items.get(res.custom_id, {})
            rec = {
                "prompt_id": res.custom_id,
                "session_id": it.get("session_id"),
                "user_email": it.get("user_email"),
                "prompt": it.get("prompt"),
                "prompt_length": it.get("prompt_length"),
                "intent": label["intent"],
                "behaviors": label["behaviors"],
                "confidence": label["confidence"],
                "rationale": label.get("rationale", ""),
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_ok += 1
    print(f"wrote {n_ok} labeled prompts -> {OUT}  ({n_err} errored/skipped)")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "submit"
    {"submit": submit, "fetch": fetch}[mode]()
