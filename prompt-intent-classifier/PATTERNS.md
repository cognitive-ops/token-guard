# Corpus pattern study (real production data)

Source: local Loki restored from the online backup — **11,747** real `user_prompt`
events, 29-day window, 43 developers, 1,867 sessions.

## Key numbers

- **Length:** median 92 chars, but enormous spread — p75=301, p90=1,634, p99=19,709,
  max=62,414. Mean (1,029) is meaningless; the distribution is heavy-tailed.
- **Length buckets:** ultra-short <15 = 12.8%, short = 13.7%, medium = 31%,
  long = 21%, very-long 400+ = 21.5%.
- **Users:** 43 distinct. Heavy skew — top user 1,925 prompts, median 176, p90 570.
- **Sessions:** 1,867; median 3 prompts/session, p90=13, max=391. **73.7% of sessions
  have ≥2 prompts** → sequence-level tags (`stuck-looping`, `scope-expansion`) apply
  broadly.
- **Multilingual:** 15.8% of prompts contain non-ASCII; Russian, Indonesian and others
  are clearly present. The labeler and the local model must be language-agnostic.

## Composition (the important finding)

Only **79.1%** of `user_prompt` events are real, classifiable developer prompts. The
rest is noise that would poison a naive dataset:

| Category | Share | Handling |
|---|---|---|
| real developer prompt | 79.1% | **label these** |
| slash-command (`/clear`, `/plan`, `/mcp`, `/add-dir`, …) | 7.6% | regex-tag as `control`; no LLM |
| injected/harness (`<observed_from_primary_session>`, `<task-notification>`) | 7.0% | **exclude** — not user-written |
| confirmation (`yes`, `ok`, `1`, `go ahead`) | 2.7% | `control`; useful only as session context |
| ultra-short other | 3.7% | usually continuation; keep for context |

## Decisions forced by the data (updates to the plan)

1. **Add a preprocessing/filter stage** (was not in the original plan). Drop injected
   harness blocks, regex-route slash-commands and confirmations to a `control` bucket,
   and only send *real* prompts to the LLM labeler. This also cuts labeling cost ~21%.
2. **Heuristic intent distribution sanity-checks the taxonomy:** feature 25%, debug 16%,
   ops 12%, understand 9%, test 8%, review 7%, refactor 4% — the v1 intents map to real
   volume; none is empty, none dominates pathologically.
3. **Use a multilingual sentence-embedding model** for the local student
   (e.g. `paraphrase-multilingual-MiniLM-L12-v2`), not English-only MiniLM.
4. **Reconstruct sessions** by `session_id` ordered by `event_sequence` to give the
   labeler prior-turn context for `stuck-looping` / `scope-expansion`.
5. **Stratify the labeling sample** across length buckets and users so rare classes and
   quiet users aren't drowned out by the top-volume developers.
