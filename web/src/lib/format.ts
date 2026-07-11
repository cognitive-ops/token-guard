/**
 * Display formatting — Grafana's field "unit" options expressed as functions.
 * Locale fixed to en-US so server and client render identically (no hydration
 * mismatch).
 */
const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const compact = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export const formatUsd = (n: number): string => usd.format(n);
export const formatCompact = (n: number): string => compact.format(n);
export const formatInt = (n: number): string => integer.format(n);

/** Relative "x ago" for the exporter-health panel (dateTimeFromNow unit). */
export function formatAgo(unixSeconds: number, now: number): string {
  const diff = Math.max(0, now - unixSeconds);
  if (diff < 90) return `${Math.round(diff)}s ago`;
  if (diff < 5400) return `${Math.round(diff / 60)}m ago`;
  if (diff < 129600) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}
