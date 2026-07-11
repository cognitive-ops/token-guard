import "server-only";
import { promWindow } from "@/lib/time-range";
import { lokiWindow } from "@/lib/loki/client";
import { joinDeveloperCosts, summariseDeveloperCosts, type DeveloperCostRow } from "@/lib/cost-model";
import {
  cached,
  rangeFromToken,
  promGauge,
  promScalar,
  promByLabel,
  promByLabelInstant,
  promSeries,
  snapshotScalar,
  type LabelledValue,
  type TimeSeriesPoint,
} from "./common";

/** Per-section loaders for the Real Cost dashboard, cached by range token. */

export interface KpiData {
  orgRealCost: number | null;
  serviceBilled: number | null;
  otelEstimate: number;
  seatsByType: LabelledValue[];
  activeUsers: number;
  totalPrompts: number;
  totalTokens: number;
  sessions: number;
  linesOfCode: number;
  commits: number;
  pullRequests: number;
  costPerMTokens: number;
}

export const getKpis = (token: string) =>
  cached("rc-kpis", token, async (): Promise<KpiData> => {
    const r = rangeFromToken(token);
    const w = promWindow(r.windowSeconds);
    const lw = lokiWindow(r);
    const cost = `sum(increase(claude_code_cost_usage_USD_total[${w}]))`;
    const tokens = `sum(increase(claude_code_token_usage_tokens_total[${w}]))`;
    const [
      orgRealCost, serviceBilled, otelEstimate, seats, activeUsers,
      totalPrompts, totalTokens, sessions, loc, commits, prs, cost1k,
    ] = await Promise.all([
      promGauge("orgRealCost", "claude_org_real_cost_total_usd", r),
      promGauge("serviceBilled", "claude_service_billed_cost_total_usd", r),
      promScalar("otelEstimate", cost, r),
      promByLabel("seats", "claude_seat_count", "seat_type", r),
      promScalar("activeUsers", `count(count by (user_email)(increase(claude_code_cost_usage_USD_total[${w}])>0))`, r),
      snapshotScalar("prompts", `sum(claude_prompt_count)`, `sum(count_over_time({service_name="claude-code"} | event_name="user_prompt" [${lw}]))`, r),
      promScalar("tokens", tokens, r),
      promScalar("sessions", `count(count_over_time(claude_code_session_count_total[${w}]))`, r),
      promScalar("loc", `sum(increase(claude_code_lines_of_code_count_total[${w}]))`, r),
      promScalar("commits", `sum(max_over_time(claude_code_commit_count_total[${w}]))`, r),
      promScalar("prs", `sum(max_over_time(claude_code_pull_request_count_total[${w}]))`, r),
      // Cost per 1M tokens — the unit Anthropic prices in; per-1k rounds to $0.00.
      promScalar("costM", `${cost}/clamp_min(${tokens},1)*1000000`, r),
    ]);
    return {
      orgRealCost, serviceBilled, otelEstimate,
      seatsByType: seats,
      activeUsers: Math.round(activeUsers),
      totalPrompts, totalTokens, sessions, linesOfCode: loc, commits, pullRequests: prs,
      costPerMTokens: cost1k,
    };
  });

export interface DeveloperData {
  rows: DeveloperCostRow[];
  totals: ReturnType<typeof summariseDeveloperCosts>;
}

export const getDevelopers = (token: string) =>
  cached("rc-devs", token, async (): Promise<DeveloperData> => {
    const r = rangeFromToken(token);
    const [real, extra] = await Promise.all([
      promByLabel("devReal", "claude_dev_real_cost_usd", "email", r),
      promByLabel("devExtra", "claude_dev_extra_usage_usd", "email", r),
    ]);
    const rows = joinDeveloperCosts(real, extra);
    return { rows, totals: summariseDeveloperCosts(rows) };
  });

export interface BreakdownData {
  costByModel: LabelledValue[];
  tokensByType: LabelledValue[];
  costByRepo: LabelledValue[];
  costByTerminal: LabelledValue[];
  promptLanguage: LabelledValue[];
  costByUser: LabelledValue[];
  tokensByUser: LabelledValue[];
}

export const getBreakdowns = (token: string) =>
  cached("rc-breakdowns", token, async (): Promise<BreakdownData> => {
    const r = rangeFromToken(token);
    const w = promWindow(r.windowSeconds);
    const cost = (by: string) => `sum by (${by})(increase(claude_code_cost_usage_USD_total[${w}]))`;
    const [model, type, project, terminal, language, costUser, tokenUser] = await Promise.all([
      promByLabel("costByModel", cost("model"), "model", r),
      promByLabel("tokensByType", `sum by (type)(increase(claude_code_token_usage_tokens_total[${w}]))`, "type", r),
      promByLabel("costByRepo", `sum by (repository_fullname)(increase(claude_code_cost_usage_USD_total{repository_fullname!=""}[${w}]))`, "repository_fullname", r),
      promByLabel("costByTerminal", cost("terminal_type"), "terminal_type", r),
      promByLabelInstant("language", "sum by (language)(claude_prompt_language_count)", "language", r),
      promByLabel("costByUser", cost("user_email"), "user_email", r),
      promByLabel("tokensByUser", `sum by (user_email)(increase(claude_code_token_usage_tokens_total[${w}]))`, "user_email", r),
    ]);
    return {
      costByModel: model, tokensByType: type, costByRepo: project,
      costByTerminal: terminal, promptLanguage: language, costByUser: costUser, tokensByUser: tokenUser,
    };
  });

export const getCostOverTime = (token: string) =>
  cached("rc-timeseries", token, async (): Promise<TimeSeriesPoint[]> => {
    const r = rangeFromToken(token);
    return promSeries(
      "costOverTime",
      `sum by (model)(increase(claude_code_cost_usage_USD_total[${r.step}s]))`,
      "model",
      r,
    );
  });

export interface ExporterHealth {
  lastSuccess: number | null;
  errors: number | null;
}

export const getExporterHealth = (token: string) =>
  cached("rc-exporter", token, async (): Promise<ExporterHealth> => {
    const r = rangeFromToken(token);
    const [lastSuccess, errors] = await Promise.all([
      promGauge("exporterLastSuccess", "claude_billing_exporter_last_success_timestamp", r),
      promGauge("exporterErrors", "claude_billing_exporter_errors", r),
    ]);
    return { lastSuccess, errors };
  });
