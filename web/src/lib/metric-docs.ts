/**
 * Plain-language explanations for every metric shown in the dashboards — the
 * content behind the "(i)" buttons. Each entry says what the number means,
 * where the data comes from, and how it's computed, so a non-technical viewer
 * can trust and interpret it.
 *
 * Grounded in the real data model: OTEL telemetry (estimates), the
 * billing-exporter (real cost), and the Loki event/intent/behavior streams.
 */
export interface MetricDoc {
  title: string;
  what: string;
  source: string;
  calc: string;
  query?: string;
}

const OTEL = "Claude Code OpenTelemetry metrics → Prometheus.";
const LOKI = "Claude Code logs (user-prompt events) → Loki.";
const BILLING =
  "billing-exporter: Anthropic Admin Cost Report API + your seat roster → Prometheus.";

export const METRIC_DOCS = {
  // ---- Cost ----
  orgRealCost: {
    title: "Org Real Cost",
    what: "What Claude Code actually costs the organization — the authoritative figure, not the telemetry estimate.",
    source: BILLING,
    calc: "Sum of each developer's real cost: flat seat fee (Premium/Standard) + any metered overage. Service/automation API keys add their billed Cost-Report spend.",
    query: "claude_org_real_cost_total_usd",
  },
  serviceBilled: {
    title: "Service-key Billed",
    what: "Real, metered spend for service/automation API keys (CI, agents) — already discount-adjusted.",
    source: BILLING,
    calc: "Authoritative billed USD from the Anthropic Cost Report API for counted Claude Code workspaces.",
    query: "claude_service_billed_cost_total_usd",
  },
  otelEstimate: {
    title: "OTEL Estimate",
    what: "An ESTIMATE of cost (tokens × public list price). Not a bill — wrong for subscription seats and ignores cache/batch discounts.",
    source: OTEL,
    calc: "Sum of the per-call cost the CLI emits, increased over the selected window.",
    query: "sum(increase(claude_code_cost_usage_USD_total[range]))",
  },
  seats: {
    title: "Seats (Premium / Standard)",
    what: "Number of paid Claude Code seats by tier. Premium includes Claude Code; Standard does not.",
    source: BILLING,
    calc: "Counted from your seat roster.",
    query: "claude_seat_count",
  },
  costPerMTokens: {
    title: "Cost / 1M Tokens",
    what: "Estimated cost efficiency per million tokens — the unit model pricing is quoted in (per-1k rounds to $0.00).",
    source: OTEL,
    calc: "OTEL cost ÷ total tokens × 1,000,000 over the window.",
  },
  costPerPrompt: {
    title: "Cost / Prompt",
    what: "Estimated cost per user prompt.",
    source: `${OTEL} ${LOKI}`,
    calc: "OTEL cost ÷ number of user-prompt events over the window.",
  },
  costPerCommit: {
    title: "Cost per Commit",
    what: "Estimated AI spend per git commit produced.",
    source: OTEL,
    calc: "OTEL cost ÷ commit count over the window.",
  },
  costPer1kLoc: {
    title: "Cost per 1000 LOC",
    what: "Estimated AI spend per thousand lines of code changed.",
    source: OTEL,
    calc: "OTEL cost ÷ lines of code × 1000 over the window.",
  },
  costPerActiveHour: {
    title: "Cost per Active Hour",
    what: "Estimated spend per hour of active Claude Code use.",
    source: OTEL,
    calc: "OTEL cost ÷ active hours over the window.",
  },
  extraUsage: {
    title: "Extra Usage (overage)",
    what: "Metered usage billed beyond a seat's flat allowance. $0 means the developer stayed within plan.",
    source: BILLING,
    calc: "Per-developer overage from the Cost Report API plus any manual entry from claude.ai billing.",
    query: "claude_dev_extra_usage_usd",
  },

  // ---- Usage / volume ----
  totalTokens: {
    title: "Total Tokens",
    what: "All tokens processed (input + output + cache read/creation).",
    source: OTEL,
    calc: "Sum of token usage over the window.",
    query: "sum(increase(claude_code_token_usage_tokens_total[range]))",
  },
  activeUsers: {
    title: "Active Users",
    what: "Distinct developers who incurred any usage in the window.",
    source: OTEL,
    calc: "Count of unique user emails with cost > 0.",
  },
  totalPrompts: {
    title: "Total Prompts",
    what: "Number of prompts developers sent to Claude Code.",
    source: LOKI,
    calc: "Count of user_prompt events over the window.",
    query: 'count_over_time({service_name="claude-code"} | event_name="user_prompt")',
  },
  sessions: {
    title: "Sessions",
    what: "Number of Claude Code sessions started.",
    source: OTEL,
    calc: "Sum of session count over the window.",
  },
  linesOfCode: {
    title: "Lines of Code",
    what: "Lines added/modified/removed by Claude Code.",
    source: OTEL,
    calc: "Sum of line-of-code count over the window.",
  },
  commits: {
    title: "Commits",
    what: "Git commits created during Claude Code sessions — not total git history. Commits made outside a Claude Code session aren't counted.",
    source: OTEL,
    calc: "Each session's commit counter is a separate, short-lived series; we take its peak (the session's final count) and sum across sessions. Reliable at ~30-day windows; short ranges can undercount because the sparse per-session counters expire ~3h after a session ends.",
    query: "sum(max_over_time(claude_code_commit_count_total[range]))",
  },
  pullRequests: {
    title: "Pull Requests",
    what: "Pull requests opened during Claude Code sessions — not total PR activity. PRs opened outside a Claude Code session aren't counted.",
    source: OTEL,
    calc: "Same per-session peak-then-sum method as Commits. Reliable at ~30-day windows; short ranges can undercount.",
    query: "sum(max_over_time(claude_code_pull_request_count_total[range]))",
  },
  activeHours: {
    title: "Active Hours",
    what: "Hours of active Claude Code interaction.",
    source: OTEL,
    calc: "Active-time seconds ÷ 3600 over the window.",
  },
  cacheEfficiency: {
    title: "Cache Efficiency",
    what: "How well context is reused. Higher is better (target > 10:1) — cache reads are far cheaper than re-creating context.",
    source: OTEL,
    calc: "cacheRead tokens ÷ cacheCreation tokens.",
  },
  pctNewCode: {
    title: "% Code that is New",
    what: "Share of changed lines that are additions vs. removals.",
    source: OTEL,
    calc: "added ÷ (added + removed) lines.",
  },

  // ---- Breakdowns ----
  costByModel: {
    title: "Cost by Model",
    what: "Estimated spend split across models (Haiku/Sonnet/Opus). Helps judge model fit.",
    source: OTEL,
    calc: "OTEL cost grouped by model over the window.",
  },
  tokensByType: {
    title: "Tokens by Type",
    what: "Token split: input, output, cache creation, cache read.",
    source: OTEL,
    calc: "Tokens grouped by type over the window.",
  },
  costByProject: {
    title: "Cost by Project",
    what: "Estimated spend per project/repository.",
    source: OTEL,
    calc: "OTEL cost grouped by project_name over the window.",
  },
  tokensByRepo: {
    title: "Tokens by Repository",
    what: "Token usage per repository. (We group by repository, not project_name — the project attribute is set on <1% of usage.)",
    source: OTEL,
    calc: "Tokens grouped by repository_fullname over the window.",
  },
  avgCostPerUser: {
    title: "Avg Cost per User",
    what: "Mean estimated spend across active developers.",
    source: OTEL,
    calc: "OTEL cost ÷ active users over the window.",
  },
  avgPromptsPerUser: {
    title: "Avg Prompts per User",
    what: "Mean prompts per active developer.",
    source: LOKI,
    calc: "Total prompts ÷ developers who prompted over the window.",
  },
  intentByDeveloper: {
    title: "Intent by developer",
    what: "Per-developer breakdown of what they use Claude Code for.",
    source: "Local classifier → Loki (claude-code-intent).",
    calc: "Intent counts grouped by user_email and intent.",
  },
  behaviorsByDeveloper: {
    title: "Behaviors by developer",
    what: "Per-developer prompting behaviors.",
    source: "Local classifier → Loki (claude-code-behavior).",
    calc: "Behavior counts grouped by user_email and behavior.",
  },
  promptLangByDeveloper: {
    title: "Prompt language by developer",
    what: "Languages each developer writes prompts in.",
    source: "prompt-lang-exporter → Prometheus.",
    calc: "Prompt-language counts grouped by user_email and language.",
  },
  promptsPerDev: {
    title: "Prompts per developer",
    what: "Engagement — top developers by prompt volume.",
    source: LOKI,
    calc: "user_prompt events grouped by user_email (top 30).",
  },
  cacheEffPerDev: {
    title: "Cache efficiency per developer",
    what: "Per-developer context-reuse ratio (higher is better).",
    source: OTEL,
    calc: "cacheRead ÷ cacheCreation tokens per user (top 30).",
  },
  locByType: {
    title: "Lines of Code by Type",
    what: "Lines added / modified / removed.",
    source: OTEL,
    calc: "Line count grouped by type over the window.",
  },
  promptsOverTime: {
    title: "Prompts over time",
    what: "Prompt volume trend.",
    source: LOKI,
    calc: "user_prompt events bucketed over the window.",
  },
  locOverTime: {
    title: "LOC over time",
    what: "Lines-of-code trend by type.",
    source: OTEL,
    calc: "Line count grouped by type, bucketed over the window.",
  },
  commitsPerPr: {
    title: "Commits per PR",
    what: "Average commits per pull request — a granularity signal.",
    source: OTEL,
    calc: "commits ÷ pull requests over the window.",
  },
  costByRepo: {
    title: "Cost by Repository",
    what: "Estimated spend per repository.",
    source: OTEL,
    calc: "OTEL cost grouped by repository_fullname over the window.",
  },
  costByTerminal: {
    title: "Cost by Terminal / IDE",
    what: "Where developers run Claude Code (VS Code, terminal, etc.).",
    source: OTEL,
    calc: "OTEL cost grouped by terminal_type over the window.",
  },
  costByGitHost: {
    title: "Cost by Git Host",
    what: "Estimated spend split by git host (GitHub, Gitea, …).",
    source: OTEL,
    calc: "OTEL cost grouped by repository_host over the window.",
  },
  promptLanguage: {
    title: "Prompt Language",
    what: "Natural language developers write prompts in.",
    source: "prompt-lang-exporter: langdetect over Loki prompts → Prometheus.",
    calc: "Prompt count grouped by detected language.",
    query: "sum by (language)(claude_prompt_language_count)",
  },
  toolUsage: {
    title: "Tool Usage (Agent = delegated)",
    what: "Which tools Claude invoked. A high Agent/Task share signals delegated, 'vibe-coding' style work.",
    source: LOKI,
    calc: "Count of tool_result events grouped by tool_name.",
  },
  requestSource: {
    title: "Request source (main vs subagent)",
    what: "Split of cost between the main agent and delegated subagents.",
    source: OTEL,
    calc: "OTEL cost grouped by query_source over the window.",
  },
  effort: {
    title: "Effort level",
    what: "Distribution of the CLI's effort/thinking level.",
    source: OTEL,
    calc: "OTEL cost grouped by effort over the window.",
  },
  subagentType: {
    title: "Subagent type usage",
    what: "Which named subagents are used most.",
    source: OTEL,
    calc: "OTEL cost grouped by agent_name (where set) over the window.",
  },
  sessionStart: {
    title: "Session start type",
    what: "How sessions begin: fresh, resumed, or continued.",
    source: OTEL,
    calc: "Session count grouped by start_type over the window.",
  },

  // ---- Intent / behavior (local classifier) ----
  intentMix: {
    title: "Intent mix",
    what: "What developers use Claude Code for (debugging, feature work, refactor, …).",
    source: "Local ONNX prompt-intent classifier → Loki (claude-code-intent). Prompt text never leaves the analytics box.",
    calc: "Count of classified intents over the window.",
  },
  behaviors: {
    title: "Behaviors",
    what: "Prompting behaviors detected (well-specified, verifies-output, underspecified, stuck-looping).",
    source: "Local classifier → Loki (claude-code-behavior).",
    calc: "Count of classified behaviors over the window.",
  },
  slashCommands: {
    title: "Slash commands",
    what: "Most-used slash commands / skills.",
    source: "Loki (claude-code-command).",
    calc: "Count of command events over the window (top 12).",
  },
  wellSpecified: {
    title: "Well-specified",
    what: "Share of prompts judged clear and well-scoped — a sign of good prompt craft.",
    source: "Local classifier → Loki.",
    calc: "well-specified behaviors ÷ classified prompts × 100.",
  },
  verifiesOutput: {
    title: "Verifies output",
    what: "Share of interactions where the developer checks/validates the result.",
    source: "Local classifier → Loki.",
    calc: "verifies-output behaviors ÷ classified prompts × 100.",
  },
  underspecified: {
    title: "Underspecified",
    what: "Share of prompts that were too vague — a coaching opportunity.",
    source: "Local classifier → Loki.",
    calc: "underspecified behaviors ÷ classified prompts × 100.",
  },
  stuckLooping: {
    title: "Stuck / looping",
    what: "Share of interactions where the developer appeared stuck or repeating.",
    source: "Local classifier → Loki.",
    calc: "stuck-looping behaviors ÷ classified prompts × 100.",
  },
  avgPromptLength: {
    title: "Avg prompt length",
    what: "Average characters per prompt over time — a rough proxy for prompt detail.",
    source: LOKI,
    calc: "Average of prompt_length across user_prompt events.",
  },

  // ---- Prompt refactoring linter ----
  refactorScore: {
    title: "Prompt lint score",
    what: "A rule-based 0-100 score of how clear, specific, and context-efficient a prompt is — not an LLM judgment, a deterministic heuristic.",
    source: "hooks/lint-prompt.sh (UserPromptSubmit) → Loki → prompt-refactor-exporter → Prometheus.",
    calc: "Clarity penalizes hedge words/run-ons; specificity rewards file paths, quoted identifiers, and explicit constraints; context efficiency rewards a high unique-word ratio and penalizes oversized pasted blocks relative to instruction text. Overall is the average of the three.",
    query: "avg by (axis)(claude_prompt_refactor_score)",
  },
  refactorPairs: {
    title: "Rephrase pairs",
    what: "Same-session prompts where a follow-up scored meaningfully better than the one before it — a detected rephrase.",
    source: "prompt-refactor-exporter.",
    calc: "Consecutive prompt_lint events in the same session, ≤5 min apart, with an overall-score improvement of ≥10 points.",
    query: "sum(claude_prompt_refactor_pairs_total)",
  },
  refactorSavedUsd: {
    title: "Est. $ saved",
    what: "An ESTIMATE of $ saved by rephrasing to a shorter/clearer prompt — not a measured cost, this stack has no real per-prompt cost data.",
    source: "prompt-refactor-exporter (token delta) × the org's real blended $/Mtok (Anthropic Admin API, same figure as the API Cost dashboard).",
    calc: "(before char_count − after char_count) ÷ 4 chars-per-token, summed across rephrase pairs, converted to $ via blendedPerMtok.",
  },
  refactorSavedSeconds: {
    title: "Est. latency saved",
    what: "An ESTIMATE of response time saved by rephrasing — not measured. This stack emits no latency/duration metric at all; this is a rough token-throughput approximation.",
    source: "prompt-refactor-exporter.",
    calc: "Estimated tokens saved ÷ TOKENS_PER_SECOND (default 60, a configurable rough constant, not a measurement).",
    query: "sum(claude_prompt_refactor_saved_seconds)",
  },
  refactorTopRephrasers: {
    title: "Top rephrasers",
    what: "Developers with the most detected rephrase pairs.",
    source: "prompt-refactor-exporter.",
    calc: "topk(10, claude_prompt_refactor_pairs_total). user_email here is a local `git config user.email` value read by the hook — best-effort, may not match the org-verified identity used elsewhere (Keycloak/Admin API).",
    query: "topk(10, claude_prompt_refactor_pairs_total)",
  },

  // ---- Leaderboard / per-developer ----
  leaderboard: {
    title: "Developer leaderboard",
    what: "Engagement and output per developer — prompts, sessions, active hours, commits, PRs, tokens, cache efficiency.",
    source: `${OTEL} ${LOKI}`,
    calc: "Each column summed per user_email over the window; cache efficiency = cacheRead ÷ cacheCreation.",
  },
  activeHoursPerDev: {
    title: "Active hours per developer",
    what: "Top developers by hours of active use.",
    source: OTEL,
    calc: "Active-time seconds ÷ 3600 per user, top 30.",
  },

  // ---- Timeline / activity ----
  costOverTime: {
    title: "Cost over time",
    what: "Estimated cost trend, split by model.",
    source: OTEL,
    calc: "OTEL cost grouped by model, bucketed over the window.",
  },
  activityHeatmap: {
    title: "Activity heatmap (hour × weekday)",
    what: "The developer's typical weekly rhythm — which hours of which weekdays they're active. Empty rows/cells mean no activity then (e.g. weekends).",
    source: OTEL,
    calc: "Token usage in 1-hour buckets (last 30 days), folded onto a 7×24 weekday×hour grid and summed. Times are UTC.",
  },
  activityByHour: {
    title: "Activity by hour of day",
    what: "Total activity folded into 24 hours — shows daily rhythm.",
    source: OTEL,
    calc: "Token usage summed per hour-of-day across the window.",
  },
  activityByWeekday: {
    title: "Activity by weekday",
    what: "Total activity folded into 7 weekdays.",
    source: OTEL,
    calc: "Token usage summed per weekday across the window.",
  },
  projectTimeline: {
    title: "Project timeline",
    what: "Which repositories the developer worked in over time.",
    source: OTEL,
    calc: "Active token usage per repository, bucketed over the window.",
  },
  apiTotalCost: {
    title: "API Cost (month)",
    what: "Authoritative billed Anthropic API spend for the selected month, across the whole org.",
    source: "Anthropic Admin Cost Report API.",
    calc: "Sum of daily billed USD over the month (real billed amounts, discounts already applied).",
  },
  apiMoM: {
    title: "Month over month",
    what: "Change in total API cost vs. the previous month.",
    source: "Anthropic Admin Cost Report API.",
    calc: "(this month − previous month) ÷ previous month.",
  },
  costByClient: {
    title: "Cost by workspace",
    what: "Billed API cost per workspace — each Anthropic workspace maps to a product/client.",
    source: "Cost Report API (group_by workspace_id) joined to workspace names.",
    calc: "Sum of billed USD per workspace over the month.",
  },
  apiDailyAvg: {
    title: "Daily average",
    what: "Mean billed API spend per day so far this month.",
    source: "Anthropic Admin Cost Report API.",
    calc: "Total billed USD ÷ number of days elapsed in the month.",
  },
  apiProjected: {
    title: "Projected (month-end)",
    what: "Run-rate estimate of the full month's API cost if the current daily pace holds. Equals the actual total for a completed month.",
    source: "Anthropic Admin Cost Report API.",
    calc: "Daily average × number of days in the calendar month.",
  },
  apiBlended: {
    title: "Blended $ / 1M tokens",
    what: "Effective billed price per million tokens across all models and tiers — a single efficiency number.",
    source: "Cost Report API (cost) + Usage Report API (tokens).",
    calc: "Total billed USD ÷ (total tokens ÷ 1,000,000).",
  },
  apiCostByModel: {
    title: "Cost by model",
    what: "Real billed $ attributed to each model, plus non-token costs (web search, code execution, sessions). The authoritative cost split — not a token proxy.",
    source: "Cost Report API (group_by description → model / cost_type).",
    calc: "Sum of billed USD per model; non-token costs grouped by their cost type.",
  },
  costTrend: {
    title: "Cost over the month",
    what: "Daily billed API cost across the org for the selected month.",
    source: "Cost Report API (daily buckets).",
    calc: "Sum of billed USD per day.",
  },
  tokensByModelMix: {
    title: "Tokens by model",
    what: "Token volume by model — what's driving usage. Cost $ is only authoritative per client; model split is a usage (token) view.",
    source: "Anthropic Admin Usage Report API (group_by model).",
    calc: "Sum of input + output + cache tokens per model over the month.",
  },
  tokensByTier: {
    title: "Tokens by service tier",
    what: "Standard vs. batch vs. priority token volume — batch is cheaper, a cost-optimization signal.",
    source: "Usage Report API (group_by service_tier).",
    calc: "Sum of tokens per service tier over the month.",
  },
  apiCacheShare: {
    title: "Cache-read share",
    what: "Share of input tokens served from cache — higher means better context reuse and lower cost.",
    source: "Usage Report API.",
    calc: "cache-read tokens ÷ total tokens.",
  },
  exporterHealth: {
    title: "Exporter health",
    what: "Whether the billing-exporter is polling successfully.",
    source: BILLING,
    calc: "Time since last successful poll; error counter.",
  },
} satisfies Record<string, MetricDoc>;

export type MetricKey = keyof typeof METRIC_DOCS;
