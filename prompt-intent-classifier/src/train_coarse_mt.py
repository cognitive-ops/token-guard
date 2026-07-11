"""Coarse multi-task student (v5) — coarse 5-way INTENT + BEHAVIOR head together.

Combines the two wins: the coarse taxonomy (intent 76% full / 84%@70% cov) and the
behavior signals the dashboard needs. Recipe = train_ft3 (confidence-weighted intent,
behavior pos_weight, warmup, label smoothing, best-checkpoint) with coarse intent.

  build = feature+refactor · investigate = debug+understand · ops · test · other

Reports intent accuracy + per-class + behaviors + selective-prediction curve.
Default base = xlm-roberta-base. Same held-out split (seed 0, stratified on fine intent).
"""

import json
import os
import sys

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import classification_report, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedGroupKFold
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer, get_linear_schedule_with_warmup

sys.path.insert(0, os.path.dirname(__file__))
import taxonomy
from train_ft import SEP, MultiTask, load_joined

FINE = taxonomy.INTENTS
COARSE = ["build", "investigate", "ops", "test", "other"]
MAP = {
    "feature": "build",
    "refactor": "build",
    "debug": "investigate",
    "understand": "investigate",
    "ops": "ops",
    "test": "test",
    "other": "other",
}
F2C = {FINE.index(f): COARSE.index(MAP[f]) for f in FINE}
BEHAVIORS = taxonomy.BEHAVIORS

BASE = os.environ.get("FT_BASE", "xlm-roberta-base")
OUT = os.environ.get("FT_OUT", f"data/model_coarse_mt_{BASE.split('/')[-1]}.pt")
EPOCHS = int(os.environ.get("FT_EPOCHS", "6"))
BEHAVIOR_W = float(os.environ.get("BEHAVIOR_W", "0.7"))
MAXLEN, BS, LR = 256, 32, 2e-5
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
CW = {"high": 1.0, "medium": 0.7, "low": 0.3}


def load_data():
    conf = [json.loads(l)["confidence"] for l in open("data/labeled.jsonl")]
    rows = load_joined()
    for r, c in zip(rows, conf, strict=False):
        r["cw"] = CW.get(c, 0.7)
        r["coarse"] = F2C[r["intent"]]
    return rows


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
        return (
            enc,
            torch.tensor([r["coarse"] for r in batch]),
            torch.tensor([r["behaviors"] for r in batch], dtype=torch.float),
            torch.tensor([r["cw"] for r in batch], dtype=torch.float),
        )

    return collate


def main():
    rows = load_data()
    print(f"loaded {len(rows)} | base={BASE} epochs={EPOCHS} | COARSE 5-way + behaviors")
    yfine = np.array([r["intent"] for r in rows])
    groups = np.array([r["session_id"] for r in rows])
    sgkf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
    tr_i, te_i = next(sgkf.split(np.arange(len(rows)), yfine, groups))
    tr, te = [rows[i] for i in tr_i], [rows[i] for i in te_i]
    tok = AutoTokenizer.from_pretrained(BASE)
    model = MultiTask(BASE, len(COARSE), len(BEHAVIORS)).to(DEVICE)
    collate = make_collate(tok)
    dl = DataLoader(DS(tr), batch_size=BS, shuffle=True, collate_fn=collate)
    dlt = DataLoader(DS(te), batch_size=64, collate_fn=collate)

    bpos = np.array([sum(r["behaviors"][j] for r in tr) for j in range(len(BEHAVIORS))])
    pw = torch.tensor((len(tr) - bpos) / np.maximum(bpos, 1), dtype=torch.float).to(DEVICE)
    ce = nn.CrossEntropyLoss(label_smoothing=0.05, reduction="none")
    bce = nn.BCEWithLogitsLoss(pos_weight=pw)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    steps = len(dl) * EPOCHS
    sched = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)

    def evaluate():
        model.eval()
        P, T, PB, TB, PROB = [], [], [], [], []
        with torch.no_grad():
            for enc, yi, yb, _ in dlt:
                enc = {k: v.to(DEVICE) for k, v in enc.items()}
                li, lb = model(**enc)
                P.append(li.argmax(1).cpu().numpy())
                T.append(yi.numpy())
                PROB.append(F.softmax(li, 1).max(1).values.cpu().numpy())
                PB.append((torch.sigmoid(lb).cpu().numpy() >= 0.5).astype(int))
                TB.append(yb.numpy().astype(int))
        return (
            np.concatenate(P),
            np.concatenate(T),
            np.concatenate(PB),
            np.concatenate(TB),
            np.concatenate(PROB),
        )

    best, best_state = -1, None
    for ep in range(EPOCHS):
        model.train()
        tot = 0.0
        for enc, yi, yb, cw in dl:
            enc = {k: v.to(DEVICE) for k, v in enc.items()}
            yi, yb, cw = yi.to(DEVICE), yb.to(DEVICE), cw.to(DEVICE)
            li, lb = model(**enc)
            loss = (ce(li, yi) * cw).mean() + BEHAVIOR_W * bce(lb, yb)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            tot += loss.item()
        P, T, PB, TB, _ = evaluate()
        acc = (P == T).mean()
        bmf1 = np.mean(
            [f1_score(TB[:, j], PB[:, j], zero_division=0) for j in range(len(BEHAVIORS))]
        )
        score = (acc + bmf1) / 2
        print(
            f"epoch {ep + 1}/{EPOCHS} loss={tot / len(dl):.3f} intent_acc={acc:.3f} behav_mF1={bmf1:.3f} score={score:.3f}"
        )
        if score > best:
            best = score
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    P, T, PB, TB, PROB = evaluate()
    print(f"\n=== COARSE INTENT acc={(P == T).mean():.3f} ===")
    print(classification_report(T, P, target_names=COARSE, digits=3, zero_division=0))
    print("=== BEHAVIORS ===")
    for j, b in enumerate(BEHAVIORS):
        print(
            f"{b:16s} P={precision_score(TB[:, j], PB[:, j], zero_division=0):.2f} "
            f"R={recall_score(TB[:, j], PB[:, j], zero_division=0):.2f} "
            f"F1={f1_score(TB[:, j], PB[:, j], zero_division=0):.2f}"
        )
    print("=== SELECTIVE PREDICTION (intent) ===")
    order = np.argsort(-PROB)
    corr = (P == T).astype(int)
    for cov in [1.0, 0.9, 0.8, 0.7]:
        k = int(len(order) * cov)
        sel = order[:k]
        print(
            f"  coverage {int(cov * 100)}%  acc={100 * corr[sel].mean():.1f}%  (p>={PROB[sel].min():.2f})"
        )
    torch.save(
        {
            "base": BASE,
            "sep": SEP,
            "maxlen": MAXLEN,
            "intents": COARSE,
            "behaviors": BEHAVIORS,
            "state_dict": best_state,
            "coarse": True,
        },
        OUT,
    )
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
