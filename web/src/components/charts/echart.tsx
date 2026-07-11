"use client";

import { useEffect, useRef } from "react";
import { useTheme } from "next-themes";
// Tree-shaken ECharts: core + only the chart types/components we use.
import * as echarts from "echarts/core";
import { PieChart, LineChart, BarChart, HeatmapChart } from "echarts/charts";
import {
  TooltipComponent,
  LegendComponent,
  GridComponent,
  VisualMapComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { ComposeOption } from "echarts/core";
import type {
  PieSeriesOption,
  LineSeriesOption,
  BarSeriesOption,
  HeatmapSeriesOption,
} from "echarts/charts";
import type {
  TooltipComponentOption,
  LegendComponentOption,
  GridComponentOption,
  VisualMapComponentOption,
} from "echarts/components";
import { echartsTheme } from "./theme";

echarts.use([
  PieChart,
  LineChart,
  BarChart,
  HeatmapChart,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

export type ChartOption = ComposeOption<
  | PieSeriesOption
  | LineSeriesOption
  | BarSeriesOption
  | HeatmapSeriesOption
  | TooltipComponentOption
  | LegendComponentOption
  | GridComponentOption
  | VisualMapComponentOption
>;

/**
 * Theme-aware ECharts wrapper. Re-initialises with the matching light/dark
 * theme whenever the resolved theme changes, and resizes with its container.
 */
export function EChart({
  option,
  height = 280,
  ariaLabel,
}: {
  option: ChartOption;
  height?: number;
  ariaLabel?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const { resolvedTheme } = useTheme();
  const mode: "light" | "dark" = resolvedTheme === "light" ? "light" : "dark";

  useEffect(() => {
    if (!ref.current) return;
    const themeName = `scopic-${mode}`;
    echarts.registerTheme(themeName, echartsTheme(mode));
    const chart = echarts.init(ref.current, themeName, { renderer: "canvas" });
    chart.setOption(option);
    chartRef.current = chart;

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
    // Re-init on theme change so axis/text colors flip. `option` applied below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  return (
    <div
      ref={ref}
      role="img"
      aria-label={ariaLabel}
      style={{ height, width: "100%", backgroundColor: "transparent" }}
    />
  );
}
