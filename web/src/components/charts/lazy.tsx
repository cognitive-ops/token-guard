"use client";

import dynamic from "next/dynamic";

/**
 * Lazy chart entrypoints. `ssr: false` keeps ECharts out of the server render
 * and the initial JS bundle — it's fetched only when a chart mounts. A skeleton
 * holds the layout so there's no content shift, keeping loads smooth.
 *
 * Defined in a client module because `ssr: false` is not allowed in a Server
 * Component; server sections import these wrappers and render them normally.
 */
function ChartSkeleton({ height = 280 }: { height?: number }) {
  return (
    <div className="animate-pulse rounded-md bg-[var(--color-panel-2)]" style={{ height }} />
  );
}

export const LazyDonutChart = dynamic(
  () => import("./donut-chart").then((m) => m.DonutChart),
  { ssr: false, loading: () => <ChartSkeleton height={260} /> },
);

export const LazyTimeSeriesChart = dynamic(
  () => import("./cost-over-time-chart").then((m) => m.TimeSeriesChart),
  { ssr: false, loading: () => <ChartSkeleton height={300} /> },
);

/** Back-compat alias used by the Real Cost page. */
export const LazyCostOverTimeChart = LazyTimeSeriesChart;

export const LazyBarChart = dynamic(
  () => import("./bar-chart").then((m) => m.BarChart),
  { ssr: false, loading: () => <ChartSkeleton height={320} /> },
);

export const LazyActivityHeatmap = dynamic(
  () => import("./heatmap").then((m) => m.ActivityHeatmap),
  { ssr: false, loading: () => <ChartSkeleton height={220} /> },
);
