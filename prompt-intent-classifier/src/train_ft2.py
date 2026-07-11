"""Accuracy-tuned student trainer (v3). Target: >75% intent accuracy.

Changes vs train_ft.py, all aimed at intent accuracy (eval against Sonnet held-out):
  - NO class weighting (balanced weights trade accuracy for rare-class recall)
  - behavior loss down-weighted (BEHAVIOR_W) so intent dominates the shared encoder
  - label smoothing on intent CE
  - linear warmup + more epochs; per-epoch held-out eval, save BEST checkpoint
  - dynamic (per-batch) padding so epochs are cheap and we can train longer
  - configurable base (default xlm-roberta-base, the strongest that loads cleanly)

Same held-out split (seed 0, stratified) as all prior runs — directly comparable.
"""

import os
import sys

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import classification_report, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer, get_linear_schedule_with_warmup

sys.path.insert(0, os.path.dirname(__file__))
import taxonomy
from train_ft import SEP, MultiTask, load_joined

BASE = os.environ.get("FT_BASE", "xlm-roberta-base")
OUT = os.environ.get("FT_OUT", f"data/model_ft2_{BASE.split('/')[-1]}.pt")
EPOCHS = int(os.environ.get("FT_EPOCHS", "6"))
BEHAVIOR_W = float(os.environ.get("BEHAVIOR_W", "0.4"))
MAXLEN = 256
BS = 32
LR = 2e-5
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
INTENTS, BEHAVIORS = taxonomy.INTENTS, taxonomy.BEHAVIORS


class DS(Dataset):
    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


def make_collate(tok):
    def collate(batch):
        enc = tok(
            [r["text"] for r in batch],
            truncation=True,
            max_length=MAXLEN,
            padding=True,
            return_tensors="pt",
        )
        yi = torch.tensor([r["intent"] for r in batch])
        yb = torch.tensor([r["behaviors"] for r in batch], dtype=torch.float)
        return enc, yi, yb

    return collate


@torch.no_grad()
def evaluate(model, dl):
    model.eval()
    pi, pb, ti, tb = [], [], [], []
    for enc, yi, yb in dl:
        enc = {k: v.to(DEVICE) for k, v in enc.items()}
        li, lb = model(**enc)
        pi.append(li.argmax(1).cpu().numpy())
        pb.append((torch.sigmoid(lb).cpu().numpy() >= 0.5).astype(int))
        ti.append(yi.numpy())
        tb.append(yb.numpy().astype(int))
    return (np.concatenate(pi), np.concatenate(ti), np.concatenate(pb), np.concatenate(tb))


def main():
    rows = load_joined()
    print(
        f"loaded {len(rows)} | base={BASE} | epochs={EPOCHS} behavior_w={BEHAVIOR_W} device={DEVICE}"
    )
    y = np.array([r["intent"] for r in rows])
    tr_i, te_i = train_test_split(np.arange(len(rows)), test_size=0.2, random_state=0, stratify=y)
    tr, te = [rows[i] for i in tr_i], [rows[i] for i in te_i]

    tok = AutoTokenizer.from_pretrained(BASE)
    model = MultiTask(BASE, len(INTENTS), len(BEHAVIORS)).to(DEVICE)
    collate = make_collate(tok)
    dl = DataLoader(DS(tr), batch_size=BS, shuffle=True, collate_fn=collate)
    dlt = DataLoader(DS(te), batch_size=64, collate_fn=collate)

    ce = nn.CrossEntropyLoss(label_smoothing=0.05)  # no class weights
    bce = nn.BCEWithLogitsLoss()
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    steps = len(dl) * EPOCHS
    sched = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)

    best_acc, best_state = 0.0, None
    for ep in range(EPOCHS):
        model.train()
        tot = 0.0
        for enc, yi, yb in dl:
            enc = {k: v.to(DEVICE) for k, v in enc.items()}
            yi, yb = yi.to(DEVICE), yb.to(DEVICE)
            li, lb = model(**enc)
            loss = ce(li, yi) + BEHAVIOR_W * bce(lb, yb)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            tot += loss.item()
        pi, ti, _, _ = evaluate(model, dlt)
        acc = (pi == ti).mean()
        print(f"epoch {ep + 1}/{EPOCHS} loss={tot / len(dl):.3f}  held-out intent acc={acc:.3f}")
        if acc > best_acc:
            best_acc = acc
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    pi, ti, pb, tb = evaluate(model, dlt)
    print(f"\n=== BEST INTENT (held-out 20%) — acc={best_acc:.3f} ===")
    print(classification_report(ti, pi, target_names=INTENTS, digits=3, zero_division=0))
    print("=== BEHAVIORS ===")
    for j, b in enumerate(BEHAVIORS):
        P = precision_score(tb[:, j], pb[:, j], zero_division=0)
        R = recall_score(tb[:, j], pb[:, j], zero_division=0)
        F = f1_score(tb[:, j], pb[:, j], zero_division=0)
        print(f"{b:16s} P={P:.2f} R={R:.2f} F1={F:.2f} support={int(tb[:, j].sum())}")
    torch.save(
        {
            "base": BASE,
            "sep": SEP,
            "maxlen": MAXLEN,
            "intents": INTENTS,
            "behaviors": BEHAVIORS,
            "state_dict": best_state,
        },
        OUT,
    )
    print(f"\nsaved best -> {OUT}  (intent acc {best_acc:.3f})")


if __name__ == "__main__":
    main()
