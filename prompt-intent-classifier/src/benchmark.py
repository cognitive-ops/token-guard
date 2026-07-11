"""Deployment-cost benchmark for the low-end analytics box.

For each fine-tuned student: on-disk size, single-thread CPU latency (fp32), and the
same after int8 dynamic quantization. Single thread simulates a low-end core; the
real workload is hourly batch over a few hundred new prompts, so this is plenty.

Usage: python src/benchmark.py data/model_ft_*.pt
"""

import glob
import json
import os
import sys
import time

import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(__file__))
from train_ft import SEP, MultiTask
from transformers import AutoTokenizer

torch.set_num_threads(1)  # low-end single-core worst case


def sample_texts(n=200):
    items = {json.loads(l)["prompt_id"]: json.loads(l) for l in open("data/label_items.jsonl")}
    out = []
    for l in open("data/labeled.jsonl"):
        d = json.loads(l)
        it = items.get(d["prompt_id"], {})
        prior = it.get("prior_prompts") or []
        prev = prior[-1] if prior else ""
        out.append((prev + SEP + (d["prompt"] or "")) if prev else (d["prompt"] or ""))
        if len(out) >= n:
            break
    return out


def time_model(model, tok, texts, maxlen=256):
    model.eval()
    with torch.no_grad():
        # warmup
        enc = tok(texts[0], truncation=True, max_length=maxlen, return_tensors="pt")
        model(**enc)
        t = time.time()
        for tx in texts:
            enc = tok(tx, truncation=True, max_length=maxlen, return_tensors="pt")
            model(**enc)
        dt = time.time() - t
    return dt / len(texts) * 1000  # ms/prompt


def main():
    paths = sys.argv[1:] or glob.glob("data/model_ft_*.pt")
    texts = sample_texts(200)
    print(f"{'model':46s} {'size_MB':>8} {'ms/prompt':>10} {'int8_MB':>8} {'int8_ms':>8}")
    for p in paths:
        b = torch.load(p, map_location="cpu")
        model = MultiTask(b["base"], len(b["intents"]), len(b["behaviors"]))
        model.load_state_dict(b["state_dict"])
        tok = AutoTokenizer.from_pretrained(b["base"])
        size = os.path.getsize(p) / 1e6
        ms = time_model(model, tok, texts, b["maxlen"])

        qmodel = torch.ao.quantization.quantize_dynamic(model, {nn.Linear}, dtype=torch.qint8)
        qpath = p.replace(".pt", ".int8.pt")
        torch.save({**b, "state_dict": qmodel.state_dict()}, qpath)
        qsize = os.path.getsize(qpath) / 1e6
        qms = time_model(qmodel, tok, texts, b["maxlen"])

        name = os.path.basename(p).replace("model_ft_", "").replace(".pt", "")
        print(f"{name:46s} {size:8.0f} {ms:10.1f} {qsize:8.0f} {qms:8.1f}")


if __name__ == "__main__":
    main()
