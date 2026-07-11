"""Taxonomy, labeling rubric, few-shot examples, and the structured-output schema.

This is the single source of truth for what we label and how. Both the test
labeler and the batch dataset build import from here, so the rubric the model
sees is exactly the one we reviewed.

Two axes (see PATTERNS.md / the plan doc):
  - intent:    one primary label per prompt
  - behaviors: zero or more, can co-occur. Two are sequence-level and need the
               prior prompts of the session as context (stuck-looping, scope-expansion).
"""

INTENTS = ["feature", "debug", "understand", "refactor", "test", "ops", "other"]
BEHAVIORS = [
    "well-specified",
    "underspecified",
    "stuck-looping",
    "verifies-output",
    "scope-expansion",
]

# Structured-output schema (json_schema). Enums + array-of-enum only — within
# the documented structured-output limits (no numeric/length constraints).
SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "behaviors": {"type": "array", "items": {"type": "string", "enum": BEHAVIORS}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "rationale": {"type": "string"},
    },
    "required": ["intent", "behaviors", "confidence", "rationale"],
    "additionalProperties": False,
}

SYSTEM = """You label software-developer prompts sent to an AI coding assistant \
(Claude Code), for an outsourcing company that wants to understand how its developers \
work so it can support them better. You are an objective annotator producing training \
data, NOT judging the developer.

Output two axes:

INTENT — the single primary goal of THIS prompt (pick exactly one):
- feature:    building new functionality / behavior ("add", "implement", "create", "build")
- debug:      diagnosing or fixing something broken (errors, wrong output, "why is X failing", pasted stack traces)
- understand: comprehension — how code works, where something is, "is it...", "does it...", reading/explaining
- refactor:   restructuring without changing behavior (rename, extract, clean up, reorganize)
- test:       writing or fixing tests, coverage, test frameworks
- ops:        CI/CD, deploy, docker, env, config, infrastructure, servers
- other:      anything that doesn't fit the above (chit-chat, project planning talk, docs, unclear)

BEHAVIORS — zero or more observational signals (NOT judgments of the person). \
A prompt can have several, or none:
- well-specified:   clear goal + enough context/constraints to act on; may include pasted code, file refs, error text
- underspecified:   vague or missing context; the assistant would have to guess what is meant ("fix it", "make it better")
- verifies-output:  the developer asks to test/check/verify/review the assistant's work, or confirm correctness before trusting it
- stuck-looping:    SEQUENCE-LEVEL. The developer is re-trying the same thing with little progress, or expressing that earlier attempts did not work ("still broken", "that didn't work", "again", repeated retries of the same ask). Judge using the prior prompts shown.
- scope-expansion:  SEQUENCE-LEVEL. This prompt adds work beyond what the session was doing ("also add...", "while you're at it", "one more thing", a new unrelated feature mid-task). Judge using the prior prompts shown.

Rules:
- Be objective and conservative. If a behavior is not clearly present, do not add it.
- NEVER infer competence, effort, or personality. "underspecified" describes the prompt, not the person.
- For the two sequence-level behaviors, use the PRIOR PROMPTS block; if there are no prior prompts, they almost never apply.
- confidence reflects how sure you are about the intent label.
- rationale: one short sentence, factual."""

# Few-shot examples (real prompt shapes from the corpus, lightly paraphrased).
FEWSHOT = [
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
            "behaviors": [],
            "confidence": "high",
            "rationale": "Asks how the existing code path behaves; comprehension only.",
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
            "behaviors": ["scope-expansion"],
            "confidence": "high",
            "rationale": "Introduces new work beyond the export task in progress.",
        },
    },
    {
        "prompt": "make it better",
        "prior": [],
        "label": {
            "intent": "other",
            "behaviors": ["underspecified"],
            "confidence": "low",
            "rationale": "No goal or context; intent cannot be determined.",
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
]


def build_user_content(prompt: str, prior_prompts: list[str]) -> str:
    """Render the per-prompt user message: prior session context + the target."""
    prior_block = (
        "\n".join(f"  {i + 1}. {p[:300]}" for i, p in enumerate(prior_prompts[-5:])) or "  (none)"
    )
    return (
        f"PRIOR PROMPTS in this session (oldest first), for the two sequence-level behaviors:\n"
        f"{prior_block}\n\n"
        f"PROMPT TO LABEL:\n{prompt[:4000]}"
    )


def fewshot_messages() -> list[dict]:
    """Few-shot as alternating user/assistant turns (assistant turns are JSON labels)."""
    import json

    msgs = []
    for ex in FEWSHOT:
        msgs.append({"role": "user", "content": build_user_content(ex["prompt"], ex["prior"])})
        msgs.append({"role": "assistant", "content": json.dumps(ex["label"])})
    return msgs
