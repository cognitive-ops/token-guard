import "server-only";
import { promWindow } from "@/lib/time-range";
import { lokiWindow, lokiInstant } from "@/lib/loki/client";
import { queryRange } from "@/lib/prometheus/client";
import { lastNotNull } from "@/lib/prometheus/reduce";
import {
  cached,
  rangeFromToken,
  promByLabel,
  promByLabelInstant,
  lokiByLabel,
  lokiSeries,
  snapshotScalar,
  snapshotByLabel,
  isSnapshotWindow,
  indexByLabel,
  type LabelledValue,
  type TimeSeriesPoint,
  type TimeRange,
} from "./common";

/** Per-section loaders for the Usage Patterns dashboard, cached by range token. */

// --- Engagement leaderboard ---

export interface LeaderboardRow {
  email: string;
  prompts: number;
  sessions: number;
  activeHours: number;
  commits: number;
  prs: number;
  locAdded: number;
  tokens: number;
  cacheEff: number;
}

export const getLeaderboard = (token: string) =>
  cached("up-leaderboard", token, async (): Promise<LeaderboardRow[]> => {
    const r = rangeFromToken(token);
    const w = promWindow(r.windowSeconds);
    const lw = lokiWindow(r);
    const [prompts, sessions, activeHours, commits, prs, locAdded, tokens, cacheEff] =
      await Promise.all([
        snapshotByLabel(
          "lbPrompts",
          `sum by (user_email)(claude_prompt_count)`,
          `sum by (user_email)(count_over_time({service_name="claude-code"} | event_name="user_prompt" [${lw}]))`,
          "user_email",
          r,
        ),
        promByLabel("lbSessions", `count by (user_email)(count_over_time(claude_code_session_count_total[${w}]))`, "user_email", r),
        promByLabel("lbActiveHours", `sum by (user_email)(increase(claude_code_active_time_seconds_total[${w}]))/3600`, "user_email", r),
        promByLabel("lbCommits", `sum by (user_email)(max_over_time(claude_code_commit_count_total[${w}]))`, "user_email", r),
        promByLabel("lbPrs", `sum by (user_email)(max_over_time(claude_code_pull_request_count_total[${w}]))`, "user_email", r),
        promByLabel("lbLoc", `sum by (user_email)(increase(claude_code_lines_of_code_count_total{type="added"}[${w}]))`, "user_email", r),
        promByLabel("lbTokens", `sum by (user_email)(increase(claude_code_token_usage_tokens_total[${w}]))`, "user_email", r),
        promByLabel(
          "lbCacheEff",
          `sum by (user_email)(increase(claude_code_token_usage_tokens_total{type="cacheRead"}[${w}]))/clamp_min(sum by (user_email)(increase(claude_code_token_usage_tokens_total{type="cacheCreation"}[${w}])),1)`,
          "user_email",
          r,
        ),
      ]);

    const promptIdx = indexByLabel(prompts);
    const sessionIdx = indexByLabel(sessions);
    const activeHoursIdx = indexByLabel(activeHours);
    const commitsIdx = indexByLabel(commits);
    const prsIdx = indexByLabel(prs);
    const locIdx = indexByLabel(locAdded);
    const tokensIdx = indexByLabel(tokens);
    const cacheEffIdx = indexByLabel(cacheEff);

    const emails = new Set<string>([
      ...promptIdx.keys(),
      ...sessionIdx.keys(),
      ...activeHoursIdx.keys(),
      ...commitsIdx.keys(),
      ...prsIdx.keys(),
      ...locIdx.keys(),
      ...tokensIdx.keys(),
      ...cacheEffIdx.keys(),
    ]);

    const rows: LeaderboardRow[] = [...emails].map((email) => ({
      email,
      prompts: promptIdx.get(email) ?? 0,
      sessions: sessionIdx.get(email) ?? 0,
      activeHours: activeHoursIdx.get(email) ?? 0,
      commits: commitsIdx.get(email) ?? 0,
      prs: prsIdx.get(email) ?? 0,
      locAdded: locIdx.get(email) ?? 0,
      tokens: tokensIdx.get(email) ?? 0,
      cacheEff: cacheEffIdx.get(email) ?? 0,
    }));

    return rows.sort((a, b) => b.prompts - a.prompts).slice(0, 30);
  });

// --- Per-developer bar charts ---

