import "server-only";
import { cached, type LabelledValue, type TimeSeriesPoint } from "./common";
import {
  adminConfigured,
  listWorkspaces,
  costReportByWorkspace,
  costReportByDescription,
  usageReportBy,
} from "@/lib/admin/client";

/**
 * API Cost dashboard data — billed $ per client (= workspace) for a month, plus
 * token-usage mix, from the Anthropic Admin API. Cached by month token.
 */

export interface ClientCost {
  client: string;
  workspaceId: string;
  cost: number;
  share: number; // 0..1 of month total
}

export interface ApiCostData {
  configured: boolean;
  error?: string;
  month: string; // YYYY-MM
  label: string; // "June 2026"
  totalCost: number;
  prevTotalCost: number;
  momPct: number | null;
  dailyAvg: number; // mean billed $/day (elapsed days)
  projected: number; // run-rate projection to month end
  blendedPerMtok: number; // total cost ÷ million tokens
  clients: ClientCost[];
  modelCost: LabelledValue[]; // real billed $ per model + non-token cost types
  dailyTrend: TimeSeriesPoint[]; // total cost per day
  modelTokens: LabelledValue[];
  tierTokens: LabelledValue[];
  totalTokens: number;
  cacheReadShare: number; // 0..1
}

/** Pretty label for non-token cost types (web_search → "Web search"). */
function prettyCostType(ct: string): string {
  return ct.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];

/** Default month token (current UTC month) "YYYY-MM". */
export function currentMonth(now = new Date()): string {
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** Parse "YYYY-MM" → ISO start/end (next-month boundary) + label, prev-month token. */
export function monthBounds(month: string) {
  const m = /^(\d{4})-(\d{2})$/.exec(month);
  const now = new Date();
  const y = m ? Number(m[1]) : now.getUTCFullYear();
  const mo = m ? Number(m[2]) - 1 : now.getUTCMonth();
  const start = new Date(Date.UTC(y, mo, 1));
  const end = new Date(Date.UTC(y, mo + 1, 1));
  const prev = new Date(Date.UTC(y, mo - 1, 1));
  return {
    startIso: start.toISOString(),
    endIso: end.toISOString(),
    label: `${MONTHS[mo]} ${y}`,
    prevToken: `${prev.getUTCFullYear()}-${String(prev.getUTCMonth() + 1).padStart(2, "0")}`,
  };
}

/** Recent months (newest first) for the picker. */
export function recentMonths(count = 12, now = new Date()): { token: string; label: string }[] {
  const out: { token: string; label: string }[] = [];
  for (let i = 0; i < count; i++) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - i, 1));
    out.push({
      token: `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`,
      label: `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`,
    });
  }
  return out;
}

function sumCost(buckets: { amount: number }[]): number {
  return buckets.reduce((a, b) => a + b.amount, 0);
}

