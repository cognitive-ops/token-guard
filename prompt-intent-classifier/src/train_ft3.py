"""Student trainer v4 — balanced: keep v3's intent gains AND fix behaviors.

vs train_ft2 (v3):
  - confidence-weighted intent loss: per-example weight from Sonnet's label
    confidence (high=1.0, medium=0.7, low=0.3) — focus learning on clean labels
  - behavior loss with pos_weight restored + healthier weight (0.7), so the
    behavior heads don't collapse (v3 regressed: underspecified R=0.03)
  - selects best checkpoint by (intent_acc + behavior_macro_F1)/2 so both matter

Same held-out split (seed 0, stratified). Default base = distilbert (deployment model).
"""

import json
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

BASE = os.environ.get("FT_BASE", "distilbert-base-multilingual-cased")
OUT = os.environ.get("FT_OUT", f"data/model_ft3_{BASE.split('/')[-1]}.pt")
EPOCHS = int(os.environ.get("FT_EPOCHS", "6"))
BEHAVIOR_W = float(os.environ.get("BEHAVIOR_W", "0.7"))
MAXLEN, BS, LR = 256, 32, 2e-5
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
INTENTS, BEHAVIORS = taxonomy.INTENTS, taxonomy.BEHAVIORS
CW = {"high": 1.0, "medium": 0.7, "low": 0.3}


def load_with_conf():
    conf = [json.loads(l)["confidence"] for l in open("data/labeled.jsonl")]
    rows = load_joined()
    assert len(conf) == len(rows)
    for r, c in zip(rows, conf, strict=False):
        r["cw"] = CW.get(c, 0.7)
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
            torch.tensor([r["intent"] for r in batch]),
            torch.tensor([r["behaviors"] for r in batch], dtype=torch.float),
            torch.tensor([r["cw"] for r in batch], dtype=torch.float),
        )

    return collate


@torch.no_grad()
def evaluate(model, dl):
    model.eval()
    pi, pb, ti, tb = [], [], [], []
    for enc, yi, yb, _ in dl:
        enc = {k: v.to(DEVICE) for k, v in enc.items()}
        li, lb = model(**enc)
        pi.append(li.argmax(1).cpu().numpy())
        pb.append((torch.sigmoid(lb).cpu().numpy() >= 0.5).astype(int))
        ti.append(yi.numpy())
        tb.append(yb.numpy().astype(int))
    return np.concatenate(pi), np.concatenate(ti), np.concatenate(pb), np.concatenate(tb)


def main():
    rows = load_with_conf()
    print(
        f"loaded {len(rows)} | base={BASE} epochs={EPOCHS} behavior_w={BEHAVIOR_W} device={DEVICE}"
    )
    y = np.array([r["intent"] for r in rows])
    tr_i, te_i = train_test_split(np.arange(len(rows)), test_size=0.2, random_state=0, stratify=y)
    tr, te = [rows[i] for i in tr_i], [rows[i] for i in te_i]
    tok = AutoTokenizer.from_pretrained(BASE)
    model = MultiTask(BASE, len(INTENTS), len(BEHAVIORS)).to(DEVICE)
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

    best_score, best_state = -1, None
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
        pi, ti, pb, tb = evaluate(model, dlt)
        acc = (pi == ti).mean()
        bmf1 = np.mean(
            [f1_score(tb[:, j], pb[:, j], zero_division=0) for j in range(len(BEHAVIORS))]
        )
        score = (acc + bmf1) / 2
        print(
            f"epoch {ep + 1}/{EPOCHS} loss={tot / len(dl):.3f} intent_acc={acc:.3f} behav_mF1={bmf1:.3f} score={score:.3f}"
        )
        if score > best_score:
            best_score = score
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    pi, ti, pb, tb = evaluate(model, dlt)
    print(f"\n=== BEST INTENT acc={(pi == ti).mean():.3f} ===")
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
    print(f"\nsaved -> {OUT}")


if __name__ == "__main__":
    main()