export interface PerDevBars {
  promptsPerDev: LabelledValue[];
  activeHoursPerDev: LabelledValue[];
  cacheEffPerDev: LabelledValue[];
}

export const getPerDevBars = (token: string) =>
  cached("up-perdev-bars", token, async (): Promise<PerDevBars> => {
    const r = rangeFromToken(token);
    const w = promWindow(r.windowSeconds);
    const lw = lokiWindow(r);
    const [prompts, activeHours, cacheEff] = await Promise.all([
      snapshotByLabel(
        "barPrompts",
        `sum by (user_email)(claude_prompt_count)`,
        `topk(30, sum by (user_email)(count_over_time({service_name="claude-code"} | event_name="user_prompt" [${lw}])))`,
        "user_email",
        r,
      ),
      promByLabel("barActiveHours", `sum by (user_email)(increase(claude_code_active_time_seconds_total[${w}]))/3600`, "user_email", r),
      promByLabel(
        "barCacheEff",
        `sum by (user_email)(increase(claude_code_token_usage_tokens_total{type="cacheRead"}[${w}]))/clamp_min(sum by (user_email)(increase(claude_code_token_usage_tokens_total{type="cacheCreation"}[${w}])),1)`,
        "user_email",
        r,
      ),
    ]);
    return {
      promptsPerDev: prompts.slice(0, 30),
      activeHoursPerDev: activeHours.slice(0, 30),
      cacheEffPerDev: cacheEff.slice(0, 30),
    };
  });

// --- Donuts: "what it's used for" + "workflow style" ---

export interface UsageDonuts {
  intentMix: LabelledValue[];
  behaviors: LabelledValue[];
  slashCommands: LabelledValue[];
  toolUsage: LabelledValue[];
  requestSource: LabelledValue[];
  effort: LabelledValue[];
  costByModel: LabelledValue[];
  subagentType: LabelledValue[];
  sessionStart: LabelledValue[];
  promptLanguage: LabelledValue[];
}

export const getDonuts = (token: string) =>
  cached("up-donuts", token, async (): Promise<UsageDonuts> => {
    const r = rangeFromToken(token);
    const w = promWindow(r.windowSeconds);
    const lw = lokiWindow(r);
    const cost = (by: string) => `sum by (${by})(increase(claude_code_cost_usage_USD_total[${w}]))`;
    const [
      intentMix, behaviors, slashCommands, toolUsage, requestSource,
      effort, costByModel, subagentType, sessionStart, promptLanguage,
    ] = await Promise.all([
      snapshotByLabel("intentMix", `sum by (intent)(claude_prompt_intent_count)`, `sum by (intent)(count_over_time({service_name="claude-code-intent"} | intent=~\`.+\` [${lw}]))`, "intent", r),
      snapshotByLabel("behaviors", `sum by (behavior)(claude_prompt_behavior_count)`, `sum by (behavior)(count_over_time({service_name="claude-code-behavior"} | behavior=~\`.+\` [${lw}]))`, "behavior", r),
      snapshotByLabel("slashCommands", `sum by (command)(claude_prompt_command_count)`, `sum by (command)(count_over_time({service_name="claude-code-command"} | command=~\`.+\` [${lw}]))`, "command", r),
      promByLabelInstant("toolUsage", `sum by (tool_name)(claude_tool_usage_count)`, "tool_name", r),
      promByLabel("requestSource", cost("query_source"), "query_source", r),
      promByLabel("effort", cost("effort"), "effort", r),
      promByLabel("costByModel", cost("model"), "model", r),
      promByLabel("subagentType", `sum by (agent_name)(increase(claude_code_cost_usage_USD_total{agent_name=~".+"}[${w}]))`, "agent_name", r),
      promByLabel("sessionStart", `count by (start_type)(count_over_time(claude_code_session_count_total[${w}]))`, "start_type", r),
      promByLabelInstant("promptLanguage", "sum by (language)(claude_prompt_language_count)", "language", r),
    ]);
    return {
      intentMix,
      behaviors,
      slashCommands: slashCommands.slice(0, 12),
      toolUsage,
      requestSource,
      effort,
      costByModel,
      subagentType,
      sessionStart,
      promptLanguage,
    };
  });

// --- Prompt-craft stats ---

export interface CraftStat {
  count: number;
  pct: number;
}

