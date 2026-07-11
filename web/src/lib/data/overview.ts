import "server-only";
import { promWindow } from "@/lib/time-range";
import { lokiWindow } from "@/lib/loki/client";
import { queryRange } from "@/lib/prometheus/client";
import { lastNotNull } from "@/lib/prometheus/reduce";
import {
  cached,
  rangeFromToken,
  promScalar,
  promByLabel,
  promByLabelInstant,
  promSeries,
  snapshotScalar,
  snapshotByLabel,
  lokiByLabel,
  indexByLabel,
  type LabelledValue,
  type TimeSeriesPoint,
} from "./common";

/** Per-section loaders for the Overview dashboard, cached by range token. */

export interface KpiData {
  totalCost: number;
  activeUsers: number;
  totalTokens: number;
  linesOfCode: number;
  totalPrompts: number;
  costPer1kLoc: number;
  avgCostPerUser: number;
  costPerPrompt: number;
  costPerActiveHour: number;
}

export const getKpis = (token: string) =>
  cached("ov-kpis", token, async (): Promise<KpiData> => {
    const r = rangeFromToken(token);
    const w = promWindow(r.windowSeconds);
    const lw = lokiWindow(r);
    const cost = `sum(increase(claude_code_cost_usage_USD_total[${w}]))`;
    const loc = `sum(increase(claude_code_lines_of_code_count_total[${w}]))`;
    const [
      totalCost, activeUsers, totalTokens, linesOfCode, totalPrompts,
      costPer1kLoc, costPerActiveHour,
    ] = await Promise.all([
      promScalar("totalCost", cost, r),
      promScalar("activeUsers", `count(count by (user_email)(increase(claude_code_cost_usage_USD_total[${w}])>0))`, r),
      promScalar("totalTokens", `sum(increase(claude_code_token_usage_tokens_total[${w}]))`, r),
      promScalar("loc", loc, r),
      snapshotScalar("prompts", `sum(claude_prompt_count)`, `sum(count_over_time({service_name="claude-code"} | event_name="user_prompt" [${lw}]))`, r),
      promScalar("costPer1kLoc", `${cost}/clamp_min(${loc},1)*1000`, r),
      promScalar("costPerActiveHour", `${cost}/clamp_min(sum(increase(claude_code_active_time_seconds_total[${w}]))/3600,1)`, r),
    ]);
    const users = Math.round(activeUsers);
    return {
      totalCost,
      activeUsers: users,
      totalTokens,
      linesOfCode,
      totalPrompts,
      costPer1kLoc,
      avgCostPerUser: totalCost / Math.max(users, 1),
      costPerPrompt: totalCost / Math.max(totalPrompts, 1),
      costPerActiveHour,
    };
  });

export interface BreakdownData {
  tokensByRepo: LabelledValue[];
  costByModel: LabelledValue[];
  tokensByType: LabelledValue[];
  costByRepo: LabelledValue[];
  costByGitHost: LabelledValue[];
  costByTerminal: LabelledValue[];
  toolUsage: LabelledValue[];
  requestSource: LabelledValue[];
  effort: LabelledValue[];
  intentMix: LabelledValue[];
  promptLanguage: LabelledValue[];
}

export const getBreakdowns = (token: string) =>
  cached("ov-breakdowns", token, async (): Promise<BreakdownData> => {
    const r = rangeFromToken(token);
    const w = promWindow(r.windowSeconds);
    const lw = lokiWindow(r);
    const cost = (by: string) => `sum by (${by})(increase(claude_code_cost_usage_USD_total[${w}]))`;
    const tokens = (by: string) => `sum by (${by})(increase(claude_code_token_usage_tokens_total[${w}]))`;
    const [
      tokensByRepo, costByModel, tokensByType, costByRepo,
      costByGitHost, costByTerminal, toolUsage, requestSource, effort,
      intentMix, promptLanguage,
    ] = await Promise.all([
      promByLabel("tokensByRepo", tokens("repository_fullname"), "repository_fullname", r),
      promByLabel("costByModel", cost("model"), "model", r),
      promByLabel("tokensByType", tokens("type"), "type", r),
      promByLabel("costByRepo", cost("repository_fullname"), "repository_fullname", r),
      promByLabel("costByGitHost", cost("repository_host"), "repository_host", r),
      promByLabel("costByTerminal", cost("terminal_type"), "terminal_type", r),
      promByLabelInstant("toolUsage", `sum by (tool_name)(claude_tool_usage_count)`, "tool_name", r),
      promByLabel("requestSource", cost("query_source"), "query_source", r),
      promByLabel("effort", cost("effort"), "effort", r),
      snapshotByLabel("intentMix", `sum by (intent)(claude_prompt_intent_count)`, `sum by (intent)(count_over_time({service_name="claude-code-intent"} | intent=~\`.+\` [${lw}]))`, "intent", r),
      promByLabelInstant("promptLanguage", "sum by (language)(claude_prompt_language_count)", "language", r),
    ]);
    return {
      tokensByRepo, costByModel, tokensByType, costByRepo,
      costByGitHost, costByTerminal, toolUsage, requestSource, effort,
      intentMix, promptLanguage,
    };
  });

