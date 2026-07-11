/**
 * Dashboard-as-code.
 *
 * Every PromQL/LogQL string the Real Cost view needs lives here, in one place,
 * the way Grafana keeps them inside dashboard JSON — except these are typed,
 * commented, diff-friendly, and reused by both the page and the tests.
 *
 * `win` is a Prometheus duration literal (e.g. "30d") standing in for Grafana's
 * `$__range`; `step` (a number of seconds) stands in for `$__interval`.
 *
 * Queries are copied verbatim from grafana/dashboards/real-cost-dashboard.json
 * so behaviour is identical — only the macros are substituted.
 */

/** Exporter / standalone gauges — present at `now`, no window needed. */
export const exporterQueries = {
  orgRealCost: "claude_org_real_cost_total_usd",
  serviceBilled: "claude_service_billed_cost_total_usd",
  seatCount: "claude_seat_count",
  devRealCost: "claude_dev_real_cost_usd",
  devExtraUsage: "claude_dev_extra_usage_usd",
  workspaceBilled: "sum by (workspace_id)(claude_workspace_billed_cost_usd)",
  exporterLastSuccess: "claude_billing_exporter_last_success_timestamp",
  exporterErrors: "claude_billing_exporter_errors",
  promptLanguage: "sum by (language)(claude_prompt_language_count)",
} as const;

/** OTEL usage rollups over the selected window. */
export function otelQueries(win: string) {
  return {
    // Headline / secondary stat tiles
    estimatedCost: `sum(increase(claude_code_cost_usage_USD_total[${win}]))`,
    totalTokens: `sum(increase(claude_code_token_usage_tokens_total[${win}]))`,
    activeUsers: `count(count by (user_email)(increase(claude_code_cost_usage_USD_total[${win}])>0))`,
    sessions: `sum(increase(claude_code_session_count_total[${win}]))`,
    linesOfCode: `sum(increase(claude_code_lines_of_code_count_total[${win}]))`,
    commits: `sum(increase(claude_code_commit_count_total[${win}]))`,
    pullRequests: `sum(increase(claude_code_pull_request_count_total[${win}]))`,
    costPer1kTokens: `sum(increase(claude_code_cost_usage_USD_total[${win}]))/clamp_min(sum(increase(claude_code_token_usage_tokens_total[${win}])),1)*1000`,

    // Breakdowns (donuts)
    costByModel: `sum by (model)(increase(claude_code_cost_usage_USD_total[${win}]))`,
    tokensByType: `sum by (type)(increase(claude_code_token_usage_tokens_total[${win}]))`,
    costByProject: `sum by (project_name)(increase(claude_code_cost_usage_USD_total[${win}]))`,
    costByTerminal: `sum by (terminal_type)(increase(claude_code_cost_usage_USD_total[${win}]))`,

    // Per-developer usage tables
    costByUser: `sum by (user_email)(increase(claude_code_cost_usage_USD_total[${win}]))`,
    tokensByUser: `sum by (user_email)(increase(claude_code_token_usage_tokens_total[${win}]))`,
  } as const;
}

/** OTEL cost over time, one series per model (Grafana's `$__interval`). */
export function otelCostOverTime(stepSeconds: number): string {
  return `sum by (model)(increase(claude_code_cost_usage_USD_total[${stepSeconds}s]))`;
}

/** LogQL: prompt count over the window. */
export function promptCount(win: string): string {
  return `sum(count_over_time({service_name="claude-code"} | event_name=\`user_prompt\` [${win}]))`;
}
