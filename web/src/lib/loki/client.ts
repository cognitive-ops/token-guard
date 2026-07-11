import "server-only";
import { z } from "zod";
import { env } from "@/lib/env";
import type { TimeRange } from "@/lib/time-range";
import type { Series } from "@/lib/prometheus/types";
import { createLimiter } from "@/lib/limit";

// Separate pools: fast instant queries (donuts/scalars) must not be starved by
// a slow 200-point range scan (a time-series). Each kind gets its own budget.
const limitInstant = createLimiter(3);
const limitRange = createLimiter(3);

/**
 * Loki client — mirrors the Prometheus client so LogQL metric queries
 * (count_over_time / avg_over_time over the event streams) reuse the same
 * Series shape and reducers.
 *
 * Two important Loki specifics handled here:
 * - Timestamps are nanoseconds.
 * - Windows are clamped to 30 days. Loki retains 90d, but a 90d
 *   count_over_time over the full event stream is heavy enough to overwhelm this
 *   single-binary Loki (drops connections), so we cap queries at 30d. A 1-year
 *   range still works — it just returns the last 30 days, the most we query.
 */
const MAX_WINDOW = 30 * 86_400;

const VectorOrMatrixResult = z.object({
  metric: z.record(z.string()).optional(),
  value: z.tuple([z.number(), z.string()]).optional(),
  values: z
    .array(z.tuple([z.union([z.number(), z.string()]), z.string()]))
    .optional(),
});

const LokiEnvelope = z.object({
  status: z.literal("success"),
  data: z.object({
    resultType: z.enum(["matrix", "vector", "streams", "scalar"]),
    result: z.array(VectorOrMatrixResult),
  }),
});

export class LokiError extends Error {
  constructor(message: string, readonly expr: string) {
    super(message);
    this.name = "LokiError";
  }
}

function clampStart(range: TimeRange): number {
  return Math.max(range.start, range.end - MAX_WINDOW);
}

function fetchLoki(
  path: string,
  search: Record<string, string>,
  expr: string,
): Promise<z.infer<typeof LokiEnvelope>> {
  const limit = path.endsWith("/query") ? limitInstant : limitRange;
  return limit(async () => {
    const url = new URL(path, env.LOKI_URL);
    for (const [k, v] of Object.entries(search)) url.searchParams.set(k, v);

    // Timeout starts once the query actually runs (after acquiring a slot).
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), env.QUERY_TIMEOUT_MS);
    let res: Response;
    try {
      res = await fetch(url, {
        signal: controller.signal,
        next: { revalidate: env.REVALIDATE_SECONDS, tags: ["loki"] },
      });
    } catch (cause) {
      throw new LokiError(`Loki request failed: ${(cause as Error).message}`, expr);
    } finally {
      clearTimeout(timeout);
    }
    if (!res.ok) throw new LokiError(`Loki returned HTTP ${res.status}`, expr);
    const parsed = LokiEnvelope.safeParse(await res.json());
    if (!parsed.success) throw new LokiError(`Unexpected Loki response: ${parsed.error.message}`, expr);
    return parsed.data;
  });
}

// Align the instant-query timestamp to a 5-min bucket. Loki's instant-metric
// results cache keys on the exact `time`; a per-second `now` would miss every
// request. Bucketing makes repeated/concurrent loads (and the 90d/365d ranges
// that share a clamped window) reuse the cached result — sub-second instead of
// ~4s. 5 min matches the dashboard's existing REVALIDATE staleness.
const CACHE_ALIGN_SECONDS = 300;

/** Instant LogQL metric query at `range.end` → Series[] (one sample each). */
export async function lokiInstant(expr: string, range: TimeRange): Promise<Series[]> {
  const alignedEnd = Math.floor(range.end / CACHE_ALIGN_SECONDS) * CACHE_ALIGN_SECONDS;
  const data = await fetchLoki(
    "/loki/api/v1/query",
    { query: expr, time: String(alignedEnd * 1_000_000_000) },
    expr,
  );
  return data.data.result.map((r) => ({
    labels: r.metric ?? {},
    samples: r.value ? [{ t: r.value[0], v: Number(r.value[1]) }] : [],
  }));
}

/** Range LogQL metric query → Series[] (matrix), window clamped to 30d. */
export async function lokiRange(expr: string, range: TimeRange): Promise<Series[]> {
  const data = await fetchLoki(
    "/loki/api/v1/query_range",
    {
      query: expr,
      start: String(clampStart(range) * 1_000_000_000),
      end: String(range.end * 1_000_000_000),
      step: String(range.step),
    },
    expr,
  );
  return data.data.result.map((r) => ({
    labels: r.metric ?? {},
    samples: (r.values ?? []).map(([t, v]) => ({ t: Number(t), v: Number(v) })),
  }));
}

/** Convenience: sum a single-series instant query to a scalar. */
export async function lokiScalar(expr: string, range: TimeRange): Promise<number> {
  const series = await lokiInstant(expr, range);
  return series.reduce((acc, s) => acc + (s.samples.at(-1)?.v ?? 0), 0);
}

/**
 * The Prometheus-style `[window]` duration to embed in LogQL, clamped to Loki's
 * 30d limit so count_over_time/avg_over_time never trip max_query_length.
 */
export function lokiWindow(range: TimeRange): string {
  return `${Math.min(range.windowSeconds, MAX_WINDOW)}s`;
}
