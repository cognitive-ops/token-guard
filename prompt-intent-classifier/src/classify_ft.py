"""Local inference with a fine-tuned student (CPU-friendly, for the low-end box).

Loads a model saved by train_ft.py and classifies prompts. Default device is CPU
(the production analytics machine has no GPU); pass device="cuda" only for testing.
"""

import os
import sys

import torch

sys.path.insert(0, os.path.dirname(__file__))
from train_ft import SEP, MultiTask  # reuse the architecture
from transformers import AutoTokenizer

_CACHE = {}


def load(path, device="cpu", quantize=True):
    """Load a fine-tuned student. quantize=True applies int8 dynamic quantization
    (CPU only) — ~3x faster inference for the low-end analytics box."""
    key = (path, device, quantize)
    if key in _CACHE:
        return _CACHE[key]
    import torch.nn as nn

    b = torch.load(path, map_location=device)
    model = MultiTask(b["base"], len(b["intents"]), len(b["behaviors"]))
    model.load_state_dict(b["state_dict"])
    model.to(device).eval()
    if quantize and device == "cpu":
        model = torch.ao.quantization.quantize_dynamic(model, {nn.Linear}, dtype=torch.qint8)
    tok = AutoTokenizer.from_pretrained(b["base"])
    _CACHE[key] = (model, tok, b, device)
    return _CACHE[key]


@torch.no_grad()
def classify_ft(
    prompt,
    prev="",
    path="data/model_ft_distilbert-base-multilingual-cased.pt",
    device="cpu",
    behavior_threshold=0.5,
    intent_threshold=0.67,
):
    """Classify one prompt. Selective prediction: if the top intent's softmax
    probability is below intent_threshold, intent is reported as "unclassified"
    (flag the prompt rather than miscount it). intent_threshold=0.67 ≈ 70% coverage
    at ~75% accuracy for distilbert; use 0.63 for xlm-r (80% coverage, 76.5%)."""
    model, tok, b, dev = load(path, device)
    text = (prev + SEP + prompt) if prev else prompt
    enc = tok(text, truncation=True, max_length=b["maxlen"], return_tensors="pt").to(dev)
    li, lb = model(**enc)
    p = torch.softmax(li, 1)[0]
    top = int(p.argmax())
    conf = float(p[top])
    intent = b["intents"][top] if conf >= intent_threshold else "unclassified"
    bprobs = torch.sigmoid(lb)[0]
    behaviors = [
        b["behaviors"][j] for j in range(len(b["behaviors"])) if bprobs[j] >= behavior_threshold
    ]
    return {
        "intent": intent,
        "intent_confidence": round(conf, 3),
        "top_intent": b["intents"][top],
        "behaviors": behaviors,
    }


if __name__ == "__main__":
    path = (
        sys.argv[1] if len(sys.argv) > 1 else "data/model_ft_distilbert-base-multilingual-cased.pt"
    )
    for p, prev in [
        ("add a dark-mode toggle to the settings page", ""),
        ("still failing with the same error", "fix the login bug"),
        ("also add CSV export while you're at it", "build the report table"),
        ("how does the auth middleware decide which routes to protect?", ""),
    ]:
        print(f"{p[:48]:48s} -> {classify_ft(p, prev, path=path)}")
