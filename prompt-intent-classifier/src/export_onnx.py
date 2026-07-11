"""Export a fine-tuned student to ONNX (fp32 + int8) for the low-end box.

Produces data/onnx/{model.onnx, model.int8.onnx, tokenizer.json, meta.json}.
Deploy with onnxruntime + tokenizers only — no torch, no transformers (~200 MB
install vs ~3 GB, smaller Docker image, faster CPU inference).

Usage: python src/export_onnx.py [model.pt]   (default: coarse_mt — the committed deploy-model/ bundle)
"""

import json
import os
import sys

import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(__file__))
from train_ft import SEP, MultiTask
from transformers import AutoTokenizer

OUTDIR = "data/onnx"
# Prefer coarse_mt (the committed deploy-model/ bundle), then the v4/v2 distilbert fine-tunes.
DEFAULT = next(
    (
        p
        for p in [
            "data/model_coarse_mt_xlm-roberta-base.pt",
            "data/model_ft3_distilbert-base-multilingual-cased.pt",
            "data/model_ft_distilbert-base-multilingual-cased.pt",
        ]
        if os.path.exists(p)
    ),
    None,
)


class ONNXWrap(nn.Module):
    """Explicit positional forward so torch.onnx.export can trace it."""

    def __init__(self, mt):
        super().__init__()
        self.mt = mt

    def forward(self, input_ids, attention_mask):
        return self.mt(input_ids=input_ids, attention_mask=attention_mask)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    assert path, "no model.pt found to export"
    os.makedirs(OUTDIR, exist_ok=True)
    b = torch.load(path, map_location="cpu")
    model = MultiTask(b["base"], len(b["intents"]), len(b["behaviors"]))
    model.load_state_dict(b["state_dict"])
    model.eval()
    wrap = ONNXWrap(model).eval()

    tok = AutoTokenizer.from_pretrained(b["base"])
    enc = tok("export sample prompt", return_tensors="pt")
    args = (enc["input_ids"], enc["attention_mask"])

    fp32 = os.path.join(OUTDIR, "model.onnx")
    torch.onnx.export(
        wrap,
        args,
        fp32,
        input_names=["input_ids", "attention_mask"],
        output_names=["intent_logits", "behavior_logits"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "seq"},
            "attention_mask": {0: "batch", 1: "seq"},
            "intent_logits": {0: "batch"},
            "behavior_logits": {0: "batch"},
        },
        opset_version=17,
        dynamo=False,  # legacy TorchScript exporter (no onnxscript dependency)
    )

    # int8 dynamic quantization (weights only) — onnxruntime
    from onnxruntime.quantization import QuantType, quantize_dynamic

    int8 = os.path.join(OUTDIR, "model.int8.onnx")
    quantize_dynamic(fp32, int8, weight_type=QuantType.QInt8)

    # tokenizer + metadata for the light runtime
    tok.save_pretrained(OUTDIR)  # writes tokenizer.json
    json.dump(
        {
            "base": b["base"],
            "sep": SEP,
            "maxlen": b["maxlen"],
            "intents": b["intents"],
            "behaviors": b["behaviors"],
            "source_model": os.path.basename(path),
        },
        open(os.path.join(OUTDIR, "meta.json"), "w"),
        indent=2,
    )

    for f in ("model.onnx", "model.int8.onnx", "tokenizer.json"):
        p = os.path.join(OUTDIR, f)
        if os.path.exists(p):
            print(f"  {f:20s} {os.path.getsize(p) / 1e6:7.1f} MB")
    print(f"exported {path} -> {OUTDIR}/")


if __name__ == "__main__":
    main()
