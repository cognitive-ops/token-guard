"""Fine-tuned transformer student (multi-task) — the v2 student.

v1 used linear heads on frozen MiniLM embeddings (49% intent). Labels are 94.7%
self-consistent, so the cap is far higher — this fine-tunes the encoder end-to-end.

Architecture: one shared multilingual encoder + two heads
  - intent head:   7-way softmax (cross-entropy, class-weighted for imbalance)
  - behavior head: 5-way sigmoid (BCE, multilabel)
Input: context-augmented text (prev >>> current) so the two sequence-level
behaviors have signal. Same held-out split (seed 0, stratified) as v1.

Pure PyTorch (no Trainer/accelerate). Saves data/model_ft.pt + a report.
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
from transformers import AutoModel, AutoTokenizer

sys.path.insert(0, os.path.dirname(__file__))
import taxonomy

LABELED = "data/labeled.jsonl"
ITEMS = "data/label_items.jsonl"
BASE = os.environ.get("FT_BASE", "distilbert-base-multilingual-cased")
OUT = os.environ.get("FT_OUT", f"data/model_ft_{BASE.split('/')[-1]}.pt")
SEP = " >>> "
MAXLEN = 256
EPOCHS = int(os.environ.get("FT_EPOCHS", "4"))
BS = 32
LR = 2e-5
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
INTENTS, BEHAVIORS = taxonomy.INTENTS, taxonomy.BEHAVIORS
I2IDX = {v: i for i, v in enumerate(INTENTS)}


def load_joined():
    items = {json.loads(l)["prompt_id"]: json.loads(l) for l in open(ITEMS)}
    rows = []
    for l in open(LABELED):
        d = json.loads(l)
        it = items.get(d["prompt_id"], {})
        prior = it.get("prior_prompts") or []
        prev = prior[-1] if prior else ""
        text = (prev + SEP + (d["prompt"] or "")) if prev else (d["prompt"] or "")
        rows.append(
            {
                "text": text,
                "intent": I2IDX[d["intent"]],
                "behaviors": [1.0 if b in d["behaviors"] else 0.0 for b in BEHAVIORS],
                "session_id": d.get("session_id") or it.get("session_id"),
            }
        )
    return rows


class DS(Dataset):
    def __init__(self, rows, tok):
        self.rows, self.tok = rows, tok

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        enc = self.tok(
            r["text"], truncation=True, max_length=MAXLEN, padding="max_length", return_tensors="pt"
        )
        return (
            {k: v.squeeze(0) for k, v in enc.items()},
            torch.tensor(r["intent"]),
            torch.tensor(r["behaviors"]),
        )


class MultiTask(nn.Module):
    def __init__(self, base, n_intent, n_behav):
        super().__init__()
        self.enc = AutoModel.from_pretrained(base)
        h = self.enc.config.hidden_size
        self.drop = nn.Dropout(0.1)
        self.intent = nn.Linear(h, n_intent)
        self.behav = nn.Linear(h, n_behav)

    def forward(self, **enc):
        out = self.enc(**enc).last_hidden_state  # (B,T,H)
        mask = enc["attention_mask"].unsqueeze(-1).float()  # mean-pool
        pooled = (out * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        pooled = self.drop(pooled)
        return self.intent(pooled), self.behav(pooled)


def main():
    rows = load_joined()
    print(f"loaded {len(rows)} rows | device={DEVICE} | base={BASE}")
    y = np.array([r["intent"] for r in rows])
    tr_i, te_i = train_test_split(np.arange(len(rows)), test_size=0.2, random_state=0, stratify=y)
    tr = [rows[i] for i in tr_i]
    te = [rows[i] for i in te_i]

    tok = AutoTokenizer.from_pretrained(BASE)
    model = MultiTask(BASE, len(INTENTS), len(BEHAVIORS)).to(DEVICE)

    # class weights for intent (inverse frequency)
    counts = np.bincount([r["intent"] for r in tr], minlength=len(INTENTS))
    w = torch.tensor(counts.sum() / (len(INTENTS) * np.maximum(counts, 1)), dtype=torch.float).to(
        DEVICE
    )
    # pos_weight for behaviors (imbalance)
    bpos = np.array([sum(r["behaviors"][j] for r in tr) for j in range(len(BEHAVIORS))])
    pw = torch.tensor((len(tr) - bpos) / np.maximum(bpos, 1), dtype=torch.float).to(DEVICE)

    ce = nn.CrossEntropyLoss(weight=w)
    bce = nn.BCEWithLogitsLoss(pos_weight=pw)
    opt = torch.optim.AdamW(model.parameters(), lr=LR)
    dl = DataLoader(DS(tr, tok), batch_size=BS, shuffle=True)

    for ep in range(EPOCHS):
        model.train()
        tot = 0.0
        for enc, yi, yb in dl:
            enc = {k: v.to(DEVICE) for k, v in enc.items()}
            yi, yb = yi.to(DEVICE), yb.to(DEVICE)
            li, lb = model(**enc)
            loss = ce(li, yi) + bce(lb, yb)
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item()
        print(f"epoch {ep + 1}/{EPOCHS} loss={tot / len(dl):.3f}")

    # eval
    model.eval()
    dlt = DataLoader(DS(te, tok), batch_size=64)
    pi, pb, ti, tb = [], [], [], []
    with torch.no_grad():
        for enc, yi, yb in dlt:
            enc = {k: v.to(DEVICE) for k, v in enc.items()}
            li, lb = model(**enc)
            pi.append(li.argmax(1).cpu().numpy())
            pb.append((torch.sigmoid(lb).cpu().numpy() >= 0.5).astype(int))
            ti.append(yi.numpy())
            tb.append(yb.numpy().astype(int))
    pi, ti = np.concatenate(pi), np.concatenate(ti)
    pb, tb = np.concatenate(pb), np.concatenate(tb)

    print("\n=== INTENT (held-out 20%) ===")
    print(classification_report(ti, pi, target_names=INTENTS, digits=3, zero_division=0))
    print("=== BEHAVIORS (held-out 20%) ===")
    print(f"{'behavior':16s} {'P':>5} {'R':>5} {'F1':>5} {'support':>8}")
    for j, b in enumerate(BEHAVIORS):
        P = precision_score(tb[:, j], pb[:, j], zero_division=0)
        R = recall_score(tb[:, j], pb[:, j], zero_division=0)
        F = f1_score(tb[:, j], pb[:, j], zero_division=0)
        print(f"{b:16s} {P:5.2f} {R:5.2f} {F:5.2f} {int(tb[:, j].sum()):8d}")

    torch.save(
        {
            "base": BASE,
            "sep": SEP,
            "maxlen": MAXLEN,
            "intents": INTENTS,
            "behaviors": BEHAVIORS,
            "state_dict": model.state_dict(),
        },
        OUT,
    )
    print(f"\nsaved -> {OUT}")


if __name__ == "__main__":
    main()
