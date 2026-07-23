# Prompt Intent & Behavior Classifier — Solution & Architecture

Status doc, derived from code in this dir (`src/`, `dvc.yaml`, `Makefile`, `deploy-model/`)
as of 2026-07-23. Companion to [README.md](README.md), [PIPELINE.md](PIPELINE.md),
[EVAL.md](EVAL.md), [PATTERNS.md](PATTERNS.md), [LABEL_RELIABILITY.md](LABEL_RELIABILITY.md).

## 1. Problem

Token Guard's analytics stack (`../CLAUDE.md`) captures every `user_prompt` a developer
sends to Claude Code, into Loki. Raw text isn't a metric. This subproject turns each
prompt into two structured signals an org can chart per-developer/per-team:

- **intent** — what the prompt is trying to do (`build`/`investigate`/`ops`/`test`/`other`)
- **behaviors** — multi-label quality/process signals (`well-specified`, `underspecified`,
  `verifies-output`, `stuck-looping`, `scope-expansion`)

Constraint that shapes everything below: the **inference target is a 2 vCPU / 7.6 GB RAM /
13 GB disk box** already running the rest of the analytics stack, and it must run **hourly,
forever, at ~$0 marginal cost**. Calling an LLM API per-prompt at inference time was
rejected on cost/footprint grounds — the design instead trains a small local model once.

## 2. Solution shape: LLM-teacher → local-student distillation

```
OFFLINE (this repo) — run occasionally, costs money once
──────────────────────────────────────────────────────────────────────────
  Loki (user_prompt)
        │
        v
  extract_prompts_full.py   (SSM tunnel, manual)
        │
        v
  clean_dataset.py           [DVC stage 1]
        │
        v
  scrub_secrets.py (gitleaks)[DVC stage 2]
        │
        v
  labelable.jsonl  (secret-free)
        │
        v
  label.py / label_batch.py  (Sonnet 4.6, structured output)
        │
        v
  labeled.jsonl ──────────────► gold_set.py (Opus 4.8 gold-set QA)
        │
        v
  train_coarse_mt.py         (xlm-roberta-base, multi-task)
        │
        v
  export_onnx.py             (fp32 + int8)
        │
        v
  tune_thresholds.py         (per-behavior F1 tuning)
        │
        v
  deploy-model/  (onnx + tokenizer + meta.json)
        │
        │  git / LFS
        v
──────────────────────────────────────────────────────────────────────────
ONLINE (production box) — runs hourly, ~free
──────────────────────────────────────────────────────────────────────────
  Loki (user_prompt, live) ──┐
                              v
                        classify_onnx.py  (onnxruntime + tokenizers only)
                              │
                              v
                        prompt-intent-exporter  (Prometheus gauges)
```

The offline half is a classic **distillation** pipeline: an expensive, accurate teacher
(Sonnet 4.6, occasionally checked against Opus 4.8) labels a corpus once; a cheap student
(a 278 MB transformer, quantized to ~135 MB) is trained to imitate it and does the
recurring work for free. This repo *is* the offline half; `prompt-intent-exporter`
(sibling dir, see `../CLAUDE.md`) is the online half that polls Loki hourly and calls
`classify_onnx.py`.

## 3. Data pipeline (DVC) — sensitivity-graded stages

Prompts are the org's most sensitive telemetry (may contain secrets, proprietary code,
PII). The pipeline is a strict one-way sensitivity funnel, enforced by DVC's cache
policy rather than convention alone — see [`PIPELINE.md`](PIPELINE.md).

| Stage | Script | Sensitivity | DVC caching |
|---|---|---|---|
| 0. extract | `extract_prompts_full.py` | raw, SENSITIVE | dep only — never an output, never cached/pushed |
| 1. clean | `clean_dataset.py` | SENSITIVE (pre-scrub) | `cache: false` — stays local |
| 2. scrub | `scrub_secrets.py` (gitleaks) | **secret-free** | cached, the only stage safe to `dvc push` |

Stage 0 needs a prod SSM tunnel to Loki (`:3100`), so it's manual, not `dvc repro`. Stages
1–2 are deterministic and reproducible via `make data`.

**Stage 1 (`clean_dataset.py`)** does the real filtering work, delegating categorization to
`preprocess.py`:
- merges every `data/raw/*.jsonl`, dedups by `prompt_id` (prefers the richer-metadata copy),
  drops rows with a scrambled/non-ISO timestamp (corrupted Loki export rows)
