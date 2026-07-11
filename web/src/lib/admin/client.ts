import "server-only";
import { readFileSync } from "node:fs";
import { z } from "zod";
import { env } from "@/lib/env";
import { createLimiter } from "@/lib/limit";

/**
 * Anthropic Admin API client (server-only) for the API Cost dashboard.
 *
 * Two endpoints:
 * - /v1/organizations/cost_report          — billed USD, daily buckets, group_by workspace_id (= client)
 * - /v1/organizations/usage_report/messages — token counts, daily, group_by model/service_tier/workspace_id/…
 * plus /v1/organizations/workspaces for workspace_id → friendly name.
 *
 * The Admin key (sk-ant-admin…) is read once, server-side, from ADMIN_KEY or
 * ADMIN_KEY_PATH; it never reaches the browser.
 */

const API_BASE = "https://api.anthropic.com";
const VERSION = "2023-06-01";
const limit = createLimiter(4);

let cachedKey: string | null | undefined;
function adminKey(): string | null {
  if (cachedKey !== undefined) return cachedKey;
  if (env.ADMIN_KEY) return (cachedKey = env.ADMIN_KEY.trim());
  if (env.ADMIN_KEY_PATH) {
    try {
      cachedKey = readFileSync(env.ADMIN_KEY_PATH, "utf8").trim();
    } catch {
      cachedKey = null;
    }
    return cachedKey;
  }
  return (cachedKey = null);
}

/** True when an Admin key is configured (gates the /api-cost feature). */
export function adminConfigured(): boolean {
  return adminKey() !== null;
}

export class AdminApiError extends Error {}

async function adminGet(path: string, params: Record<string, string | string[]>) {
  const key = adminKey();
  if (!key) throw new AdminApiError("Admin API key not configured");
  const url = new URL(path, API_BASE);
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach((x) => url.searchParams.append(k, x));
    else url.searchParams.set(k, v);
  }
  return limit(async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), Math.max(env.QUERY_TIMEOUT_MS, 30_000));
    try {
      const res = await fetch(url, {
        signal: controller.signal,
        headers: { "x-api-key": key, "anthropic-version": VERSION },
        next: { revalidate: env.REVALIDATE_SECONDS, tags: ["admin"] },
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new AdminApiError(`Admin API ${res.status} on ${path}: ${body.slice(0, 200)}`);
      }
      return res.json();
    } finally {
      clearTimeout(timeout);
    }
  });
}

// --- Schemas. Result rows vary by endpoint/version, and we only read a few
// known fields, so keep row records permissive (unknown) and cast at read time. ---
const Bucketed = z.object({
  data: z.array(z.object({
    starting_at: z.string(),
    results: z.array(z.record(z.unknown())),
  })),
});
const CostEnvelope = Bucketed;
const UsageEnvelope = Bucketed;

export interface CostBucket { day: string; workspaceId: string; amount: number }

/**
 * Cost Report `amount` is in the smallest currency unit (cents), as a decimal
 * string — e.g. "123.45" in "USD" means $1.23 (per the Admin API reference).
 * Convert to dollars at the boundary so every consumer reads real USD.
 */
function centsToUsd(amount: unknown): number {
  return Number(amount) / 100;
}
export interface UsageBucket { day: string; key: string; tokens: number; cacheRead: number }
export interface DescCost { model: string | null; costType: string | null; amount: number }

/** workspace_id → friendly name (paginates). */
export async function listWorkspaces(): Promise<Map<string, string>> {
  const map = new Map<string, string>();
  let page: string | undefined;
  do {
    const json: unknown = await adminGet("/v1/organizations/workspaces", page ? { limit: "100", page } : { limit: "100" });
    const parsed = z.object({ data: z.array(z.object({ id: z.string(), name: z.string() })), has_more: z.boolean().optional(), next_page: z.string().nullable().optional() }).parse(json);
    for (const w of parsed.data) map.set(w.id, w.name);
    page = parsed.has_more ? (parsed.next_page ?? undefined) : undefined;
  } while (page);
  return map;
}

/** Daily billed cost by workspace over [start, end) (ISO). */
export async function costReportByWorkspace(startIso: string, endIso: string): Promise<CostBucket[]> {
  const json = await adminGet("/v1/organizations/cost_report", {
    starting_at: startIso,
    ending_at: endIso,
    bucket_width: "1d",
    limit: "31",
    "group_by[]": ["workspace_id"],
  });
  const env_ = CostEnvelope.parse(json);
  const out: CostBucket[] = [];
  for (const bucket of env_.data) {
    for (const r of bucket.results) {
      const amt = centsToUsd(r.amount); // API returns cents; store dollars
      if (amt > 0) out.push({ day: bucket.starting_at.slice(0, 10), workspaceId: String(r.workspace_id ?? "(none)"), amount: amt });
    }
  }
  return out;
}

/**
 * Billed cost grouped by `description` over [start, end). The description carries
 * parsed `model`, `cost_type` (tokens / web_search / code_execution / session_usage)
 * and `token_type`, so we can attribute real $ to each model and cost category —
 * a breakdown the workspace grouping can't give.
 */
export async function costReportByDescription(startIso: string, endIso: string): Promise<DescCost[]> {
  const json = await adminGet("/v1/organizations/cost_report", {
    starting_at: startIso,
    ending_at: endIso,
    bucket_width: "1d",
    limit: "31",
    "group_by[]": ["description"],
  });
  const env_ = CostEnvelope.parse(json);
  const out: DescCost[] = [];
  for (const bucket of env_.data) {
    for (const r of bucket.results) {
      const amt = centsToUsd(r.amount); // cents → USD
      if (amt > 0) {
        out.push({
          model: r.model != null ? String(r.model) : null,
          costType: r.cost_type != null ? String(r.cost_type) : null,
          amount: amt,
        });
      }
    }
  }
  return out;
}

/** Daily token usage grouped by one dimension (model / service_tier / workspace_id …). */
export async function usageReportBy(startIso: string, endIso: string, dimension: string): Promise<UsageBucket[]> {
  const json = await adminGet("/v1/organizations/usage_report/messages", {
    starting_at: startIso,
    ending_at: endIso,
    bucket_width: "1d",
    limit: "31",
    "group_by[]": [dimension],
  });
  const env_ = UsageEnvelope.parse(json);
  const num = (v: unknown) => (typeof v === "number" ? v : Number(v) || 0);
  const out: UsageBucket[] = [];
  for (const bucket of env_.data) {
    for (const r of bucket.results) {
      // Per the Usage Report schema: there is no `input_tokens` or flat
      // `cache_creation_input_tokens` field. Inputs are `uncached_input_tokens`
      // + `cache_read_input_tokens`, and cache creation is a nested object.
      const cc = (r.cache_creation ?? {}) as Record<string, unknown>;
      const cacheCreation = num(cc.ephemeral_1h_input_tokens) + num(cc.ephemeral_5m_input_tokens);
      const tokens =
        num(r.uncached_input_tokens) + num(r.output_tokens) +
        num(r.cache_read_input_tokens) + cacheCreation;
      out.push({
        day: bucket.starting_at.slice(0, 10),
        key: String(r[dimension] ?? "(none)"),
        tokens,
        cacheRead: num(r.cache_read_input_tokens),
      });
    }
  }
  return out;
}
