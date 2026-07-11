"""Per-behavior decision-threshold tuning (free optimization of the behavior axis).

The behavior heads are high-recall / low-precision at the default 0.5 cutoff. Tuning
a per-behavior threshold to maximize F1 lifts behavior quality with no retraining.

Honest protocol: split the held-out TEST set in half — tune thresholds on one half,
report the gain on the other half (the model trained on neither). Writes the tuned
thresholds into data/onnx/meta.json so the exporter applies them per behavior.
"""

import json
import os
import sys

import numpy as np
import torch
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold

sys.path.insert(0, os.path.dirname(__file__))
import taxonomy
from train_ft import MultiTask, load_joined

MODEL = sys.argv[1] if len(sys.argv) > 1 else "data/model_coarse_mt_xlm-roberta-base.pt"
META = "data/onnx/meta.json"
BEH = taxonomy.BEHAVIORS
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def main():
    rows = load_joined()
    y = np.array([r["intent"] for r in rows])
    groups = np.array([r["session_id"] for r in rows])
    assert all(groups), "session_id missing on some rows; grouped split needs it"
    sgkf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
    _, te = next(sgkf.split(np.arange(len(rows)), y, groups))

    b = torch.load(MODEL, map_location=DEVICE)
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(b["base"])
    model = MultiTask(b["base"], len(b["intents"]), len(b["behaviors"]))
    model.load_state_dict(b["state_dict"])
    model.to(DEVICE).eval()

    # behavior probabilities + truth on the test set
    P, Y = [], []
    with torch.no_grad():
        for s in range(0, len(te), 64):
            chunk = [rows[i] for i in te[s : s + 64]]
            enc = tok(
                [r["text"] for r in chunk],
                truncation=True,
                max_length=256,
                padding=True,
                return_tensors="pt",
            ).to(DEVICE)
            _, lb = model(**enc)
            P.append(torch.sigmoid(lb).cpu().numpy())
            Y.append(np.array([r["behaviors"] for r in chunk]))
    P = np.concatenate(P)
    Y = np.concatenate(Y).astype(int)

    # split the held-out test in half BY SESSION: tune on val, report on eval (no leak)
    te_groups = groups[te]
    gss = GroupShuffleSplit(n_splits=1, test_size=0.5, random_state=1)
    val, ev = next(gss.split(np.arange(len(P)), groups=te_groups))

    print(
        f"{'behavior':16s} {'thr':>4} {'F1@0.5(eval)':>12} {'F1@tuned(eval)':>15} {'P→':>6}{'R':>6}"
    )
    tuned = {}
    grid = np.round(np.arange(0.10, 0.91, 0.02), 2)
    for j, name in enumerate(BEH):
        # best threshold on val
        best_t, best_f1 = 0.5, -1
        for t in grid:
            f = f1_score(Y[val, j], (P[val, j] >= t).astype(int), zero_division=0)
            if f > best_f1:
                best_f1, best_t = f, float(t)
        tuned[name] = best_t
        # report on eval half
        f1_05 = f1_score(Y[ev, j], (P[ev, j] >= 0.5).astype(int), zero_division=0)
        pe = (P[ev, j] >= best_t).astype(int)
        f1_t = f1_score(Y[ev, j], pe, zero_division=0)
        pr = precision_score(Y[ev, j], pe, zero_division=0)
        rc = recall_score(Y[ev, j], pe, zero_division=0)
        print(f"{name:16s} {best_t:4.2f} {f1_05:12.3f} {f1_t:15.3f} {pr:6.2f}{rc:6.2f}")

    # macro-F1 on eval half: default vs tuned
    f1d = np.mean(
        [
            f1_score(Y[ev, j], (P[ev, j] >= 0.5).astype(int), zero_division=0)
            for j in range(len(BEH))
        ]
    )
    f1t = np.mean(
        [
            f1_score(Y[ev, j], (P[ev, j] >= tuned[BEH[j]]).astype(int), zero_division=0)
            for j in range(len(BEH))
        ]
    )
    print(
        f"\nbehavior macro-F1 (eval half):  default 0.5 = {f1d:.3f}   tuned = {f1t:.3f}  (+{f1t - f1d:.3f})"
    )

    if not os.path.exists(META):
        sys.exit(f"error: {META} not found — run export_onnx.py before tune_thresholds.py")
    m = json.load(open(META))
    m["behavior_thresholds"] = tuned
    json.dump(m, open(META, "w"), indent=2)
    print(f"wrote per-behavior thresholds to {META}: {tuned}")


if __name__ == "__main__":
    main()