- **`preprocess.categorize()`** buckets every event into `real` / `control` (slash-command
  or short confirmation, regex-only, no LLM) / `injected` (harness blocks like
  `<observed_from_primary_session>`, `<task-notification>` — not user-written, dropped) /
  `empty`. Per [`PATTERNS.md`](PATTERNS.md), only **79.1%** of raw `user_prompt` events are
  real classifiable text — skipping this stage would poison the dataset with ~21% noise
  and needlessly cost 21% more in labeling spend.
- reconstructs **session order** (`session_id`, sorted by `event_sequence`) and attaches
  each real prompt's last-5 prior prompts as context — required for the two
  sequence-level behaviors (`stuck-looping`, `scope-expansion`)
- strips low-signal noise (punctuation-only, <3 chars, multilingual confirmation words in
  a 30-entry allowlist covering French/Spanish/German/Russian/Portuguese) and dedups by
  `(normalized text, last-5 prior prompts)`

**Stage 2 (`scrub_secrets.py`)** shells out to `gitleaks` per row. Notably it scans **prompt
+ prior_prompts together**, not just the prompt — a secret pasted in an earlier turn rides
along in later rows' context and must flag those rows too. Flagged prompt_ids go to
`secret_quarantine_ids.txt` (ids only, no leaked content, kept as an audit trail); the temp
dir holding raw text is always deleted in a `finally` block.

## 4. Taxonomy & the teacher (`taxonomy.py`, `label_batch.py`)

`taxonomy.py` is the single source of truth for the rubric — imported by both the
smoke-test labeler (`label_test.py`) and the production batch labeler, so what's reviewed
by a human is exactly what ships.

- **Intent** (one per prompt, fine-grained v1): `feature` `debug` `understand` `refactor`
  `test` `ops` `other`
- **Behaviors** (multi-label, zero or more): `well-specified` `underspecified`
  `verifies-output`, plus two **sequence-level** ones judged from prior turns:
  `stuck-looping`, `scope-expansion`
- **Structured output**: a strict JSON schema (enums + array-of-enum only) forces the
  teacher to emit `{intent, behaviors, confidence, rationale}` — no parsing of free text.
- **Few-shot**: 6 hand-picked, paraphrased real-shape examples embedded as alternating
  user/assistant turns, covering each intent and behavior at least once.
- **Cost control**: prompt caching on the system+few-shot prefix (`~$0.0013/prompt`), the
  **Batch API** (50% off) for the full-corpus run (`label_batch.py submit`/`fetch`,
  ~$28 for 9.7k prompts on Sonnet 4.6), and the stage-1 filtering that cuts volume ~21%
  before any LLM call.

**Teacher choice: Sonnet 4.6.** Quality is checked two ways, both recorded as
traceable aggregate-only metrics (no prompt content committed):
- *Self-consistency* ([LABEL_RELIABILITY.md](LABEL_RELIABILITY.md)): two independent Sonnet
  passes over the same 9,652 prompts agree **94.7%** on intent, 92.5–98.9% per-behavior.
  This is the ceiling — no student can be more "right" than the teacher is consistent with
  itself.
- *Cross-model accuracy* ([EVAL.md](EVAL.md)): a 198-prompt Opus 4.8 gold set agrees with
  Sonnet only **77.3%** on intent — the gap is genuine taxonomy fuzziness (concentrated in
  `ops`/`other`/`feature`/`understand`), not run-to-run noise. This finding is what
  motivated the coarse 5-way taxonomy in §5.

## 5. Taxonomy v2: fine → coarse collapse

Error analysis (`error_analysis.py`, summarized in EVAL.md) showed the `debug`/`understand`
and `feature`/`refactor` boundaries are ambiguous even to a clean-agreement subset (70.9%
accuracy ceiling). Rather than relabel, the 7-way taxonomy is **merged post-hoc** into a
5-way one at train time (`train_coarse_mt.py`):

```
build       = feature + refactor
investigate = debug + understand
ops         = ops            (unchanged)
test        = test            (unchanged)
other       = other           (unchanged)
```

This is a free accuracy lever — same labels, no new labeling cost — because it removes the
taxonomy's fuzziest internal boundary rather than asking the model to resolve it. Effect
(EVAL.md): full-coverage intent accuracy 69.2% (7-way) → **75.7%** (5-way); at 70% selective
coverage, 79.3% → **84.4%**.

