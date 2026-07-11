# Label reliability — Sonnet 4.6 self-agreement (traceable record)

Aggregate metrics only (no prompt content). This records the run-to-run consistency
of the teacher labels, so the dataset's quality can be traced back later.

## Provenance

| Field | Value |
|---|---|
| Date computed | 2026-06-09 |
| Teacher model | `claude-sonnet-4-6` |
| Labeling | Batch API, structured output (forced JSON schema), `effort: low` |
| Rubric / schema | `src/taxonomy.py` (v1 taxonomy) |
| **Run 1 batch id** | `msgbatch_01VauTR4YTsrEt6UEEP5SyMx` — ended 2026-06-09 04:37:25 UTC, **9,666 succeeded** |
| **Run 2 batch id** | `msgbatch_019CyhvpkLW4r7HjZ2bvRchC` — ended 2026-06-09 04:43:56 UTC, **9,703 succeeded** |
| Reproduce | `src/label_reliability.py` (recomputes the table below from the two batch ids) |

> Run 2 was an unintended duplicate submission; it is reused here as an independent
> second labeling pass to measure self-consistency. Both runs labeled the same prompt
> set (same `prompt_id` custom_ids) with identical system/rubric/schema.

## Method

Two independent Sonnet 4.6 passes over the same prompts. Compared on the **intersection**
of prompt_ids that succeeded in both runs. "Agreement" = the two runs produced the same
label. This is the **upper bound on how well any student model can score against these
labels** — a student cannot be more right than the labels are self-consistent.

## Coverage

| | count |
|---|---|
| Run 1 succeeded | 9,666 |
| Run 2 succeeded | 9,703 |
| **Overlap compared (N)** | **9,652** (99.3% of the 9,717-prompt corpus) |

## Intent self-agreement (one label per prompt)

| Metric | Count | Rate |
|---|---|---|
| **Intent agreement** | **9,137 / 9,652** | **94.66%** |

## Behavior self-agreement (multi-label)

Agreement = both runs agree on presence/absence of that tag. `run_pos` = how many of
the 9,652 each run tagged positive.

| Behavior | Agree | Rate | run1_pos | run2_pos |
|---|---|---|---|---|
| well-specified | 8,926 / 9,652 | 92.48% | 4,850 | 4,790 |
| underspecified | 8,930 / 9,652 | 92.52% | 1,876 | 1,948 |
| stuck-looping | 9,386 / 9,652 | 97.24% | 1,532 | 1,594 |
| verifies-output | 9,543 / 9,652 | 98.87% | 492 | 503 |
| scope-expansion | 9,111 / 9,652 | 94.39% | 1,891 | 2,006 |
| **exact-set (all 5 match)** | **7,793 / 9,652** | **80.74%** | — | — |

## Interpretation

- Intent labels are **94.66%** self-consistent → reliable; label noise is low.
- Therefore a student scoring well below ~95% intent is **model-limited, not label-limited**
  (v1 linear student scored 49% — see [`EVAL.md`](EVAL.md)).
- Each behavior is individually ≥92% consistent; the 80.7% exact-set figure is lower only
  because it requires all five to match simultaneously.

Cross-model agreement (Sonnet vs Opus 4.8 gold, 198 prompts = 77.3% intent) is recorded
separately in [`EVAL.md`](EVAL.md); that lower number reflects genuine taxonomy boundary
fuzziness between models, not run-to-run noise.
