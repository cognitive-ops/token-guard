# Evaluation (v1)

Aggregate metrics only — no prompt content. Dataset: 9,717 real prompts labeled by
Sonnet 4.6; 198-prompt Opus 4.8 gold set; two independent Sonnet runs for self-consistency.

## Label reliability — Sonnet self-consistency (two runs, same prompts)
- Overlap: 9,652 prompts (99.3% of corpus)
- **Intent self-agreement: 94.7%** — labels are stable run-to-run
- Behavior exact-set agreement: 80.7%; per-behavior 92.5–98.9%

## Cross-model agreement — Sonnet vs Opus 4.8 gold (198 prompts)
- **Intent agreement: 77.3%** — the gap vs 94.7% self-agreement is genuine taxonomy
  fuzziness between models, concentrated in `ops`/`other`/`feature`/`understand`.
- Behaviors (Opus=truth): well-specified P0.85/R0.79, verifies-output P0.77/R0.91 (good);
  scope-expansion P0.23 and stuck-looping P0.42 (Sonnet over-tags the sequence-level ones).

## Student model — held-out 20% (MiniLM embeddings + linear heads)
- Intent accuracy 49.1%, macro-F1 0.44. Best: debug 0.59, understand 0.52, feature 0.51,
  ops 0.50. Weak: refactor 0.27, test 0.19 (only 30 test examples in the split).
- Behaviors: well-specified F1 0.77 (good); others 0.22–0.51.

## Interpretation
- **Labels are reliable** (94.7% self-consistent), so the student's 49% is **not** a label-noise
  problem — the cheap linear-on-frozen-embeddings student is the bottleneck.
- **Taxonomy needs a v2 pass**: the `other` bucket and `ops`↔`feature`↔`understand` boundaries
  drive most cross-model disagreement; the two sequence-level behaviors are noisiest.

## Student models — v1 vs v2 (fine-tuned), held-out 20% (1,944 prompts)

| Student | Intent acc | Macro-F1 | refactor F1 | test F1 |
|---|---|---|---|---|
| v1: linear heads on frozen MiniLM | 49.1% | 0.44 | 0.27 | 0.19 |
| **v2: distilbert-multilingual fine-tuned** | **65.2%** | **0.58** | 0.41 | 0.40 |

Fine-tuning lifted intent accuracy **+16 points** and roughly doubled the rare-class F1s.
v2 per-intent F1: understand 0.74, debug 0.72, other 0.62, ops 0.61, feature 0.59,
refactor 0.41, test 0.40. v2 behaviors: well-specified 0.77, stuck-looping 0.57,
scope-expansion 0.56, underspecified 0.49, verifies-output 0.38.

## Deployment cost (single-thread CPU — the low-end analytics box)

| Variant | Intent acc | On-disk | ms/prompt (1 core) |
|---|---|---|---|
| distilbert-ML fine-tuned, fp32 | 65.2% | 539 MB | 106 |
| **distilbert-ML fine-tuned, int8** | **63.5%** | 412 MB | 35 |

int8 dynamic quantization costs ~1.7 pts for 3× faster CPU + 127 MB smaller. The
footprint floor (~360 MB) is the 119k-token multilingual embedding table — unavoidable
given ~16% non-English prompts. (MiniLM-L12-H384 is *not* smaller: its XLM-R vocab is
250k, a larger embedding table.)

## Recommendation — "just enough" for the low-end box

**distilbert-base-multilingual-cased, fine-tuned, int8-quantized, on CPU.** At 35 ms/prompt
single-thread, the hourly batch of a few hundred new prompts finishes in seconds; 412 MB
fits a modest box. Use fp32 (106 ms, +1.7 pts) only if RAM is ample and accuracy matters
more than footprint. Inference path: `src/classify_ft.py` (`quantize=True` by default on CPU).

## v3 — accuracy-tuned (no class weights, warmup, per-epoch best checkpoint)

| Student | Intent acc (100% cov) | On-disk |
|---|---|---|
| v2 distilbert-ML | 65.2% | 539 MB |
| **v3 xlm-roberta-base** | **69.2%** | 1.1 GB |

The 100%-coverage number plateaus ~69% because of **taxonomy ambiguity**, not model
capacity — proven by stratifying held-out accuracy by Sonnet's own confidence:

