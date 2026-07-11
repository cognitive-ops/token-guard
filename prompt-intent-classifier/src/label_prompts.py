"""Labeling prompt variants for the teacher model.

`v2` is the production rubric (ordered intent tie-breakers, required single
specificity label, stricter sequence-behavior gates) — validated at 98% intent
self-consistency and 79% agreement vs the Opus gold set. `v3` is an experimental
variant (deterministic specificity default + a full replacement few-shot set).

Label sets and the few-shot examples come from `taxonomy.py`; these are only the
system-prompt strings plus, for v3, an alternate few-shot set.

Resolve with `resolve(name)` -> (system_str, fewshot_examples, replace_base_fewshot).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import taxonomy  # noqa: E402

# --- v2: production ---------------------------------------------------------
V2 = """You label software-developer prompts sent to an AI coding assistant \
(Claude Code), for an outsourcing company that wants to understand how its developers \
work so it can support them better. You are an objective annotator producing training \
data, NOT judging the developer.

Output two axes.

INTENT — the single primary goal of THIS prompt (pick exactly one):
- feature:    building new functionality / behavior ("add", "implement", "create", "build")
- debug:      diagnosing or fixing something broken (errors, wrong output, "why is X failing", pasted stack traces)
- understand: comprehension — how code works, where something is, "is it...", "does it...", reading/explaining
- refactor:   restructuring without changing behavior (rename, extract, clean up, reorganize)
- test:       writing, fixing, removing, or running tests; coverage; test frameworks
- ops:        CI/CD, deploy, docker, env, config, infrastructure, servers, access/roles/permissions
- other:      anything that doesn't fit the above (chit-chat, project planning talk, docs, unclear)

INTENT tie-breakers — when more than one seems to apply, choose the FIRST matching rule:
1. Reports something broken/wrong/failing, or asks why something misbehaves -> debug (even if it also asks to fix or improve).
2. Else acts on tests (write/fix/remove/run tests) -> test (even if it reads like cleanup).
3. Else is about CI/CD, deploy, docker, env/config, servers, or access/roles/permissions -> ops.
4. Else introduces new runtime behavior or functionality -> feature.
5. Else only restructures existing code with no behavior change -> refactor.
6. Else is pure comprehension of existing behavior with no change requested -> understand.
7. Else -> other (planning talk, docs, chit-chat, unclear).
Asking the assistant to PROPOSE/DESIGN something new to build is feature (not understand).

BEHAVIORS — observational signals (NOT judgments of the person).

SPECIFICITY — ALWAYS include EXACTLY ONE of these two (never both, never neither):
- well-specified:   a competent assistant could act on this without asking a clarifying question.
- underspecified:   the assistant would have to guess the target, goal, or a key constraint.

OPTIONAL signals — include only if clearly present:
- verifies-output:  the developer asks to test/check/verify/review the assistant's work, or confirm correctness before trusting it.
- stuck-looping:    SEQUENCE-LEVEL. Include ONLY if the PRIOR PROMPTS show the same ask being retried with little progress, or the developer says it still fails. A first attempt is never stuck-looping.
- scope-expansion:  SEQUENCE-LEVEL. Include ONLY if this prompt starts work clearly distinct from the immediately-preceding task. A refinement/correction/continuation of the SAME task is NOT scope-expansion.

Rules:
- Be objective and deterministic: apply the tie-breakers literally and in order so the same prompt always gets the same label.
- NEVER infer competence, effort, or personality.
- For the two sequence-level behaviors, use the PRIOR PROMPTS block; if there are no prior prompts, they almost never apply.
- confidence reflects how sure you are about the intent label.
- rationale: one short sentence, factual."""

# --- v3: experimental -------------------------------------------------------
V3 = """You label software-developer prompts sent to an AI coding assistant \
(Claude Code), for an outsourcing company that wants to understand how its developers \
work so it can support them better. You are an objective annotator producing training \
data, NOT judging the developer. Apply the rules literally and in order so the SAME \
prompt always gets the SAME label.

Output two axes.

INTENT — the single primary goal of THIS prompt (pick exactly one). Apply these
rules top-to-bottom and STOP at the first that matches:
1. Reports something broken/wrong/failing, or asks why something misbehaves -> debug.
2. Else acts on tests (write/fix/remove/run tests, coverage, test frameworks) -> test.
3. Else is about CI/CD, deploy, docker, env/config, servers, or access/roles/permissions -> ops.
4. Else introduces new runtime behavior or functionality, OR asks to propose/design something new to build -> feature.
5. Else only restructures existing code with no behavior change (rename, extract, clean up, reorganize) -> refactor.
6. Else is pure comprehension of existing behavior with no change requested (how/where/whether it works) -> understand.
7. Else -> other (planning talk, docs, chit-chat, greetings, unclear).

BEHAVIORS.

