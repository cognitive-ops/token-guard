"""Load the trained student model and classify prompts locally (no API, no cost).

This is the function the production exporter will call per prompt. It mirrors the
training featurization exactly (context-augmented embedding + numeric features).
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

MODEL_OUT = "data/model.joblib"
_BUNDLE = None
_EMBEDDER = None


def _load():
    global _BUNDLE, _EMBEDDER
    if _BUNDLE is None:
        import joblib
        from sentence_transformers import SentenceTransformer

        _BUNDLE = joblib.load(MODEL_OUT)
        _EMBEDDER = SentenceTransformer(_BUNDLE["embed_model"])
    return _BUNDLE, _EMBEDDER


def classify(prompt: str, prev_prompt: str = "", n_prior: int = 0, behavior_threshold: float = 0.5):
    """Return {intent, behaviors, intent_proba} for one prompt."""
    b, emb = _load()
    aug = (prev_prompt + b["sep"] + prompt) if prev_prompt else prompt
    vecs = emb.encode([aug, prompt, prev_prompt or prompt], normalize_embeddings=True)
    sim = float(np.dot(vecs[1], vecs[2])) if prev_prompt else 0.0
    num = b["scaler"].transform([[np.log1p(len(prompt)), min(n_prior, 20), sim]])
    X = np.hstack([vecs[0:1], num])
    intent = b["intent"].predict(X)[0]
    proba = float(b["intent"].predict_proba(X).max())
    behaviors = [
        name
        for name, clf in b["behaviors"].items()
        if clf.predict_proba(X)[0, 1] >= behavior_threshold
    ]
    return {"intent": intent, "behaviors": behaviors, "intent_proba": round(proba, 3)}


if __name__ == "__main__":
    for p, prev in [
        ("add a dark-mode toggle to the settings page", ""),
        ("still failing with the same error", "fix the login bug"),
        ("also add CSV export while you're at it", "build the report table"),
        ("how does the auth middleware decide which routes to protect?", ""),
    ]:
        print(f"{p[:50]:50s} -> {classify(p, prev)}")
