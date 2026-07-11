"""Error analysis for the intent classifier.

Confusion matrix + stratification of accuracy by (a) Sonnet label confidence and
(b) run1/run2 self-agreement, to separate *label noise* from *model error*. Also
dumps sample misclassifications for the top confused pairs (local only — prompt text
is sensitive, never committed).
"""

import json
import os
import sys

import numpy as np
import torch
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import train_test_split

sys.path.insert(0, os.path.dirname(__file__))
import taxonomy
from train_ft import MultiTask, load_joined
from transformers import AutoTokenizer

MODEL = os.environ.get("ANALYZE_MODEL", "data/model_ft2_xlm-roberta-base.pt")
INTENTS = taxonomy.INTENTS


def run2_labels():
    """run2 intent labels by prompt_id (from API; cached results)."""
    import anthropic

    c = anthropic.Anthropic()
    out = {}
    for r in c.messages.batches.results("msgbatch_019CyhvpkLW4r7HjZ2bvRchC"):
        if r.result.type != "succeeded":
            continue
        t = next((b.text for b in r.result.message.content if b.type == "text"), None)
        if t:
            out[r.custom_id] = json.loads(t)["intent"]
    return out


def main():
    rows = load_joined()
    meta = [json.loads(l) for l in open("data/labeled.jsonl")]  # aligned with rows order
    assert len(meta) == len(rows)
    pid = [m["prompt_id"] for m in meta]
    conf = [m["confidence"] for m in meta]
    prompts = [m["prompt"] for m in meta]

    y = np.array([r["intent"] for r in rows])
    idx = np.arange(len(rows))
    _, te = train_test_split(idx, test_size=0.2, random_state=0, stratify=y)

    b = torch.load(MODEL, map_location="cuda")
    tok = AutoTokenizer.from_pretrained(b["base"])
    m = MultiTask(b["base"], len(b["intents"]), len(b["behaviors"]))
    m.load_state_dict(b["state_dict"])
    m.cuda().eval()

    preds = {}
    with torch.no_grad():
        for i in te:
            enc = tok(rows[i]["text"], truncation=True, max_length=256, return_tensors="pt").to(
                "cuda"
            )
            preds[i] = int(m(**enc)[0].argmax(1))

    yt = np.array([rows[i]["intent"] for i in te])
    yp = np.array([preds[i] for i in te])
    acc = (yt == yp).mean()
    print(f"MODEL={os.path.basename(MODEL)}  held-out acc={acc:.3f}  n={len(te)}\n")

    print("CONFUSION MATRIX (rows=true, cols=pred):")
    cm = confusion_matrix(yt, yp, labels=range(len(INTENTS)))
    print("true\\pred   " + " ".join(f"{x[:5]:>6}" for x in INTENTS))
    for i, name in enumerate(INTENTS):
        print(f"{name:11s} " + " ".join(f"{cm[i, j]:6d}" for j in range(len(INTENTS))))

    print("\nTOP CONFUSED PAIRS (true -> pred):")
    pairs = []
    for i in range(len(INTENTS)):
        for j in range(len(INTENTS)):
            if i != j and cm[i, j] > 0:
                pairs.append((cm[i, j], INTENTS[i], INTENTS[j]))
    pairs.sort(reverse=True)
    for c, a, bb in pairs[:8]:
        print(f"  {a:11s} -> {bb:11s} : {c}")

    # stratify by Sonnet confidence
    print("\nACCURACY BY SONNET CONFIDENCE:")
    for level in ["high", "medium", "low"]:
        sel = [i for i in te if conf[i] == level]
        if sel:
            a = np.mean([preds[i] == rows[i]["intent"] for i in sel])
            print(f"  {level:7s} n={len(sel):5d} acc={a:.3f}")

    # stratify by run1/run2 agreement
    print("\nACCURACY BY RUN1/RUN2 LABEL AGREEMENT:")
    r2 = run2_labels()
    agree_idx, disagree_idx = [], []
    for i in te:
        p = pid[i]
        if p in r2:
            (agree_idx if r2[p] == INTENTS[rows[i]["intent"]] else disagree_idx).append(i)
    for name, sel in [
        ("labels AGREE (clean)", agree_idx),
        ("labels DISAGREE (ambiguous)", disagree_idx),
    ]:
        if sel:
            a = np.mean([preds[i] == rows[i]["intent"] for i in sel])
            print(f"  {name:28s} n={len(sel):5d} acc={a:.3f}")

    # sample misclassifications for the top confused pair
    if pairs:
        _, ta, pa = pairs[0]
        ti, pj = INTENTS.index(ta), INTENTS.index(pa)
        print(f"\nSAMPLE MISCLASSIFICATIONS — true={ta} predicted={pa} (local only):")
        shown = 0
        for i in te:
            if rows[i]["intent"] == ti and preds[i] == pj:
                print(f"  [{conf[i]:6s}] {prompts[i][:120]}")
                shown += 1
                if shown >= 6:
                    break


if __name__ == "__main__":
    main()
