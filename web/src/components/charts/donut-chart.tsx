"use client";

import { EChart, type ChartOption } from "./echart";
import type { LabelledValue } from "@/lib/prometheus/reduce";

/** Donut chart — the equivalent of a Grafana `piechart` panel. */
export function DonutChart({
  data,
  valuePrefix = "",
  ariaLabel,
}: {
  data: LabelledValue[];
  valuePrefix?: string;
  ariaLabel?: string;
}) {
  if (data.length === 0) {
    return (
      <div className="flex h-[260px] items-center justify-center text-sm text-[var(--color-muted)]">
        No data
      </div>
    );
  }

  const option: ChartOption = {
    tooltip: {
      trigger: "item",
      valueFormatter: (v) => `${valuePrefix}${Number(v).toLocaleString("en-US")}`,
    },
    legend: {
      type: "scroll",
      orient: "vertical",
      right: 0,
      top: "center",
    },
    series: [
      {
        type: "pie",
        radius: ["48%", "72%"],
        center: ["36%", "50%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: "var(--color-panel)", borderWidth: 2 },
        label: { show: false },
        data: data.map((d) => ({ name: d.label || "(none)", value: d.value })),
      },
    ],
  };

  return <EChart option={option} ariaLabel={ariaLabel} />;
}