## 6. Student model (`train_coarse_mt.py`)

**Architecture**: `xlm-roberta-base` encoder + two linear heads sharing the `[CLS]`
representation — a standard multi-task setup (`MultiTask` class, defined in `train_ft.py`
and reused here):
- intent head: 5-way softmax (coarse taxonomy)
- behavior head: 5-way independent sigmoid (multi-label)

**Input framing**: `prev_prompt + " >>> " + current_prompt` (the `SEP` constant), truncated
to 256 tokens — this is how sequence-level behavior signal (stuck-looping, scope-expansion)
reaches a model that otherwise sees one example at a time, without needing a
session-level/recurrent architecture.

**Why xlm-roberta-base, not English MiniLM**: 15.8% of real prompts are non-ASCII
(Russian, Indonesian, and others per PATTERNS.md) — an English-only encoder would silently
fail on a sixth of the corpus.

**Training recipe** (the "v5 / coarse_mt" recipe, the accumulated best-of from
`train_ft` → `train_ft3` → `train_coarse_mt`):
- **Confidence-weighted loss**: the teacher's own `confidence` field (high/medium/low)
  downweights the cross-entropy loss for labels Sonnet itself was unsure about
  (`CW = {high: 1.0, medium: 0.7, low: 0.3}`) — a soft way to discount noisy labels
  without discarding them.
- **`pos_weight` on the BCE behavior loss**, computed from the training split's own
  class balance — behaviors are individually rare (e.g. `verifies-output` at ~5% positive
  per LABEL_RELIABILITY.md), so unweighted BCE would collapse to always-negative.
- Label smoothing (0.05), linear warmup + decay schedule, gradient clipping, `AdamW`.
- **Grouped, stratified split**: `StratifiedGroupKFold` grouped by `session_id` — prevents
  same-session prompts (which share vocabulary/topic) leaking between train and held-out
  test, which would inflate reported accuracy.
- **Best-checkpoint selection** on `(intent_acc + behavior_macro_F1) / 2`, not just intent
  accuracy — keeps the behavior head from being sacrificed for a marginally better epoch
  on intent alone.
- Reports a **selective-prediction curve** (accuracy at 100/90/80/70% coverage) every run —
  abstention is a first-class deployment lever here, not an afterthought (§8).

Held-out results (EVAL.md, coarse 5-way, xlm-roberta-base): **75.7%** intent accuracy at
100% coverage, **84.4%** at 70% coverage; `investigate` F1 0.85 (dominant class), `test`
(n=30 in the split) the main drag.

## 7. Export & runtime (`export_onnx.py`, `classify_onnx.py`)

The trained checkpoint (`.pt`, torch+transformers, ~1.1 GB with the 250k-token XLM-R
vocab) is unsuitable for the target box: `pip install torch` alone risks pulling ~5 GB
(the "CUDA-torch disk trap," explicitly called out in EVAL.md) against a 13 GB disk budget.

`export_onnx.py` traces the model (`torch.onnx.export`, opset 17, legacy TorchScript
exporter — avoids an `onnxscript` dependency) to `model.onnx`, then applies **int8 dynamic
weight quantization** (`quantize_dynamic`) to `model.int8.onnx`. Quantizing the embedding
table (not just linear layers) is what gets the file down to **135 MB** — the 119k-token
multilingual vocab is otherwise the size floor (~360 MB), per EVAL.md.

**Deployed footprint**: `onnxruntime` + `tokenizers` only — no `torch`, no `transformers` —
~215 MB of installs + 135 MB model ≈ **~350 MB total**, vs ~3 GB for the torch path.
Accuracy is preserved through quantization (ONNX int8 predictions match the torch model,
per EVAL.md); CPU latency **~32 ms/prompt** on 2 threads, so an hourly batch of a few
hundred prompts finishes in seconds and a full 9.7k-prompt backfill takes ~5 min.

`classify_onnx.py` is deliberately tiny and stateless-after-first-call: lazy-loads
session/tokenizer/meta once into module globals (`_load()`), pins
`intra_op_num_threads=2` to match the 2-vCPU box, and exposes one function,
`classify_onnx(prompt, prev="")`, returning
`{intent, intent_confidence, top_intent, behaviors}`.

