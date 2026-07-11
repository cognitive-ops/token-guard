"""Recompute Sonnet-vs-Sonnet self-agreement from the two labeling batches.

Reproduces the table in LABEL_RELIABILITY.md. Run 1 is read from the downloaded
results file if present, else fetched from the API by batch id.

Usage: python src/label_reliability.py
"""

import json
import os
import sys

import anthropic

sys.path.insert(0, os.path.dirname(__file__))
import taxonomy

RUN1_ID = "msgbatch_01VauTR4YTsrEt6UEEP5SyMx"
RUN2_ID = "msgbatch_019CyhvpkLW4r7HjZ2bvRchC"
# Optional local copy of run-1 results (gitignored). If absent, fetched from the API
# by RUN1_ID. Override with the RUN1_FILE env var (e.g. a downloaded results file).
RUN1_FILE = os.environ.get("RUN1_FILE", "data/run1_results.jsonl")


def from_file(path):
    out = {}
    for l in open(path):
        d = json.loads(l)
        if d["result"]["type"] != "succeeded":
            continue
        t = next(
            (b["text"] for b in d["result"]["message"]["content"] if b["type"] == "text"), None
        )
        if t:
            out[d["custom_id"]] = json.loads(t)
    return out


def from_api(client, batch_id):
    out = {}
    for r in client.messages.batches.results(batch_id):
        if r.result.type != "succeeded":
            continue
        t = next((b.text for b in r.result.message.content if b.type == "text"), None)
        if t:
            out[r.custom_id] = json.loads(t)
    return out


def main():
    client = anthropic.Anthropic()
    run1 = from_file(RUN1_FILE) if os.path.exists(RUN1_FILE) else from_api(client, RUN1_ID)
    run2 = from_api(client, RUN2_ID)
    common = sorted(set(run1) & set(run2))
    N = len(common)
    print(f"run1={RUN1_ID} succeeded={len(run1)}")
    print(f"run2={RUN2_ID} succeeded={len(run2)}")
    print(f"overlap N={N}")
    ai = sum(1 for i in common if run1[i]["intent"] == run2[i]["intent"])
    print(f"INTENT agree {ai}/{N} = {100 * ai / N:.2f}%")
    ex = sum(1 for i in common if set(run1[i]["behaviors"]) == set(run2[i]["behaviors"]))
    for b in taxonomy.BEHAVIORS:
        ag = sum(1 for i in common if (b in run1[i]["behaviors"]) == (b in run2[i]["behaviors"]))
        p1 = sum(1 for i in common if b in run1[i]["behaviors"])
        p2 = sum(1 for i in common if b in run2[i]["behaviors"])
        print(f"  {b:16s} agree={ag}/{N}={100 * ag / N:.2f}% run1_pos={p1} run2_pos={p2}")
    print(f"BEHAVIOR exact-set agree {ex}/{N} = {100 * ex / N:.2f}%")


if __name__ == "__main__":
    main()