export interface CraftStats {
  wellSpecified: CraftStat;
  verifiesOutput: CraftStat;
  underspecified: CraftStat;
  stuckLooping: CraftStat;
}

export const getCraftStats = (token: string) =>
  cached("up-craft", token, async (): Promise<CraftStats> => {
    const r = rangeFromToken(token);
    const lw = lokiWindow(r);
    const behavior = (b: string) =>
      snapshotScalar(
        `craft-${b}`,
        `sum(claude_prompt_behavior_count{behavior="${b}"})`,
        `sum(count_over_time({service_name="claude-code-behavior"} | behavior=\`${b}\` [${lw}]))`,
        r,
      );
    const [classifiedTotal, well, verifies, under, stuck] = await Promise.all([
      snapshotScalar(
        "craftTotal",
        `sum(claude_prompt_intent_count)`,
        `sum(count_over_time({service_name="claude-code-intent"} | intent=~\`.+\` [${lw}]))`,
        r,
      ),
      behavior("well-specified"),
      behavior("verifies-output"),
      behavior("underspecified"),
      behavior("stuck-looping"),
    ]);
    const denom = Math.max(classifiedTotal, 1);
    const stat = (count: number): CraftStat => ({ count, pct: (100 * count) / denom });
    return {
      wellSpecified: stat(well),
      verifiesOutput: stat(verifies),
      underspecified: stat(under),
      stuckLooping: stat(stuck),
    };
  });

// --- Two-label per-developer tables ---

export interface TwoLabelRow {
  key1: string;
  key2: string;
  value: number;
}

function mapTwoLabel(
  series: Awaited<ReturnType<typeof lokiInstant>>,
  label1: string,
  label2: string,
): TwoLabelRow[] {
  const rows: TwoLabelRow[] = [];
  for (const s of series) {
    const k1 = s.labels[label1];
    const k2 = s.labels[label2];
    if (k1 === undefined || k2 === undefined) continue;
    const v = lastNotNull(s);
    if (v === null) continue;
    rows.push({ key1: k1, key2: k2, value: v });
  }
  return rows.sort((a, b) => b.value - a.value);
}

export interface PerDevTables {
  intentByDeveloper: TwoLabelRow[];
  behaviorsByDeveloper: TwoLabelRow[];
  promptLangByDeveloper: TwoLabelRow[];
}

/** Two-label series via the Prometheus snapshot gauge for ~30d windows, else Loki. */
async function twoLabelSnapshot(promExpr: string, lokiExpr: string, r: TimeRange) {
  if (isSnapshotWindow(r)) {
    const s = await queryRange(promExpr, r);
    if (s.length) return s;
  }
  return lokiInstant(lokiExpr, r);
}

export const getPerDevTables = (token: string) =>
  cached("up-perdev-tables", token, async (): Promise<PerDevTables> => {
    const r = rangeFromToken(token);
    const lw = lokiWindow(r);
    const [intent, behavior, language] = await Promise.all([
      twoLabelSnapshot(
        `sum by (user_email, intent)(claude_prompt_intent_count)`,
        `sum by (user_email, intent)(count_over_time({service_name="claude-code-intent"} | intent=~\`.+\` [${lw}]))`,
        r,
      ),
      twoLabelSnapshot(
        `sum by (user_email, behavior)(claude_prompt_behavior_count)`,
        `sum by (user_email, behavior)(count_over_time({service_name="claude-code-behavior"} | behavior=~\`.+\` [${lw}]))`,
        r,
      ),
      queryRange("sum by (user_email, language)(claude_prompt_language_count)", r),
    ]);
    return {
      intentByDeveloper: mapTwoLabel(intent, "user_email", "intent"),
      behaviorsByDeveloper: mapTwoLabel(behavior, "user_email", "behavior"),
      promptLangByDeveloper: mapTwoLabel(language, "user_email", "language"),
    };
  });

// --- Prompt volume time series ---

export interface PromptVolume {
  promptsOverTime: TimeSeriesPoint[];
}

export const getPromptVolume = (token: string) =>
  cached("up-prompt-volume", token, async (): Promise<PromptVolume> => {
    const r = rangeFromToken(token);
    const prompts = await lokiSeries(
      "promptsOverTime",
      `sum(count_over_time({service_name="claude-code"} | event_name="user_prompt" [${r.step}s]))`,
      "",
      r,
    );
    return { promptsOverTime: prompts };
  });
