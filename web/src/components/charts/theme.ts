/**
 * Shared ECharts palette + per-mode theme objects so charts read as one
 * professional, Scopic-blue family and stay legible in both light and dark.
 */
// Categorical palette — a refined, professional set anchored on Scopic blue.
// Moderately-saturated, harmonious hues (not neon), ordered so ADJACENT series
// alternate across the wheel and stay legible in both light and dark.
export const PALETTE = [
  "#3667d6", // blue (Scopic primary)
  "#2bb6a6", // teal
  "#7a5cf0", // indigo
  "#e8a13c", // amber
  "#d65f8a", // rose
  "#4aa3df", // sky
  "#5bb96a", // green
  "#c4663e", // terracotta
  "#9b7ad1", // lavender
  "#d4b13f", // gold
  "#5a8fb5", // steel
  "#cf5b5b", // muted red
];

interface Mode {
  text: string;
  muted: string;
  grid: string;
  tooltipBg: string;
  border: string;
}

const DARK: Mode = {
  text: "#c4ccd6",
  muted: "#8a93a2",
  grid: "#232c3f",
  tooltipBg: "#121826",
  border: "#232c3f",
};
const LIGHT: Mode = {
  text: "#27313f",
  muted: "#5a6775",
  grid: "#e6ebf2",
  tooltipBg: "#ffffff",
  border: "#dde4ee",
};

export function echartsTheme(mode: "light" | "dark") {
  const m = mode === "light" ? LIGHT : DARK;
  return {
    color: PALETTE,
    backgroundColor: "transparent",
    textStyle: { color: m.text, fontFamily: "inherit" },
    title: { textStyle: { color: m.text } },
    legend: { textStyle: { color: m.muted } },
    tooltip: {
      backgroundColor: m.tooltipBg,
      borderColor: m.border,
      textStyle: { color: m.text },
    },
    categoryAxis: {
      axisLine: { lineStyle: { color: m.grid } },
      axisTick: { lineStyle: { color: m.grid } },
      axisLabel: { color: m.muted },
      splitLine: { show: false, lineStyle: { color: m.grid } },
    },
    valueAxis: {
      axisLine: { lineStyle: { color: m.grid } },
      axisLabel: { color: m.muted },
      splitLine: { lineStyle: { color: m.grid } },
    },
    visualMap: { textStyle: { color: m.muted } },
  };
}
