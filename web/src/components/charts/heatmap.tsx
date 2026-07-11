"use client";

import { EChart, type ChartOption } from "./echart";

const HOURS = Array.from({ length: 24 }, (_, h) => `${h}`);
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/**
 * Weekday × hour-of-day activity heatmap. `cells` is a 7×24 grid of values
 * (cells[weekday][hour]); darker = more activity.
 */
export function ActivityHeatmap({
  cells,
  ariaLabel,
}: {
  cells: number[][];
  ariaLabel?: string;
}) {
  // Only emit non-zero cells so empty hours stay blank (Grafana-style) instead
  // of all rendering as the lowest heat color.
  const points: [number, number, number][] = [];
  let max = 0;
  for (let d = 0; d < 7; d++) {
    for (let h = 0; h < 24; h++) {
      const v = cells[d]?.[h] ?? 0;
      if (v > max) max = v;
      if (v > 0) points.push([h, d, v]);
    }
  }
  if (max === 0) {
    return (
      <div className="flex h-[220px] items-center justify-center text-sm text-[var(--color-muted)]">
        No data
      </div>
    );
  }

  const option: ChartOption = {
    tooltip: {
      position: "top",
      formatter: (p) => {
        const a = p as unknown as { data: [number, number, number] };
        return `${WEEKDAYS[a.data[1]]} ${a.data[0]}:00 — ${a.data[2].toLocaleString("en-US")}`;
      },
    },
    grid: { left: 44, right: 12, top: 10, bottom: 56, containLabel: true },
    // No splitArea bands — empty hours show the panel background (Grafana-style),
    // so the colored cells read cleanly in both themes.
    xAxis: { type: "category", data: HOURS, splitArea: { show: false }, axisLabel: { interval: 2 } },
    yAxis: { type: "category", data: WEEKDAYS, splitArea: { show: false } },
    visualMap: {
      min: 0,
      max,
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      itemHeight: 90,
      // High-contrast heat scale (cool → warm) — readable in light and dark.
      inRange: {
        color: ["#1f6feb", "#16a34a", "#eab308", "#f97316", "#ef4444"],
      },
      show: true,
    },
    series: [
      {
        type: "heatmap",
        data: points,
        itemStyle: { borderColor: "var(--color-panel)", borderWidth: 1 },
        emphasis: { itemStyle: { shadowBlur: 6, shadowColor: "rgba(10,108,255,0.5)" } },
      },
    ],
  };

  return <EChart option={option} height={260} ariaLabel={ariaLabel} />;
}
