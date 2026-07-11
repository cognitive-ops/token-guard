/**
 * Time-range model.
 *
 * Grafana hides this behind its time picker and the `$__range` / `$__interval`
 * macros. Here it is explicit and testable. The UI drives it through the URL:
 * either a preset (`?range=24h`) or a custom window (`?from=…&to=…`, unix
 * seconds), which makes every view shareable and bookmarkable.
 */
export interface TimeRange {
  /** Inclusive start, unix seconds. */
  start: number;
  /** Inclusive end, unix seconds. */
  end: number;
  /** Resolution for range queries, in seconds (Grafana's `$__interval`). */
  step: number;
  /** Window length in seconds (Grafana's `$__range`). */
  windowSeconds: number;
  /** Human label for display, e.g. "Last 30 days". */
  label: string;
  /** Stable token used as a cache key (preset id or `custom:from-to`). */
  token: string;
}

const DAY = 86_400;

/** Comprehensive preset list shown in the time picker. */
export const TIME_PRESETS = [
  { id: "1h", label: "Last 1 hour", seconds: 3_600 },
  { id: "6h", label: "Last 6 hours", seconds: 21_600 },
  { id: "12h", label: "Last 12 hours", seconds: 43_200 },
  { id: "24h", label: "Last 24 hours", seconds: 86_400 },
  { id: "2d", label: "Last 2 days", seconds: 2 * DAY },
  { id: "7d", label: "Last 7 days", seconds: 7 * DAY },
  { id: "14d", label: "Last 14 days", seconds: 14 * DAY },
  { id: "30d", label: "Last 30 days", seconds: 30 * DAY },
  { id: "90d", label: "Last 90 days", seconds: 90 * DAY },
  { id: "180d", label: "Last 6 months", seconds: 180 * DAY },
  { id: "365d", label: "Last 1 year", seconds: 365 * DAY },
] as const;

export type PresetId = (typeof TIME_PRESETS)[number]["id"];

const PRESET_BY_ID = new Map(TIME_PRESETS.map((p) => [p.id, p]));

/**
 * Choose a step that yields ~`targetPoints` samples across the window, clamped
 * to a sane minimum. Coarser windows get coarser steps — exactly what Grafana's
 * `$__interval` does.
 */
export function chooseStep(windowSeconds: number, targetPoints = 90): number {
  const raw = Math.floor(windowSeconds / targetPoints);
  return Math.max(60, Math.ceil(raw / 60) * 60);
}

/**
 * How stale a window's data may be, scaled to the window length. Short,
 * near-live views (1h) stay fresh so they match Grafana's live `now`; long
 * windows (30d) tolerate up to 5-min staleness so their heavy count_over_time
 * queries keep hitting cache. Used for BOTH the Loki instant-query time bucket
 * and the app-level cache revalidate, so the two never disagree.
 */
export function freshnessSeconds(windowSeconds: number): number {
  return Math.min(300, Math.max(30, Math.round(windowSeconds * 0.01)));
}

/** Build a TimeRange from a window length ending at `now`. */
function build(
  windowSeconds: number,
  now: number,
  label: string,
  token: string,
): TimeRange {
  return {
    start: now - windowSeconds,
    end: now,
    step: chooseStep(windowSeconds),
    windowSeconds,
    label,
    token,
  };
}

/**
 * Resolve a range token into a concrete TimeRange. Tokens are stable strings so
 * they double as cache keys:
 *   - a preset id ("30d", "6h", …)
 *   - "custom:<fromSec>-<toSec>"
 * Falls back to `fallback` (default "30d") for anything unrecognised.
 */
export function resolveRange(
  token: string | undefined,
  now: number,
  fallback: PresetId = "30d",
): TimeRange {
  if (token?.startsWith("custom:")) {
    const [fromStr, toStr] = token.slice(7).split("-");
    const from = Number(fromStr);
    const to = Number(toStr);
    if (Number.isFinite(from) && Number.isFinite(to) && to > from) {
      const win = to - from;
      return {
        start: from,
        end: to,
        step: chooseStep(win),
        windowSeconds: win,
        label: "Custom range",
        token,
      };
    }
  }
  const preset = PRESET_BY_ID.get((token ?? fallback) as PresetId) ?? PRESET_BY_ID.get(fallback)!;
  return build(preset.seconds, now, preset.label, preset.id);
}

/** Build the range token from URL search params. */
export function rangeTokenFromParams(params: {
  range?: string;
  from?: string;
  to?: string;
}): string | undefined {
  if (params.from && params.to) {
    const from = Math.floor(Number(params.from));
    const to = Math.floor(Number(params.to));
    if (Number.isFinite(from) && Number.isFinite(to) && to > from) {
      return `custom:${from}-${to}`;
    }
  }
  return params.range;
}

/** Prometheus duration literal for a window, in seconds (e.g. `2592000s`). */
export function promWindow(seconds: number): string {
  return `${Math.max(60, Math.round(seconds))}s`;
}

// ---------------------------------------------------------------------------
// Legacy helpers (kept for existing unit tests + the simple day-based picker).
// ---------------------------------------------------------------------------

export const RANGE_PRESETS = [1, 7, 14, 30, 90] as const;
export type RangePreset = (typeof RANGE_PRESETS)[number];

export function isRangePreset(value: unknown): value is RangePreset {
  return typeof value === "number" && (RANGE_PRESETS as readonly number[]).includes(value);
}

export function parseRangeDays(
  param: string | string[] | undefined,
  fallbackDays: number,
): number {
  const raw = Array.isArray(param) ? param[0] : param;
  if (!raw) return fallbackDays;
  const match = /^(\d+)d$/.exec(raw.trim());
  if (!match) return fallbackDays;
  const days = Number(match[1]);
  return isRangePreset(days) ? days : fallbackDays;
}

export function rangeForDays(days: number, now: number): TimeRange {
  return build(days * DAY, now, `Last ${days} days`, `${days}d`);
}

export function asPromDuration(windowSeconds: number): string {
  return `${Math.round(windowSeconds / DAY)}d`;
}
