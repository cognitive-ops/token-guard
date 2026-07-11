"""Light CPU inference — onnxruntime + tokenizers only (no torch, no transformers).

This is what runs on the low-end analytics box. Footprint: onnxruntime (~200 MB)
+ tokenizers (~15 MB) + the int8 ONNX model (~120 MB) + tokenizer.json.
"""

import json
import os

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

DIR = os.environ.get("ONNX_DIR", "data/onnx")
_SESS = None
_TOK = None
_META = None


def _load(int8=True):
    global _SESS, _TOK, _META
    if _SESS is None:
        _META = json.load(open(os.path.join(DIR, "meta.json")))
        _TOK = Tokenizer.from_file(os.path.join(DIR, "tokenizer.json"))
        _TOK.enable_truncation(max_length=_META["maxlen"])
        name = "model.int8.onnx" if int8 else "model.onnx"
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(os.environ.get("ORT_THREADS", "2"))  # 2-core box
        _SESS = ort.InferenceSession(
            os.path.join(DIR, name), so, providers=["CPUExecutionProvider"]
        )
    return _SESS, _TOK, _META


def _softmax(x):
    e = np.exp(x - x.max())
    return e / e.sum()


def classify_onnx(prompt, prev="", intent_threshold=0.67, behavior_threshold=0.5, int8=True):
    sess, tok, meta = _load(int8)
    text = (prev + meta["sep"] + prompt) if prev else prompt
    enc = tok.encode(text)
    ids = np.array([enc.ids], dtype=np.int64)
    mask = np.array([enc.attention_mask], dtype=np.int64)
    il, bl = sess.run(None, {"input_ids": ids, "attention_mask": mask})
    p = _softmax(il[0])
    top = int(p.argmax())
    conf = float(p[top])
    intent = meta["intents"][top] if conf >= intent_threshold else "unclassified"
    bprob = 1 / (1 + np.exp(-bl[0]))
    # tuned per-behavior; behavior_threshold is the fallback
    bthr = meta.get("behavior_thresholds", {})
    behaviors = [
        meta["behaviors"][j]
        for j in range(len(meta["behaviors"]))
        if bprob[j] >= bthr.get(meta["behaviors"][j], behavior_threshold)
    ]
    return {
        "intent": intent,
        "intent_confidence": round(conf, 3),
        "top_intent": meta["intents"][top],
        "behaviors": behaviors,
    }


if __name__ == "__main__":
    for p, prev in [
        ("add a dark-mode toggle to the settings page", ""),
        ("still failing with the same error", "fix the login bug"),
        ("also add CSV export while you're at it", "build the report table"),
        ("how does the auth middleware decide which routes to protect?", ""),
    ]:
        print(f"{p[:46]:46s} -> {classify_onnx(p, prev)}")
