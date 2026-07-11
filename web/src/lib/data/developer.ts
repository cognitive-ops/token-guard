import "server-only";
import { promWindow } from "@/lib/time-range";
import { lokiWindow } from "@/lib/loki/client";
import {
  cached,
  rangeFromToken,
  promScalar,
  promByLabel,
  promByLabelInstant,
  promSeries,
  snapshotScalar,
  snapshotByLabel,
  lokiSeries,
  type LabelledValue,
  type TimeSeriesPoint,
  type TimeRange,
} from "./common";

/**
 * Per-section loaders for the Developer drilldown dashboard — every query is
 * filtered to a single developer (user_email). Cached by (name+user, token).
 */

const cost = "claude_code_cost_usage_USD_total"; // ESTIMATE
const tokens = "claude_code_token_usage_tokens_total";
const loc = "claude_code_lines_of_code_count_total";

export interface DevKpiData {
  totalCost: number;
  totalTokens: number;
  sessions: number;
  prompts: number;
  commits: number;
  pullRequests: number;
  pctNewCode: number;
  costPerCommit: number;
  costPerPrompt: number;
  cacheEfficiency: number;
  commitsPerPr: number;
  locAdded: number;
}

/** Per-developer prompt count — Prometheus snapshot gauge / Loki hybrid. */
function getDevPromptCount(user: string, r: TimeRange): Promise<number> {
  const u = `user_email="${user}"`;
  return snapshotScalar(
    "devPrompts",
    `sum(claude_prompt_count{${u}})`,
    `sum(count_over_time({service_name="claude-code"} | event_name="user_prompt" | user_email="${user}" [${lokiWindow(r)}]))`,
    r,
  );
}

export const getDevKpis = (user: string, token: string) =>
  cached(`dev-kpis:${user}`, token, async (): Promise<DevKpiData> => {
    const r = rangeFromToken(token);
    const w = promWindow(r.windowSeconds);
    const u = `user_email="${user}"`;
    const costExpr = `sum(increase(${cost}{${u}}[${w}]))`;
    const [
      totalCost,
      totalTokens,
      sessions,
      prompts,
      commits,
      pullRequests,
      pctNewCode,
      costPerCommit,
      cacheEfficiency,
      commitsPerPr,
      locAdded,
    ] = await Promise.all([
      promScalar("devCost", costExpr, r),
      promScalar("devTokens", `sum(increase(${tokens}{${u}}[${w}]))`, r),
      promScalar("devSessions", `count(count_over_time(claude_code_session_count_total{${u}}[${w}]))`, r),
      getDevPromptCount(user, r),
      promScalar("devCommits", `sum(max_over_time(claude_code_commit_count_total{${u}}[${w}]))`, r),
      promScalar("devPrs", `sum(max_over_time(claude_code_pull_request_count_total{${u}}[${w}]))`, r),
      promScalar(
        "devPctNew",
        `sum(increase(${loc}{${u},type="added"}[${w}]))/clamp_min(sum(increase(${loc}{${u},type=~"added|removed"}[${w}])),1)`,
        r,
      ),
      promScalar(
        "devCostPerCommit",
        `${costExpr}/clamp_min(sum(max_over_time(claude_code_commit_count_total{${u}}[${w}])),1)`,
        r,
      ),
      promScalar(
        "devCacheEff",
        `sum(increase(${tokens}{${u},type="cacheRead"}[${w}]))/clamp_min(sum(increase(${tokens}{${u},type="cacheCreation"}[${w}])),1)`,
        r,
      ),
      promScalar(
        "devCommitsPerPr",
        `sum(max_over_time(claude_code_commit_count_total{${u}}[${w}]))/clamp_min(sum(max_over_time(claude_code_pull_request_count_total{${u}}[${w}])),1)`,
        r,
      ),
      promScalar("devLocAdded", `sum(increase(${loc}{${u},type="added"}[${w}]))`, r),
    ]);
    return {
      totalCost,
      totalTokens,
      sessions,
      prompts,
      commits,
      pullRequests,
      pctNewCode,
      costPerCommit,
      costPerPrompt: totalCost / Math.max(prompts, 1),
      cacheEfficiency,
      commitsPerPr,
      locAdded,
    };
  });

export interface DevBreakdownData {
  tokensByType: LabelledValue[];
  costByModel: LabelledValue[];
  costByRepo: LabelledValue[];
  costByTerminal: LabelledValue[];
  promptLanguage: LabelledValue[];
}

export const getDevBreakdowns = (user: string, token: string) =>
  cached(`dev-breakdowns:${user}`, token, async (): Promise<DevBreakdownData> => {
    const r = rangeFromToken(token);
    const w = promWindow(r.windowSeconds);
    const u = `user_email="${user}"`;
    const [tokensByType, costByModel, costByRepo, costByTerminal, promptLanguage] =
      await Promise.all([
        promByLabel("devTokensByType", `sum by (type)(increase(${tokens}{${u}}[${w}]))`, "type", r),
        promByLabel("devCostByModel", `sum by (model)(increase(${cost}{${u}}[${w}]))`, "model", r),
        promByLabel(
          "devCostByRepo",
          `sum by (repository_fullname)(increase(${cost}{${u},repository_fullname!=""}[${w}]))`,
          "repository_fullname",
          r,
        ),
        promByLabel(
          "devCostByTerminal",
          `sum by (terminal_type)(increase(${cost}{${u}}[${w}]))`,
          "terminal_type",
          r,
        ),
        promByLabelInstant(
          "devPromptLanguage",
          `sum by (language)(claude_prompt_language_count{${u}})`,
          "language",
          r,
        ),
      ]);
    return { tokensByType, costByModel, costByRepo, costByTerminal, promptLanguage };
  });

