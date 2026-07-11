import type { Series } from "./types";

/**
 * Pure reducers over parsed Prometheus series. Kept separate from the fetch
 * layer so the trickiest logic — the part that fixes a real bug we hit with
 * Grafana — is unit-testable without a live datasource.
 *
 * Why "last not-null" matters here: the relayed online datasource is a lagging
 * snapshot, so an *instant* query at `now` often returns empty (the scrape for
 * `now` hasn't arrived). We therefore always run a *range* query and reduce to
 * the most recent real sample — exactly Grafana's `lastNotNull` calc. This is
 * the documented gotcha for this stack, encoded once, here.
 */

/** Most recent finite sample in a series, or null if the series is empty/all-NaN. */
export function lastNotNull(series: Series): number | null {
  for (let i = series.samples.length - 1; i >= 0; i--) {
    const v = series.samples[i]?.v;
    if (v !== undefined && Number.isFinite(v)) return v;
  }
  return null;
}

/**
 * Collapse a multi-series matrix to a single scalar by summing each series'
 * last-not-null value. Mirrors a Grafana stat panel with a `sum()` query and a
 * `lastNotNull` reducer.
 */
export function scalarFromSeries(series: Series[]): number {
  return series.reduce((acc, s) => acc + (lastNotNull(s) ?? 0), 0);
}

/** One labelled datum: the value of a single label plus the reduced number. */
export interface LabelledValue {
  label: string;
  value: number;
}

/**
 * Reduce a matrix to `{ label, value }` rows keyed by one label (e.g. `model`,
 * `email`). Series missing the label or with no real samples are dropped.
 * Result is sorted by value descending — the default for the tables/pies we port.
 */
export function valuesByLabel(series: Series[], label: string): LabelledValue[] {
  const rows: LabelledValue[] = [];
  for (const s of series) {
    const labelValue = s.labels[label];
    if (labelValue === undefined) continue;
    const v = lastNotNull(s);
    if (v === null) continue;
    rows.push({ label: labelValue, value: v });
  }
  return rows.sort((a, b) => b.value - a.value);
}
