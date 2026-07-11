import "server-only";
import { unstable_cache } from "next/cache";
import { queryInstant, queryRange } from "@/lib/prometheus/client";
import { lokiInstant, lokiRange } from "@/lib/loki/client";
import {
  lastNotNull,
  scalarFromSeries,
  valuesByLabel,
  type LabelledValue,
} from "@/lib/prometheus/reduce";
import type { Series } from "@/lib/prometheus/types";
import { freshnessSeconds, resolveRange, type TimeRange } from "@/lib/time-range";
import type { TimeSeriesPoint } from "@/components/charts/cost-over-time-chart";

/**
 * Shared building blocks for every dashboard's data layer.
 *
 * Pattern: pages pass a stable range *token* (e.g. "30d" or "custom:from-to").
 * Loaders resolve it to a concrete window with the request-time clock, and wrap
 * the whole computation in `unstable_cache` keyed by (name, token) so repeated
 * requests within REVALIDATE_SECONDS are served from memory — fast, smooth, and
 * easy on the datasources. Any single failed query degrades to empty rather
 * than blanking the page.
 */

export type { LabelledValue, TimeSeriesPoint, TimeRange };

export function rangeFromToken(token: string): TimeRange {
  return resolveRange(token, Math.floor(Date.now() / 1000));
}

/** Cache a loader by (name, token), revalidating proportionally to the window
 * so short, near-live windows (1h) stay fresh and long windows (30d) stay
 * cached — matching the Loki instant-query bucket. */
export function cached<T>(name: string, token: string, fn: () => Promise<T>): Promise<T> {
  return unstable_cache(fn, [name, token], {
    revalidate: freshnessSeconds(rangeFromToken(token).windowSeconds),
    tags: ["dashboards"],
  })();
}

export async function safe<T>(label: string, fn: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await fn();
  } catch (err) {
    console.error(`[dashboard] query "${label}" failed:`, err);
    return fallback;
  }
}

// --- Prometheus reducers over a TimeRange ---

/**
 * "Total/breakdown over a window" panels run a RANGE query (robust to gappy
 * seed/relayed data) and take the last non-null value — Grafana's `lastNotNull`.
 *
 * The last sample sits up to one `step` before `now`. Short windows (1h) need a
 * small step or that lag skews the total; long windows (30d) tolerate a coarse
 * ~16-point step (lag is negligible, expensive increase() runs fewer times). So:
 * use the fresh step unless it would exceed ~240 points, else go coarse.
 */
function coarseStep(windowSeconds: number): number {
  const fresh = freshnessSeconds(windowSeconds);
  return windowSeconds / fresh <= 240 ? fresh : Math.round(windowSeconds / 16);
}

function coarse(range: TimeRange): TimeRange {
  return { ...range, step: coarseStep(range.windowSeconds) };
}

/** Latest value of a single-series gauge (e.g. exporter gauges). */
export async function promGauge(label: string, expr: string, range: TimeRange) {
  const s = await safe(label, () => queryRange(expr, coarse(range)), [] as Series[]);
  return s[0] ? lastNotNull(s[0]) : null;
}

/** Scalar from a `sum(increase(...[window]))` or gauge query, over the window. */
export async function promScalar(label: string, expr: string, range: TimeRange) {
  return scalarFromSeries(await safe(label, () => queryRange(expr, coarse(range)), [] as Series[]));
}

/** `{label,value}[]` from a `sum by (lbl)(...)` query, sorted desc. */
export async function promByLabel(
  label: string,
  expr: string,
  groupLabel: string,
  range: TimeRange,
): Promise<LabelledValue[]> {
  return valuesByLabel(await safe(label, () => queryRange(expr, coarse(range)), [] as Series[]), groupLabel);
}

/**
 * `{label,value}[]` from a materialized snapshot gauge, broken out by label,
 * read with an INSTANT query at the window end.
 *
 * Snapshot gauges (`claude_prompt_{language,intent,behavior,command}_count`) are
 * `GAUGE.clear()`-ed and repopulated each hourly poll, so the SET of label values
 * changes over time — a language that stops being detected drops out. A range
 * query + `lastNotNull` resurrects every category that held a sample anywhere in
 * the (≤30d) window, so stale classifications linger for ~30 days. An instant
 * read reflects only the latest poll — exactly how Grafana reads these gauges.
 */
export async function promByLabelInstant(
  label: string,
  expr: string,
  groupLabel: string,
  range: TimeRange,
): Promise<LabelledValue[]> {
  return valuesByLabel(await safe(label, () => queryInstant(expr, range.end), [] as Series[]), groupLabel);
}

