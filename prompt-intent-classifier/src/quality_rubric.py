"""Prompt-quality rubric, few-shot, and structured-output schema.

Grades a single developer prompt against 4 best-practice dimensions (1-5 each).
Single source of truth for the scorer (score_quality.py), same pattern as
taxonomy.py for the labeler.

Dimensions:
  - clarity:      is the task unambiguous (a single, clearly-stated ask)?
  - specificity:  are output requirements constrained (format, scope,
                   acceptance criteria, what "done" looks like)?
  - structure:    are instructions given in a logical order (context ->
                   task -> constraints, steps in a sane sequence)?
  - robustness:   does the prompt account for input variations / edge cases /
                   error conditions the assistant should handle?

overall_score / tier are computed in Python from the 4 ints (score_quality.py),
not asked of the model, to keep the schema enum-only per the structured-output
limits noted in taxonomy.py.
"""

DIMENSIONS = ["clarity", "specificity", "structure", "robustness"]

TOP_ISSUES = [
    "none",
    "ambiguous_task",
    "unconstrained_output",
    "poor_structure",
    "not_robust",
]

_SCALE = {"type": "string", "enum": ["1", "2", "3", "4", "5"]}

SCHEMA = {
    "type": "object",
    "properties": {
        "clarity": _SCALE,
        "specificity": _SCALE,
        "structure": _SCALE,
        "robustness": _SCALE,
        "top_issue": {"type": "string", "enum": TOP_ISSUES},
        "suggestion": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": [
        "clarity",
        "specificity",
        "structure",
        "robustness",
        "top_issue",
        "suggestion",
        "confidence",
    ],
    "additionalProperties": False,
}

SYSTEM = """You score software-developer prompts sent to an AI coding assistant \
(Claude Code) against 4 prompt-engineering best-practice dimensions, for an \
outsourcing company that wants to coach developers toward better prompts. You are \
an objective grader, NOT judging the developer as a person.

Score each dimension 1-5 (use the anchors literally; do not default to 3):

clarity — is the task unambiguous (a single, clearly-stated ask)?
  1: no clear task, or the goal is unstated ("fix it", "make it better")
  3: a task is identifiable but some ambiguity remains about what exactly is wanted
  5: one clearly-stated, unambiguous task

specificity — are output requirements constrained (format, scope, acceptance \
criteria, what "done" looks like)?
  1: no constraints on the output at all
  3: an output shape is implied but not stated explicitly
  5: output requirements are explicit (format, scope, acceptance criteria, or an
     expected result)

structure — are instructions given in a logical order (context -> task -> \
constraints, steps in a sane sequence)?
  1: rambling or disordered; multiple asks with no discernible order, or context
     that contradicts/comes after the task confusingly
  3: mostly ordered but with a jump or an out-of-place detail
  5: clear logical sequence a reader can follow in one pass

robustness — does the prompt account for input variations / edge cases / error \
conditions the assistant should handle?
  1: no mention of edge cases, variations, or error handling, where they would matter
  3: edge cases are implied but not enumerated
  5: edge cases, input variations, or error conditions are explicitly named
  NOTE: if the task is inherently trivial/single-path (e.g. a pure comprehension
  question with no edge cases to speak of), score robustness 5 — do not penalize
  a prompt for not inventing edge cases that don't apply.

Rules:
- Be objective and conservative: if a dimension is not clearly met at a level, score it lower.
- NEVER infer competence, effort, or personality; you are scoring the PROMPT, not the person.
- top_issue: the SINGLE lowest-scoring dimension that most limits how actionable this prompt
  is, mapped to its issue tag ("none" only if every dimension scores 4 or 5).
- suggestion: one short, concrete sentence on how to rewrite the prompt to fix top_issue.
  Empty string if top_issue is "none".
- confidence reflects how sure you are about these scores."""

FEWSHOT = [
    {
        "prompt": "make it better",
        "label": {
            "clarity": "1",
            "specificity": "1",
            "structure": "1",
            "robustness": "1",
            "top_issue": "ambiguous_task",
            "suggestion": "State what 'it' refers to and what outcome 'better' means (e.g. faster, fewer errors, cleaner API).",
            "confidence": "high",
        },
    },
    {
        "prompt": "parseAmount returns 0 when the input has a thousands separator; the bug only shows once the value reaches 4 digits. Fix it so 1,234 parses to 1234, and add a regression test covering values with and without separators.",
        "label": {
            "clarity": "5",
            "specificity": "5",
            "structure": "5",
            "robustness": "4",
            "top_issue": "none",
            "suggestion": "",
            "confidence": "high",
        },
    },
    {
        "prompt": "the dashboard feels slow lately, can you look into it",
        "label": {
            "clarity": "2",
            "specificity": "1",
            "structure": "2",
            "robustness": "1",
            "top_issue": "unconstrained_output",
            "suggestion": "Name which dashboard/page, what 'slow' means (load time, a specific action), and what result would count as fixed.",
            "confidence": "medium",
        },
    },
    {
        "prompt": "also add a PDF export, email it to the admin nightly, and while you're at it clean up the report page styling",
        "label": {
            "clarity": "2",
            "specificity": "2",
            "structure": "1",
            "robustness": "1",
            "top_issue": "poor_structure",
            "suggestion": "Split into separate prompts: PDF export, the nightly email job, and the styling cleanup, each with its own acceptance criteria.",
            "confidence": "high",
        },
    },
    {
        "prompt": "write a function that parses a CSV row into an Invoice object. Fields are id (int), amount (decimal, may be empty), and date (ISO-8601). Handle: empty amount -> null, malformed date -> raise InvalidRowError, and extra trailing columns -> ignore. Return the parsed Invoice or raise.",
        "label": {
            "clarity": "5",
            "specificity": "5",
            "structure": "5",
            "robustness": "5",
            "top_issue": "none",
            "suggestion": "",
            "confidence": "high",
        },
    },
    {
        "prompt": "does validateSession get called when the gateway forwards a request from the public router?",
        "label": {
            "clarity": "5",
            "specificity": "4",
            "structure": "5",
            "robustness": "5",
            "top_issue": "none",
            "suggestion": "",
            "confidence": "high",
        },
    },
    {
        "prompt": "refactor the auth module",
        "label": {
            "clarity": "2",
            "specificity": "1",
            "structure": "2",
            "robustness": "1",
            "top_issue": "unconstrained_output",
            "suggestion": "Name what specifically should change (e.g. extract token validation into its own function) and what must stay behaviorally identical.",
            "confidence": "medium",
        },
    },
]


def build_user_content(prompt: str) -> str:
    """Render the per-prompt user message."""
    return f"PROMPT TO SCORE:\n{prompt[:4000]}"


def fewshot_messages() -> list[dict]:
    """Few-shot as alternating user/assistant turns (assistant turns are JSON scores)."""
    import json

    msgs = []
    for ex in FEWSHOT:
        msgs.append({"role": "user", "content": build_user_content(ex["prompt"])})
        msgs.append({"role": "assistant", "content": json.dumps(ex["label"])})
    return msgs


def overall_score(scores: dict) -> int:
    """0-100 from the 4 per-dimension ints (equal weight)."""
    total = sum(int(scores[d]) for d in DIMENSIONS)
    return round(total / (5 * len(DIMENSIONS)) * 100)


def tier(score: int) -> str:
    if score < 40:
        return "poor"
    if score < 60:
        return "fair"
    if score < 80:
        return "good"
    return "excellent"