## 8. Selective prediction (abstention) — the accuracy lever that needs no retraining

Two independently-tuned abstention layers, both encoded in `deploy-model/meta.json`:

1. **Intent**: softmax confidence on the winning class vs `intent_threshold` (default
   `0.67`). Below threshold, emit `"unclassified"` instead of a low-confidence guess.
   Per EVAL.md this trades coverage for accuracy along a documented curve — e.g. the coarse
   model reaches **84.4%** accuracy at 70% coverage vs 75.7% at 100%. For analytics
   *aggregates* (counts per team/intent), the abstained bucket is small and unbiased enough
   to just report alongside the rest.
2. **Behaviors**: `tune_thresholds.py` finds a per-behavior sigmoid cutoff that maximizes
   F1 (default 0.5 is a poor prior — heads are high-recall/low-precision), using an
   **honest split-in-half protocol**: tune on one half of the held-out test set (grouped by
   session again, `GroupShuffleSplit`), report the gain on the other half the thresholds
   were never fit to. Thresholds are written into `meta.json.behavior_thresholds`
   (currently: well-specified 0.46, underspecified 0.52, stuck-looping 0.76,
   verifies-output 0.80, scope-expansion 0.70 — see `deploy-model/meta.json`) and consumed
   directly by `classify_onnx.py`.

## 9. Deployed artifact contract

`deploy-model/` is the entire runtime contract, versioned via Git LFS (per `make deploy`):

| File | Role |
|---|---|
| `model.int8.onnx` | quantized weights, ~135 MB |
| `tokenizer.json` | HF fast-tokenizer, self-contained (no `AutoTokenizer`/network needed) |
| `meta.json` | `base`, `sep`, `maxlen`, `intents[]`, `behaviors[]`, `source_model`, `behavior_thresholds{}` — the only thing a consumer needs besides the two files above |

`prompt-intent-exporter` (sibling service, see `../CLAUDE.md`) is the sole production
consumer: polls Loki hourly, calls `classify_onnx()` per new prompt, writes
`claude_prompt_{intent,behavior}_count{...,user_email}` Prometheus gauges. This repo has
no HTTP surface of its own — it produces a portable model bundle, nothing more.

## 10. Reproducibility & promotion path

```
make data     # dvc repro: raw -> clean -> scrub  (offline, needs Loki tunnel for stage 0)
make prep     # extract + submit label batch        (costs money, non-deterministic)
              # ... wait for Anthropic batch ...
make model    # fetch labels -> train -> export -> tune thresholds
make deploy   # copy data/onnx/{model.int8.onnx,tokenizer.json,meta.json} -> deploy-model/
              # then: git add deploy-model && git commit  (manual, reviewed)
```

`TRAIN_SCRIPT` (default `train_coarse_mt.py`) and `EXPORT_MODEL` are Makefile-overridable
to swap in `train_ft3.py` (7-way fine alternative) without touching the script. Labeling
and extraction are intentionally kept **out** of `dvc.yaml` — they cost real money and are
non-deterministic (LLM calls, prod tunnel access), so they're documented manual steps
instead of pipeline stages that `dvc repro` might silently re-trigger.

## 11. Known limitations / open work (from EVAL.md's own assessment)

- **Taxonomy ceiling, not model ceiling**: full-coverage accuracy plateaus ~69–76% because
  of genuine label ambiguity (proven by stratifying accuracy on Sonnet's own confidence:
  77.2% on high-confidence labels vs 55.4% on low). A still-coarser 3–4-way taxonomy is the
  documented next lever for full-coverage 85%.
  - **`other` and `ops` boundaries** drive most cross-model disagreement and are flagged for
  a taxonomy v2 rubric pass.
- **Sequence-level behaviors are the noisiest signal**: `stuck-looping`/`scope-expansion`
  have the lowest cross-model agreement (Sonnet over-tags both vs Opus gold: P0.42/P0.23).
- **Rare classes underfit**: `test` (n=30 in held-out) and `refactor` remain the weakest
  per-class F1s — more labeled examples for these, not more model capacity, is the
  prescribed fix.
- **Footprint floor is the multilingual vocab** (~360 MB even after quantization); a
  reduced-vocabulary multilingual encoder (e.g. Geotrend) is noted as a possible sub-400 MB
  path, contingent on verifying it still covers Russian/Indonesian/Vietnamese coverage
  found in the real corpus.