/** Scalar from a snapshot gauge, read with an INSTANT query (see promByLabelInstant). */
export async function promScalarInstant(label: string, expr: string, range: TimeRange) {
  return scalarFromSeries(await safe(label, () => queryInstant(expr, range.end), [] as Series[]));
}

// --- Loki reducers over a TimeRange ---

/** Scalar from a LogQL instant metric query (summed across series). */
export async function lokiScalarSafe(label: string, expr: string, range: TimeRange) {
  const s = await safe(label, () => lokiInstant(expr, range), [] as Series[]);
  return s.reduce((acc, x) => acc + (x.samples.at(-1)?.v ?? 0), 0);
}

/** `{label,value}[]` from a LogQL `sum by (lbl)(count_over_time(...))`. */
export async function lokiByLabel(
  label: string,
  expr: string,
  groupLabel: string,
  range: TimeRange,
): Promise<LabelledValue[]> {
  return valuesByLabel(await safe(label, () => lokiInstant(expr, range), [] as Series[]), groupLabel);
}

// --- Prometheus-snapshot / Loki hybrid -------------------------------------
//
// The prompt-intent / prompt-lang exporters materialize per-user prompt
// classification counts into Prometheus gauges (`claude_prompt_*_count`,
// `claude_prompt_count`), recomputed hourly over a FIXED ~30d lookback. Reading
// those is <1ms; the equivalent Loki `count_over_time` scan of the full
// claude-code stream (filtered on a structured-metadata user_email) is ~2–5s.
//
// Because the gauge is a fixed snapshot it can't honor an arbitrary time
// window, so we only take the fast path when the selected window is ~30d or
// wider (the dashboard default — and where Loki is clamped to 30d anyway, so the
// two agree). Shorter/custom windows fall back to the time-accurate Loki path.
// A 28d floor leaves slack for the exporter's 29–30d lookback. If the snapshot
// is empty for the entity (exporter mid-refresh) we also fall back to Loki, so a
// panel never blanks.

/** Window at/above which the materialized ~30d prompt snapshot is used. */
export const SNAPSHOT_WINDOW_SECONDS = 28 * 86_400;

export const isSnapshotWindow = (range: TimeRange): boolean =>
  range.windowSeconds >= SNAPSHOT_WINDOW_SECONDS;

/** Scalar via the Prometheus snapshot gauge for ~30d windows, else Loki. */
export async function snapshotScalar(
  label: string,
  promExpr: string,
  lokiExpr: string,
  range: TimeRange,
): Promise<number> {
  if (isSnapshotWindow(range)) {
    const n = await promScalarInstant(`${label}Snap`, promExpr, range);
    if (n > 0) return n;
  }
  return lokiScalarSafe(label, lokiExpr, range);
}

/** `{label,value}[]` via the Prometheus snapshot gauge for ~30d windows, else Loki. */
export async function snapshotByLabel(
  label: string,
  promExpr: string,
  lokiExpr: string,
  groupLabel: string,
  range: TimeRange,
): Promise<LabelledValue[]> {
  if (isSnapshotWindow(range)) {
    const rows = await promByLabelInstant(`${label}Snap`, promExpr, groupLabel, range);
    if (rows.length) return rows;
  }
  return lokiByLabel(label, lokiExpr, groupLabel, range);
}

// --- Time-series pivots ---

/** Pivot Prometheus/Loki matrix series into time buckets keyed by one label. */
export function pivot(series: Series[], groupLabel: string): TimeSeriesPoint[] {
  const buckets = new Map<number, Record<string, number>>();
  for (const s of series) {
    const name = s.labels[groupLabel] ?? "value";
    for (const { t, v } of s.samples) {
      if (!Number.isFinite(v)) continue;
      const b = buckets.get(t) ?? {};
      b[name] = (b[name] ?? 0) + v;
      buckets.set(t, b);
    }
  }
  return [...buckets.entries()].sort(([a], [b]) => a - b).map(([t, series]) => ({ t, series }));
}

export async function promSeries(label: string, expr: string, groupLabel: string, range: TimeRange) {
  return pivot(await safe(label, () => queryRange(expr, range), [] as Series[]), groupLabel);
}

export async function lokiSeries(label: string, expr: string, groupLabel: string, range: TimeRange) {
  return pivot(await safe(label, () => lokiRange(expr, range), [] as Series[]), groupLabel);
}

/** Map of label → joined rows (for multi-metric tables like the leaderboard). */
export function indexByLabel(rows: LabelledValue[]): Map<string, number> {
  return new Map(rows.map((r) => [r.label, r.value]));
}
