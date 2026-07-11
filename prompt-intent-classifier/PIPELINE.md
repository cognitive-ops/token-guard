# Data pipeline (DVC)

Reproducible, secret-safe path from raw Loki prompts to a clean labelable corpus.

```
Stage 0 (manual)      Stage 1: clean            Stage 2: scrub
extract_prompts_full  clean_dataset.py          scrub_secrets.py (gitleaks)
   Loki + backups  →  data/raw/*.jsonl  →  data/interim/clean.jsonl  →  data/processed/labelable.jsonl
   (SENSITIVE)        (SENSITIVE, deps)     (SENSITIVE, cache:false)     (SECRET-FREE, cached)
```

`clean` + `scrub` are DVC stages (`dvc.yaml`); run them with `make data` (= `dvc repro`).

## Stages

| Stage | Script | In → Out | Notes |
|-------|--------|----------|-------|
| 0. extract *(manual)* | `src/extract_prompts_full.py` | Loki → `data/raw/loki_prompts.jsonl` | Needs a prod SSM tunnel to Loki on `:3100` (see repo `CLAUDE.md` / `prompt-explorer/`). Walks back in <30d windows over the full retention. Not a DVC stage because it needs prod access. Also drop any restored backup dumps into `data/raw/*.jsonl`. |
| 1. clean | `src/clean_dataset.py` | `data/raw/*.jsonl` → `data/interim/clean.jsonl` | Merge+dedup by `prompt_id`, drop scrambled rows, keep "real" prompts w/ prior context, strip noise (punct-only, <3 chars, multilingual confirmations), dedup by (text + context). |
| 2. scrub | `src/scrub_secrets.py` | `data/interim/clean.jsonl` → `data/processed/labelable.jsonl` (+ `secret_quarantine_ids.txt`) | Runs **gitleaks** per prompt; drops any prompt with a detected secret. Temp files holding raw secrets are always deleted. Requires `gitleaks` on PATH. |

## Run

```bash
cd prompt-intent-classifier
# Stage 0 (once, with the Loki tunnel up):
python src/extract_prompts_full.py
# Stages 1–2 (deterministic, offline):
make data          # == dvc repro
```

`data/processed/labelable.jsonl` is the clean, deduped, **secret-free** corpus that feeds labeling/training.

## Sensitive-data policy

`data/` is gitignored, so no prompt text is ever in git. Within DVC:

- **`data/raw/**`** — declared as pipeline *dependencies* only, never a tracked output → never enters the DVC cache or a remote.
- **`data/interim/clean.jsonl`** — output with **`cache: false`** → may still contain secrets, so it stays local and is never pushed.
- **`data/processed/**`** — gitleaks-scrubbed and secret-free → the only artifacts safe to cache and `dvc push`.
- The one-off restored backup archive is excluded via `.dvcignore`.
- `dvc.lock` records **only md5 hashes + sizes**, never prompt content.

**Rule of thumb:** only ever `dvc push` `data/processed/`. Raw and interim never leave the machine. The configured remote (`storage`) is an SSE-KMS S3 bucket restricted to a small allow-list of principals; only the secret-free `data/processed/**` is pushed.

## Labeling (Stage 3 — manual, expensive)

Not a `dvc repro` stage (it costs real money and is non-deterministic), so it's a documented manual step like extract:

```bash
set -a; . ../.env; set +a            # ANTHROPIC_API_KEY
python src/label.py probe            # verify prompt caching engages (~$0.01)
python src/label.py run              # -> data/processed/labeled.jsonl (checkpointed, resumable)
dvc add data/processed/labeled.jsonl && dvc push
```

- Teacher/config via env: `LABELER_MODEL` (default `claude-sonnet-5`), `LABELER_VARIANT` (`v2`), `LABELER_THINKING` (`off`), `WORKERS`.
- The prompt lives in `src/label_prompts.py` (`v2` = production rubric; `v3` = experimental). Prompt caching on the system+few-shot prefix keeps cost ~$0.0013/prompt.
- `labeled.jsonl` is secret-free (derived from the scrubbed `labelable.jsonl`), so it's safe to push.

## Evaluation (how the prompt/config were chosen)

```bash
python src/eval_consistency.py sample && python src/eval_consistency.py run && python src/eval_consistency.py score   # run-to-run self-agreement (no caching)
python src/eval_accuracy.py          # variant vs the Opus gold set (intent agreement + behavior P/R)
python src/eval_batch_size.py        # does N-per-call batching degrade vs 1/call?
```

All honor `LABELER_MODEL` / `LABELER_VARIANT` / `LABELER_THINKING` and write artifacts under `data/eval/` (gitignored).