export const getApiCost = (month: string) =>
  cached("api-cost", month, async (): Promise<ApiCostData> => {
    const { startIso, endIso, label, prevToken } = monthBounds(month);
    const empty = {
      totalCost: 0, prevTotalCost: 0, momPct: null,
      dailyAvg: 0, projected: 0, blendedPerMtok: 0,
      clients: [], modelCost: [], dailyTrend: [], modelTokens: [], tierTokens: [],
      totalTokens: 0, cacheReadShare: 0,
    } satisfies Partial<ApiCostData>;
    if (!adminConfigured()) {
      return { configured: false, month, label, ...empty };
    }

    const prev = monthBounds(prevToken);
    let names: Map<string, string>, cost, prevCost, descCost, modelUsage, tierUsage;
    try {
      [names, cost, prevCost, descCost, modelUsage, tierUsage] = await Promise.all([
        listWorkspaces(),
        costReportByWorkspace(startIso, endIso),
        costReportByWorkspace(prev.startIso, prev.endIso),
        costReportByDescription(startIso, endIso),
        usageReportBy(startIso, endIso, "model"),
        usageReportBy(startIso, endIso, "service_tier"),
      ]);
    } catch (err) {
      console.error("[api-cost] Admin API call failed:", err);
      return { configured: true, error: (err as Error).message, month, label, ...empty };
    }

    // Per-client (workspace) totals
    const byWs = new Map<string, number>();
    for (const b of cost) byWs.set(b.workspaceId, (byWs.get(b.workspaceId) ?? 0) + b.amount);
    const totalCost = sumCost(cost);
    const clients: ClientCost[] = [...byWs.entries()]
      .map(([workspaceId, c]) => ({
        client: names.get(workspaceId) ?? workspaceId,
        workspaceId,
        cost: c,
        share: totalCost > 0 ? c / totalCost : 0,
      }))
      .sort((a, b) => b.cost - a.cost);

    // Daily total trend. Enumerate EVERY day in the month (zero-fill days that
    // didn't bill) so the bar chart reads as a continuous daily series instead
    // of sparse bars on the few days that happened to bill — which otherwise
    // looks like weekly buckets. Cap at "today" for the in-progress month.
    const byDay = new Map<string, number>();
    for (const b of cost) byDay.set(b.day, (byDay.get(b.day) ?? 0) + b.amount);
    const monthStart = new Date(startIso);
    const monthEnd = new Date(endIso);
    const tomorrowUtc = new Date();
    tomorrowUtc.setUTCHours(0, 0, 0, 0);
    tomorrowUtc.setUTCDate(tomorrowUtc.getUTCDate() + 1);
    const lastDay = monthEnd < tomorrowUtc ? monthEnd : tomorrowUtc; // exclusive
    const dailyTrend: TimeSeriesPoint[] = [];
    for (const d = new Date(monthStart); d < lastDay; d.setUTCDate(d.getUTCDate() + 1)) {
      const day = d.toISOString().slice(0, 10);
      dailyTrend.push({ t: Math.floor(d.getTime() / 1000), series: { cost: byDay.get(day) ?? 0 } });
    }

    // Token mix
    const agg = (rows: { key: string; tokens: number }[]) => {
      const m = new Map<string, number>();
      for (const r of rows) m.set(r.key, (m.get(r.key) ?? 0) + r.tokens);
      return [...m.entries()].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value);
    };
    const totalTokens = modelUsage.reduce((a, r) => a + r.tokens, 0);
    const cacheRead = modelUsage.reduce((a, r) => a + r.cacheRead, 0);

    // Real billed $ per model (token costs) + per non-token cost type
    // (web search / code execution / sessions) — a true cost attribution.
    const byModel = new Map<string, number>();
    for (const r of descCost) {
      const key = r.model ?? (r.costType ? prettyCostType(r.costType) : "Other");
      byModel.set(key, (byModel.get(key) ?? 0) + r.amount);
    }
    const modelCost: LabelledValue[] = [...byModel.entries()]
      .map(([label, value]) => ({ label, value }))
      .sort((a, b) => b.value - a.value);

    // Run-rate: project the elapsed daily average across the full calendar month.
    // For a completed (past) month daysElapsed === daysInMonth, so projected === total.
    const s = new Date(startIso);
    const daysElapsed = dailyTrend.length || 1;
    const daysInMonth = new Date(Date.UTC(s.getUTCFullYear(), s.getUTCMonth() + 1, 0)).getUTCDate();
    const dailyAvg = totalCost / daysElapsed;
    const projected = dailyAvg * daysInMonth;
    const blendedPerMtok = totalTokens > 0 ? totalCost / (totalTokens / 1_000_000) : 0;

    const prevTotalCost = sumCost(prevCost);
    return {
      configured: true, month, label,
      totalCost, prevTotalCost,
      momPct: prevTotalCost > 0 ? ((totalCost - prevTotalCost) / prevTotalCost) * 100 : null,
      dailyAvg, projected, blendedPerMtok,
      clients,
      modelCost,
      dailyTrend,
      modelTokens: agg(modelUsage),
      tierTokens: agg(tierUsage),
      totalTokens,
      cacheReadShare: totalTokens > 0 ? cacheRead / totalTokens : 0,
    };
  });
