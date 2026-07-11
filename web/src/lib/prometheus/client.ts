import "server-only";
import { env } from "@/lib/env";
import type { TimeRange } from "@/lib/time-range";
import { PromEnvelopeSchema, type Series } from "./types";
import { createLimiter } from "@/lib/limit";

// Separate pools so slow range scans don't starve fast instant/gauge reads.
const limitInstant = createLimiter(8);
const limitRange = createLimiter(4);

/** Fetch + validate a Prometheus query URL, under the concurrency limit. */
function promFetch(url: URL, expr: string): Promise<Series[]> {
  const limit = url.pathname.endsWith("/query") ? limitInstant : limitRange;
  return limit(async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), env.QUERY_TIMEOUT_MS);
    let res: Response;
    try {
      res = await fetch(url, {
        signal: controller.signal,
        next: { revalidate: env.REVALIDATE_SECONDS, tags: ["prometheus"] },
      });
    } catch (cause) {
      throw new PrometheusError(`Prometheus request failed: ${(cause as Error).message}`, expr, cause);
    } finally {
      clearTimeout(timeout);
    }
    if (!res.ok) throw new PrometheusError(`Prometheus returned HTTP ${res.status} for query`, expr);
    const parsed = PromEnvelopeSchema.safeParse(await res.json());
    if (!parsed.success) {
      throw new PrometheusError(`Unexpected Prometheus response shape: ${parsed.error.message}`, expr);
    }
    return toSeries(parsed.data.data);
  });
}

/**
 * Thin, typed Prometheus client.
 *
 * Design choices:
 * - Server-only. All datasource traffic happens in React Server Components /
 *   route handlers; the browser never talks to Prometheus directly.
 * - Always uses the *range* API (`/api/v1/query_range`). Reducing to a scalar
 *   is done in `reduce.ts`, not by the instant API — see the note there about
 *   the lagging relayed datasource.
 * - Validates every response with Zod (`PromEnvelopeSchema`).
 */

export class PrometheusError extends Error {
  constructor(
    message: string,
    readonly expr: string,
    readonly cause?: unknown,
  ) {
    super(message);
    this.name = "PrometheusError";
  }
}

function toSeries(
  data: ReturnType<typeof PromEnvelopeSchema.parse>["data"],
): Series[] {
  if (data.resultType === "matrix") {
    return data.result.map((r) => ({
      labels: r.metric,
      samples: r.values.map(([t, v]) => ({ t, v: Number(v) })),
    }));
  }
  // A vector result (single sample per series) is normalised to a 1-point series.
  return data.result.map((r) => ({
    labels: r.metric,
    samples: [{ t: r.value[0], v: Number(r.value[1]) }],
  }));
}

/**
 * Run a PromQL range query and return parsed series.
 *
 * Results are cached via Next.js fetch revalidation (`REVALIDATE_SECONDS`), so
 * repeated panels sharing a query don't hammer Prometheus — the equivalent of
 * Grafana's per-panel query plus its query cache.
 */
/**
 * Run a PromQL *instant* query at `atUnixSec` and return parsed series.
 *
 * Used for "total/breakdown over a window" panels — `sum(increase(m[30d]))`
 * evaluated ONCE at the window end, the way Grafana does it. Running these as
 * range queries recomputes the long-window increase at every step, which is
 * enormously expensive and causes timeouts (→ empty panels). The long lookback
 * window means there are always samples inside it, so unlike a short-window
 * instant query this stays robust on the lagging relayed datasource too.
 */
export function queryInstant(expr: string, atUnixSec: number): Promise<Series[]> {
  const url = new URL("/api/v1/query", env.PROMETHEUS_URL);
  url.searchParams.set("query", expr);
  url.searchParams.set("time", String(atUnixSec));
  return promFetch(url, expr);
}

export function queryRange(expr: string, range: TimeRange): Promise<Series[]> {
  const url = new URL("/api/v1/query_range", env.PROMETHEUS_URL);
  url.searchParams.set("query", expr);
  url.searchParams.set("start", String(range.start));
  url.searchParams.set("end", String(range.end));
  url.searchParams.set("step", String(range.step));
  return promFetch(url, expr);
}