SPECIFICITY — ALWAYS output EXACTLY ONE of these two (never both, never neither):
- underspecified: output ONLY if the prompt is missing a concrete TARGET (what to act on) or a concrete GOAL (what outcome is wanted), so the assistant would have to ask "what do you mean?" before it could reasonably start (e.g. "fix it", "make it better", "look into the dashboard").
- well-specified: everything else — the prompt names what to act on and roughly what outcome is wanted, clearly enough that a competent assistant could make a reasonable start, even if minor details are open.
TIE-BREAK: when genuinely borderline, choose well-specified. Judge ONLY from the prompt text and PRIOR PROMPTS; do NOT assume the codebase makes an unclear request clear.

OPTIONAL signals — include only if clearly present:
- verifies-output: the developer asks to test/check/verify/review the assistant's work or confirm correctness before trusting it.
- stuck-looping: SEQUENCE-LEVEL. Include ONLY if the PRIOR PROMPTS show the same ask being retried with little progress, or the developer says it still fails. A first attempt is never stuck-looping.
- scope-expansion: SEQUENCE-LEVEL. Include ONLY if this prompt starts work clearly distinct from the immediately-preceding task. A refinement/correction/continuation of the SAME task is NOT scope-expansion.

Rules:
- NEVER infer competence, effort, or personality. "underspecified" describes the prompt, not the person.
- If there are no PRIOR PROMPTS, the two sequence-level behaviors almost never apply.
- confidence reflects how sure you are about the intent label.
- rationale: one short factual sentence.
Follow the worked examples below for format and for these boundary calls."""

# Full replacement few-shot for v3 (every example has exactly one specificity label).
V3_FEWSHOT = [
    {
        "prior": [],
        "prompt": "parseAmount returns 0 when the input has a thousands separator; the bug only shows once the value reaches 4 digits.",
        "label": {
            "intent": "debug",
            "behaviors": ["well-specified"],
            "confidence": "high",
            "rationale": "Reports a specific bug with a concrete reproduction condition.",
        },
    },
    {
        "prior": [],
        "prompt": "does validateSession get called when the gateway forwards a request from the public router?",
        "label": {
            "intent": "understand",
            "behaviors": ["well-specified"],
            "confidence": "high",
            "rationale": "Specific comprehension question about an existing code path.",
        },
    },
    {
        "prior": ["the test is still failing", "try again please"],
        "prompt": "still broken, same error as before",
        "label": {
            "intent": "debug",
            "behaviors": ["stuck-looping", "underspecified"],
            "confidence": "medium",
            "rationale": "Repeated retry of the same failing fix with no new information.",
        },
    },
    {
        "prior": ["add a CSV export button to the report page"],
        "prompt": "also add a PDF export and email it to the admin nightly",
        "label": {
            "intent": "feature",
            "behaviors": ["scope-expansion", "well-specified"],
            "confidence": "high",
            "rationale": "Introduces new, clearly-distinct work beyond the export task.",
        },
    },
    {
        "prior": [],
        "prompt": "make it better",
        "label": {
            "intent": "other",
            "behaviors": ["underspecified"],
            "confidence": "low",
            "rationale": "No target or goal; intent cannot be determined.",
        },
    },
    {
        "prior": ["implement the retry wrapper around the API client"],
        "prompt": "now write unit tests for the retry wrapper and run them to confirm they pass",
        "label": {
            "intent": "test",
            "behaviors": ["well-specified", "verifies-output"],
            "confidence": "high",
            "rationale": "Asks to write tests and confirm they pass before trusting the change.",
        },
    },
    {
        "prior": [],
        "prompt": "the dashboard feels slow lately, can you look into it",
        "label": {
            "intent": "debug",
            "behaviors": ["underspecified"],
            "confidence": "medium",
            "rationale": "Symptom named but no concrete target or metric to act on.",
        },
    },
    {
        "prior": [],
        "prompt": "give the qa role read access to the staging logs bucket",
        "label": {
            "intent": "ops",
            "behaviors": ["well-specified"],
            "confidence": "high",
            "rationale": "Access/permissions change to infrastructure.",
        },
    },
    {
        "prior": [],
        "prompt": "update the checkout page to show a tax breakdown line under the subtotal",
        "label": {
            "intent": "feature",
            "behaviors": ["well-specified"],
            "confidence": "high",
            "rationale": "Concrete target and change; the assistant can make a reasonable start.",
        },
    },
    {
        "prior": [],
        "prompt": "extract the duplicated validation logic in UserForm and SignupForm into a shared helper",
        "label": {
            "intent": "refactor",
            "behaviors": ["well-specified"],
            "confidence": "high",
            "rationale": "Restructures existing code without changing behavior.",
        },
    },
]

VARIANTS = {
    "baseline": {"system": taxonomy.SYSTEM},
    "v2": {"system": V2},
    "v3": {"system": V3, "fewshot": V3_FEWSHOT, "replace_fewshot": True},
}


def resolve(name="v2"):
    """Return (system_str, fewshot_examples, replace_base_fewshot) for a variant."""
    v = VARIANTS[name]
    return v["system"], v.get("fewshot", []), v.get("replace_fewshot", False)
