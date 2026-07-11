"use client";

import { EChart, type ChartOption } from "./echart";
import type { LabelledValue } from "@/lib/prometheus/reduce";

/** Horizontal ranked bar chart (Grafana barchart) — top-N by value. */
export function BarChart({
  data,
  valuePrefix = "",
  valueSuffix = "",
  decimals = 0,
  maxBars = 30,
  ariaLabel,
}: {
  data: LabelledValue[];
  valuePrefix?: string;
  valueSuffix?: string;
  decimals?: number;
  maxBars?: number;
  ariaLabel?: string;
}) {
  if (data.length === 0) {
    return (
      <div className="flex h-[320px] items-center justify-center text-sm text-[var(--color-muted)]">
        No data
      </div>
    );
  }
  // ECharts y-axis renders bottom-up, so reverse for descending top-down.
  const rows = data.slice(0, maxBars).reverse();
  const fmt = (v: number) =>
    `${valuePrefix}${v.toLocaleString("en-US", { maximumFractionDigits: decimals })}${valueSuffix}`;

  const option: ChartOption = {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => fmt(Number(v)) },
    grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: "value", axisLabel: { formatter: (v: number) => fmt(v) } },
    yAxis: {
      type: "category",
      data: rows.map((r) => r.label || "(none)"),
      axisLabel: { width: 150, overflow: "truncate", fontFamily: "monospace", fontSize: 11 },
    },
    series: [
      {
        type: "bar",
        data: rows.map((r) => r.value),
        itemStyle: { color: "#0a6cff", borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: "right", formatter: (p) => fmt(Number(p.value)), fontSize: 11 },
      },
    ],
  };

  const height = Math.max(220, rows.length * 22 + 40);
  return <EChart option={option} height={Math.min(height, 700)} ariaLabel={ariaLabel} />;
}