export interface DevPromptPatternData {
  intentMix: LabelledValue[];
  behaviors: LabelledValue[];
  slashCommands: LabelledValue[];
}

export const getDevPromptPatterns = (user: string, token: string) =>
  cached(`dev-prompt-patterns:${user}`, token, async (): Promise<DevPromptPatternData> => {
    const r = rangeFromToken(token);
    const u = `user_email="${user}"`;
    const lw = lokiWindow(r);
    // Snapshot gauge (<1ms) for the ~30d default; time-accurate Loki otherwise.
    const [intentMix, behaviors, slashCommands] = await Promise.all([
      snapshotByLabel(
        "devIntent",
        `sum by (intent)(claude_prompt_intent_count{${u}})`,
        `sum by (intent)(count_over_time({service_name="claude-code-intent"} | intent=~".+" | user_email=\`${user}\` [${lw}]))`,
        "intent",
        r,
      ),
      snapshotByLabel(
        "devBehaviors",
        `sum by (behavior)(claude_prompt_behavior_count{${u}})`,
        `sum by (behavior)(count_over_time({service_name="claude-code-behavior"} | behavior=~".+" | user_email=\`${user}\` [${lw}]))`,
        "behavior",
        r,
      ),
      snapshotByLabel(
        "devCommands",
        `sum by (command)(claude_prompt_command_count{${u}})`,
        `sum by (command)(count_over_time({service_name="claude-code-command"} | command=~".+" | user_email=\`${user}\` [${lw}]))`,
        "command",
        r,
      ),
    ]);
    return { intentMix, behaviors, slashCommands: slashCommands.slice(0, 12) };
  });

export interface DevOverTimeData {
  costOverTime: TimeSeriesPoint[];
  promptsOverTime: TimeSeriesPoint[];
  locOverTime: TimeSeriesPoint[];
  projectTimeline: TimeSeriesPoint[];
}

export const getDevOverTime = (user: string, token: string) =>
  cached(`dev-overtime:${user}`, token, async (): Promise<DevOverTimeData> => {
    const r = rangeFromToken(token);
    const u = `user_email="${user}"`;
    const [costOverTime, promptsOverTime, locOverTime, projectTimeline] = await Promise.all([
      promSeries(
        "devCostOverTime",
        `sum by (model)(increase(${cost}{${u}}[${r.step}s]))`,
        "model",
        r,
      ),
      lokiSeries(
        "devPromptsOverTime",
        `sum(count_over_time({service_name="claude-code"} | event_name="user_prompt" | user_email="${user}" [${r.step}s]))`,
        "",
        r,
      ),
      promSeries("devLocOverTime", `sum by (type)(increase(${loc}{${u}}[${r.step}s]))`, "type", r),
      promSeries(
        "devProjectTimeline",
        `sum by (repository_fullname)(increase(${tokens}{${u},repository_fullname!=""}[${r.step}s]))`,
        "repository_fullname",
        r,
      ),
    ]);
    return { costOverTime, promptsOverTime, locOverTime, projectTimeline };
  });

export interface DevActivityData {
  cells: number[][];
  byHour: LabelledValue[];
  byWeekday: LabelledValue[];
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export const getDevActivity = (user: string, token: string) =>
  cached(`dev-activity:${user}`, token, async (): Promise<DevActivityData> => {
    const r = rangeFromToken(token);
    const u = `user_email="${user}"`;
    // A weekday×hour heatmap is only meaningful at HOURLY resolution — each
    // bucket must map to exactly one hour-of-day. Query at a fixed 1h step
    // (capped to the last 30 days so it stays light) and fold across days.
    const HEATMAP_MAX = 30 * 86_400;
    const hr = {
      ...r,
      start: r.end - Math.min(r.windowSeconds, HEATMAP_MAX),
      step: 3_600,
    };
    const pts = await promSeries(
      "devActivity",
      `sum(increase(${tokens}{${u}}[3600s]))`,
      "",
      hr,
    );
    const cells: number[][] = Array.from({ length: 7 }, () =>
      new Array<number>(24).fill(0),
    );
    for (const p of pts) {
      const d = new Date(p.t * 1000);
      const row = cells[d.getUTCDay()]!;
      const h = d.getUTCHours();
      row[h] = (row[h] ?? 0) + (p.series.value || 0);
    }
    const byHour: LabelledValue[] = Array.from({ length: 24 }, (_, h) => ({
      label: `${h}:00`,
      value: cells.reduce((acc, row) => acc + (row[h] ?? 0), 0),
    }));
    const byWeekday: LabelledValue[] = WEEKDAYS.map((label, d) => ({
      label,
      value: (cells[d] ?? []).reduce((acc, v) => acc + v, 0),
    }));
    return { cells, byHour, byWeekday };
  });
