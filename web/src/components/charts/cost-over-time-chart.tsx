"use client";

import { EChart, type ChartOption } from "./echart";

export interface TimeSeriesPoint {
  /** unix seconds */
  t: number;
  /** map of series name → value at this bucket */
  series: Record<string, number>;
}

/**
 * Generic multi-series time chart (Grafana `timeseries`). Stacked area by
 * default; used for cost-by-model, prompts, LOC-by-type, tokens, etc.
 */
const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "Jun 3" from unix seconds, in UTC (buckets are UTC midnight). */
function dayLabelUTC(t: number): string {
  const d = new Date(t * 1000);
  return `${MONTHS_SHORT[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

export function TimeSeriesChart({
  points,
  unitPrefix = "",
  decimals = 2,
  stack = true,
  smooth = false,
  kind = "line",
  height = 300,
  ariaLabel,
  categoryDay = false,
}: {
  points: TimeSeriesPoint[];
  unitPrefix?: string;
  decimals?: number;
  stack?: boolean;
  smooth?: boolean;
  /** "bar" for discrete counts (prompts) so empty periods show as missing bars. */
  kind?: "line" | "bar";
  height?: number;
  ariaLabel?: string;
  /**
   * Render the x-axis as one labelled category per point ("Jun 1", "Jun 2", …)
   * instead of a continuous time axis. Use for dense daily bar series (e.g.
   * cost-over-the-month) so every day is an evenly-spaced, clearly-labelled bar.
   */
  categoryDay?: boolean;
}) {
  if (points.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm text-[var(--color-muted)]" style={{ height }}>
        No data
      </div>
    );
  }

  const names = [...new Set(points.flatMap((p) => Object.keys(p.series)))].sort();
  const fmt = (v: number) =>
    `${unitPrefix}${Number(v).toLocaleString("en-US", { maximumFractionDigits: decimals })}`;

  const isBar = kind === "bar";
  const option: ChartOption = {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: isBar ? "shadow" : "line" },
      valueFormatter: (v) => fmt(Number(v)),
    },
    legend: { type: "scroll", bottom: 0, show: names.length > 1 },
    grid: { left: 56, right: 20, top: 16, bottom: names.length > 1 ? 44 : 24, containLabel: true },
    xAxis: categoryDay
      ? {
          type: "category",
          data: points.map((p) => dayLabelUTC(p.t)),
          // One tick per bar; thin labels automatically so they never overlap.
          axisTick: { alignWithLabel: true },
          axisLabel: { hideOverlap: true, interval: "auto" },
        }
      : { type: "time" },
    yAxis: { type: "value", minInterval: isBar ? 1 : undefined, axisLabel: { formatter: (v: number) => fmt(v) } },
    series: names.map((name) => ({
      name,
      type: isBar ? "bar" : "line",
      stack: stack ? "total" : undefined,
      // Bars: each time bucket is its own bar, so empty periods show as gaps
      // (a missing/zero bar) instead of a misleading connected line.
      ...(isBar
        ? { barMaxWidth: 18, itemStyle: { borderRadius: [2, 2, 0, 0] } }
        : { areaStyle: stack ? { opacity: 0.18 } : undefined, lineStyle: { width: 2 }, showSymbol: false, smooth }),
      // Category axis aligns plain values to xAxis.data; time axis needs [ts, v] pairs.
      data: categoryDay
        ? points.map((p) => p.series[name] ?? 0)
        : points.map((p) => [p.t * 1000, p.series[name] ?? 0]),
    })),
  };

  return <EChart option={option} height={height} ariaLabel={ariaLabel ?? "Time series"} />;
}

/** Back-compat alias for the Real Cost page. */
export const CostOverTimeChart = TimeSeriesChart;
