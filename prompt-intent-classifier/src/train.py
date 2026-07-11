"""Train the local student model from the Sonnet-labeled dataset.

Architecture (the cheap, interpretable, retrain-in-seconds option):
  features = multilingual-MiniLM embedding of a context-augmented text
             (prev prompt >>> current prompt)  ++  [log length, #prior, sim-to-prev]
  intent   = one multinomial LogisticRegression
  behaviors= one binary LogisticRegression per label (multilabel)

Context augmentation + sim-to-prev give the linear heads the signal they need
for the two sequence-level behaviors (stuck-looping, scope-expansion).

Outputs: data/model.joblib  + an evaluation report on a held-out split.
"""

import json
import os
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(__file__))
import taxonomy

LABELED = "data/labeled.jsonl"
ITEMS = "data/label_items.jsonl"
MODEL_OUT = "data/model.joblib"
EMBED_MODEL = (
    "paraphrase-multilingual-MiniLM-L12-v2"  # multilingual: ~16% of prompts are non-English
)
SEP = "\n>>>\n"


def load_joined():
    items = {json.loads(l)["prompt_id"]: json.loads(l) for l in open(ITEMS)}
    rows = []
    for l in open(LABELED):
        d = json.loads(l)
        it = items.get(d["prompt_id"])
        if not it:
            continue
        prior = it.get("prior_prompts") or []
        rows.append(
            {
                "prompt": d["prompt"] or "",
                "prev": (prior[-1] if prior else ""),
                "n_prior": len(prior),
                "intent": d["intent"],
                "behaviors": set(d["behaviors"]),
            }
        )
    return rows


def featurize(rows, embedder):
    aug = [(r["prev"] + SEP + r["prompt"]) if r["prev"] else r["prompt"] for r in rows]
    # cache: embed the union of aug-texts, prompts, prevs once
    uniq = list(set(aug) | {r["prompt"] for r in rows} | {r["prev"] for r in rows if r["prev"]})
    emb = embedder.encode(uniq, normalize_embeddings=True, batch_size=256, show_progress_bar=True)
    idx = {t: i for i, t in enumerate(uniq)}
    E_aug = np.array([emb[idx[t]] for t in aug])
    sim = []
    for r in rows:
        if r["prev"]:
            sim.append(float(np.dot(emb[idx[r["prompt"]]], emb[idx[r["prev"]]])))
        else:
            sim.append(0.0)
    num = np.array(
        [
            [np.log1p(len(r["prompt"])), min(r["n_prior"], 20), s]
            for r, s in zip(rows, sim, strict=False)
        ]
    )
    return E_aug, num


def main():
    import joblib
    from sentence_transformers import SentenceTransformer

    rows = load_joined()
    print(f"loaded {len(rows)} labeled rows")
    embedder = SentenceTransformer(EMBED_MODEL)
    E_aug, num = featurize(rows, embedder)
    scaler = StandardScaler().fit(num)
    X = np.hstack([E_aug, scaler.transform(num)])

    y_intent = np.array([r["intent"] for r in rows])
    idx = np.arange(len(rows))
    tr, te = train_test_split(idx, test_size=0.2, random_state=0, stratify=y_intent)

    # ---- intent ----
    clf_intent = LogisticRegression(max_iter=2000, C=2.0, class_weight="balanced")
    clf_intent.fit(X[tr], y_intent[tr])
    pred = clf_intent.predict(X[te])
    print("\n=== INTENT (held-out 20%) ===")
    print(classification_report(y_intent[te], pred, digits=3, zero_division=0))

    # ---- behaviors (one binary head each) ----
    behavior_clfs = {}
    print("=== BEHAVIORS (held-out 20%) ===")
    print(f"{'behavior':16s} {'P':>5} {'R':>5} {'F1':>5} {'support':>8} {'pos_rate':>9}")
    for b in taxonomy.BEHAVIORS:
        yb = np.array([1 if b in r["behaviors"] else 0 for r in rows])
        pos = int(yb.sum())
        clf = LogisticRegression(max_iter=2000, C=2.0, class_weight="balanced")
        clf.fit(X[tr], yb[tr])
        behavior_clfs[b] = clf
        pb = clf.predict(X[te])
        from sklearn.metrics import precision_score, recall_score

        P = precision_score(yb[te], pb, zero_division=0)
        R = recall_score(yb[te], pb, zero_division=0)
        F = f1_score(yb[te], pb, zero_division=0)
        print(f"{b:16s} {P:5.2f} {R:5.2f} {F:5.2f} {int(yb[te].sum()):8d} {pos / len(yb):9.3f}")

    joblib.dump(
        {
            "embed_model": EMBED_MODEL,
            "sep": SEP,
            "scaler": scaler,
            "intent": clf_intent,
            "behaviors": behavior_clfs,
            "intents": taxonomy.INTENTS,
            "behavior_labels": taxonomy.BEHAVIORS,
        },
        MODEL_OUT,
    )
    print(f"\nsaved model -> {MODEL_OUT}")


if __name__ == "__main__":
    main()