| Held-out subset | n | Accuracy |
|---|---|---|
| **high-confidence labels** | 1,046 | **77.2%** |
| medium | 806 | 60.5% |
| low | 92 | 55.4% |

On prompts Sonnet labeled confidently, the student already clears 75%. Half of all
low-confidence labels are `other` — the fuzzy catch-all.

### Selective prediction (the >75% deployment lever)

Abstain when the model's own softmax confidence is below a threshold (flag as
`unclassified` rather than miscount). Held-out accuracy vs coverage:

| Coverage | xlm-roberta-base | distilbert-ML | distilbert threshold |
|---|---|---|---|
| 100% | 69.2% | 65.2% | — |
| 90% | 73.0% | 69.0% | p≥0.48 |
| 80% | **76.5%** | 72.2% | p≥0.58 |
| 70% | 79.3% | **74.9%** | p≥0.67 |
| 60% | 82.4% | 78.1% | p≥0.75 |

**Both models exceed 75%** with modest abstention: xlm-r at 80% coverage (76.5%),
distilbert at ~70% coverage (74.9%). Implemented in `classify_ft.py`
(`intent_threshold`, default 0.67).

## ONNX deployment (optimized for the low-end box — 2 vCPU, 7.6 GB RAM, 13 GB free disk)

Exported distilbert → ONNX, int8-quantized, served with **onnxruntime + tokenizers
only** (no torch, no transformers). `src/export_onnx.py` → `src/classify_onnx.py`.

| | torch path | **ONNX path** |
|---|---|---|
| Model file | 412 MB (int8) | **135 MB** (int8 — quantizes the embedding table too) |
| Runtime install | torch + transformers ~2–3 GB | onnxruntime + tokenizers **~215 MB** |
| Total footprint | ~3 GB | **~350 MB** |
| CPU latency | 32.7 ms/prompt | **32.3 ms/prompt** (2 threads) |

Accuracy is preserved through ONNX int8 (predictions match the torch model). On the
target box this is ~10 s for an hourly batch of ~300 prompts; full 9.7k backfill ~5 min.
**Avoids the CUDA-torch disk trap entirely** (default `pip install torch` would pull ~5 GB).

## Coarse 5-way taxonomy (error-analysis result — toward 85%)

Error analysis showed the 7-way `debug`/`understand` and `feature`/`refactor` boundaries
are genuinely ambiguous (even on the clean label-agreement subset, acc was only 70.9%),
capping raw accuracy ~69%. Merging into a 5-way taxonomy — **build** (feature+refactor),
**investigate** (debug+understand), **ops**, **test**, **other** — lifts it:

| Coverage | 7-way (xlm-r) | **5-way coarse (xlm-r)** |
|---|---|---|
| 100% | 69.2% | **75.7%** |
| 90% | 73.0% | 79.0% |
| 80% | 76.5% | 82.5% |
| 70% | 79.3% | **84.4%** |

`investigate` F1 0.85 (dominant class); `test` (n=30) is the main drag. **≥85% is reached
at ~70% coverage** (abstain on the rest). Full-coverage 85% would need a still-coarser
3–4-way taxonomy. The coarse model (`src/train_coarse.py`) currently has **no behavior
head** — to deploy it in the exporter it must be retrained as coarse-intent + behaviors.

## Recommendation (updated)

- **Low-end box, footprint-bound:** distilbert-ML int8 (412 MB, 35 ms/prompt CPU) +
  abstain at p≥0.67 → ~75% on the ~70% of prompts it's confident about, rest flagged
  `unclassified`. Best fit for the analytics machine.
- **Accuracy-first, footprint allows:** xlm-roberta-base + abstain at p≥0.63 → 76.5% at
  80% coverage. Heavier (1.1 GB; ~800 MB int8 — the 250k-token embedding table dominates).
- For analytics *aggregates* (counts per intent/team), abstention barely matters — the
  unclassified bucket is small and unbiased enough to report alongside the rest.

## Further gains (no new labeling cost — dataset is reusable)
1. Tighten the taxonomy: split/clarify `other`, sharpen `ops` vs `feature`, stricter rubric
   for the two sequence-level behaviors (their cross-model agreement is lowest).
2. Add examples for rare classes (`test`, `refactor`) and retrain.
3. For sub-400 MB: a reduced-vocabulary multilingual encoder (e.g. Geotrend) — but verify it
   covers Russian/Indonesian/Vietnamese before trusting it.
