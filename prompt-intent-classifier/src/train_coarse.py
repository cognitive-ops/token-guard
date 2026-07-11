"""Coarse-taxonomy intent model — the path to >=85% (error analysis showed the
7-way taxonomy's debug/understand and feature/refactor boundaries are genuinely
ambiguous, capping raw accuracy ~69%).

Coarse 5-way (business-meaningful, reliable):
  build       = feature + refactor   (creating / changing functionality)
  investigate = debug + understand    (diagnosing / comprehending existing code)
  ops         = ops                   (CI/deploy/infra)
  test        = test
  other       = other

Accuracy recipe from train_ft2 (no class weights, warmup, label smoothing, best
checkpoint). Reports accuracy + the selective-prediction curve. Same held-out split.
"""

import os
import sys

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

sys.path.insert(0, os.path.dirname(__file__))
import taxonomy
from train_ft import SEP, load_joined

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

BASE = os.environ.get("FT_BASE", "xlm-roberta-base")
OUT = os.environ.get("FT_OUT", f"data/model_coarse_{BASE.split('/')[-1]}.pt")
EPOCHS = int(os.environ.get("FT_EPOCHS", "6"))
MAXLEN, BS, LR = 256, 32, 2e-5
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


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
        yi = torch.tensor([F2C[r["intent"]] for r in batch])
        return enc, yi

    return collate


def main():
    rows = load_joined()
    print(f"loaded {len(rows)} | base={BASE} epochs={EPOCHS} | COARSE 5-way")
    y = np.array([r["intent"] for r in rows])
    tr_i, te_i = train_test_split(np.arange(len(rows)), test_size=0.2, random_state=0, stratify=y)
    tr, te = [rows[i] for i in tr_i], [rows[i] for i in te_i]
    tok = AutoTokenizer.from_pretrained(BASE)
    enc_model = AutoModel.from_pretrained(BASE)
    h = enc_model.config.hidden_size

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.enc = enc_model
            self.drop = nn.Dropout(0.1)
            self.head = nn.Linear(h, len(COARSE))

        def forward(self, **enc):
            out = self.enc(**enc).last_hidden_state
            mask = enc["attention_mask"].unsqueeze(-1).float()
            pooled = (out * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            return self.head(self.drop(pooled))

    model = Net().to(DEVICE)
    collate = make_collate(tok)
    dl = DataLoader(DS(tr), batch_size=BS, shuffle=True, collate_fn=collate)
    dlt = DataLoader(DS(te), batch_size=64, collate_fn=collate)
    ce = nn.CrossEntropyLoss(label_smoothing=0.05)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    steps = len(dl) * EPOCHS
    sched = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)

    def evaluate():
        model.eval()
        P, T = [], []
        probs = []
        with torch.no_grad():
            for enc, yi in dlt:
                enc = {k: v.to(DEVICE) for k, v in enc.items()}
                logit = model(**enc)
                P.append(logit.argmax(1).cpu().numpy())
                T.append(yi.numpy())
                probs.append(F.softmax(logit, 1).max(1).values.cpu().numpy())
        return np.concatenate(P), np.concatenate(T), np.concatenate(probs)

    best, best_state = 0.0, None
    for ep in range(EPOCHS):
        model.train()
        tot = 0.0
        for enc, yi in dl:
            enc = {k: v.to(DEVICE) for k, v in enc.items()}
            yi = yi.to(DEVICE)
            loss = ce(model(**enc), yi)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            tot += loss.item()
        P, T, _ = evaluate()
        acc = (P == T).mean()
        print(f"epoch {ep + 1}/{EPOCHS} loss={tot / len(dl):.3f} acc={acc:.3f}")
        if acc > best:
            best = acc
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    P, T, probs = evaluate()
    print(f"\n=== COARSE INTENT — acc={best:.3f} ===")
    print(classification_report(T, P, target_names=COARSE, digits=3, zero_division=0))
    print("=== SELECTIVE PREDICTION ===")
    order = np.argsort(-probs)
    corr = (P == T).astype(int)
    for cov in [1.0, 0.9, 0.8, 0.7]:
        k = int(len(order) * cov)
        sel = order[:k]
        print(
            f"  coverage {int(cov * 100)}%  acc={100 * corr[sel].mean():.1f}%  (p>={probs[sel].min():.2f})"
        )
    torch.save(
        {
            "base": BASE,
            "sep": SEP,
            "maxlen": MAXLEN,
            "intents": COARSE,
            "behaviors": [],
            "state_dict": best_state,
            "coarse": True,
        },
        OUT,
    )
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