export interface TablesData {
  costByUser: LabelledValue[];
  locByType: LabelledValue[];
}

export const getTables = (token: string) =>
  cached("ov-tables", token, async (): Promise<TablesData> => {
    const r = rangeFromToken(token);
    const w = promWindow(r.windowSeconds);
    const [costByUser, locByType] = await Promise.all([
      promByLabel("costByUser", `sum by (user_email)(increase(claude_code_cost_usage_USD_total[${w}]))`, "user_email", r),
      promByLabel("locByType", `sum by (type)(increase(claude_code_lines_of_code_count_total[${w}]))`, "type", r),
    ]);
    return { costByUser, locByType };
  });

export interface PromptLangRow {
  user: string;
  language: string;
  count: number;
}

export const getPromptLangByDeveloper = (token: string) =>
  cached("ov-promptlang", token, async (): Promise<PromptLangRow[]> => {
    const r = rangeFromToken(token);
    const series = await queryRange("sum by (user_email, language)(claude_prompt_language_count)", r);
    return series
      .map((s) => ({
        user: s.labels.user_email ?? "(unknown)",
        language: s.labels.language ?? "(unknown)",
        count: lastNotNull(s) ?? 0,
      }))
      .filter((row) => row.count > 0)
      .sort((a, b) => b.count - a.count);
  });

export interface LeaderboardRow {
  user: string;
  prompts: number;
  sessions: number;
  commits: number;
  cacheEff: number;
}

export const getLeaderboard = (token: string) =>
  cached("ov-leaderboard", token, async (): Promise<LeaderboardRow[]> => {
    const r = rangeFromToken(token);
    const w = promWindow(r.windowSeconds);
    const lw = lokiWindow(r);
    const [prompts, sessions, commits, cacheEff] = await Promise.all([
      snapshotByLabel("prompts", `sum by (user_email)(claude_prompt_count)`, `sum by (user_email)(count_over_time({service_name="claude-code"} | event_name="user_prompt" [${lw}]))`, "user_email", r),
      promByLabel("sessions", `count by (user_email)(count_over_time(claude_code_session_count_total[${w}]))`, "user_email", r),
      promByLabel("commits", `sum by (user_email)(max_over_time(claude_code_commit_count_total[${w}]))`, "user_email", r),
      promByLabel(
        "cacheEff",
        `sum by (user_email)(increase(claude_code_token_usage_tokens_total{type="cacheRead"}[${w}])) / clamp_min(sum by (user_email)(increase(claude_code_token_usage_tokens_total{type="cacheCreation"}[${w}])),1)`,
        "user_email",
        r,
      ),
    ]);
    const sessionsIdx = indexByLabel(sessions);
    const commitsIdx = indexByLabel(commits);
    const cacheEffIdx = indexByLabel(cacheEff);
    const users = new Set<string>([
      ...prompts.map((p) => p.label),
      ...sessions.map((s) => s.label),
      ...commits.map((c) => c.label),
      ...cacheEff.map((c) => c.label),
    ]);
    const promptsIdx = indexByLabel(prompts);
    return [...users]
      .map((user) => ({
        user,
        prompts: promptsIdx.get(user) ?? 0,
        sessions: sessionsIdx.get(user) ?? 0,
        commits: commitsIdx.get(user) ?? 0,
        cacheEff: cacheEffIdx.get(user) ?? 0,
      }))
      .sort((a, b) => b.prompts - a.prompts)
      .slice(0, 30);
  });

export const getCostOverTime = (token: string) =>
  cached("ov-timeseries", token, async (): Promise<TimeSeriesPoint[]> => {
    const r = rangeFromToken(token);
    return promSeries(
      "costOverTime",
      `sum by (user_email)(increase(claude_code_cost_usage_USD_total[${r.step}s]))`,
      "user_email",
      r,
    );
  });
