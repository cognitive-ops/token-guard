import { InfoButton } from "@/components/info-button";
import type { MetricDoc } from "@/lib/metric-docs";

/** A headline stat tile (Grafana `stat`), with an optional (i) explanation. */
export function KpiCard({
  label,
  value,
  hint,
  info,
  accent = "var(--color-brand)",
  raw,
  hideWhenZero,
  compactValue,
}: {
  label: string;
  value: string;
  hint?: string;
  info?: MetricDoc;
  accent?: string;
  /** Raw numeric value, used by hideWhenZero. */
  raw?: number;
  /** Hide the card entirely when raw === 0 (a zero count carries no insight). */
  hideWhenZero?: boolean;
  /** Render value at a smaller, wrapping size — for long text (e.g. names). */
  compactValue?: boolean;
}) {
  if (hideWhenZero && raw === 0) return null;
  return (
    <div className="panel panel-hover relative overflow-hidden p-4">
      <span className="absolute inset-x-0 top-0 h-0.5" style={{ backgroundColor: accent }} />
      <div className="flex items-center justify-between gap-1">
        <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-muted)]">
          {label}
        </div>
        {info && <InfoButton doc={info} />}
      </div>
      <div
        className={
          compactValue
            ? "mt-1.5 line-clamp-2 text-base font-semibold leading-snug"
            : "mt-1.5 text-3xl font-bold tabular-nums"
        }
        style={{ color: accent }}
        title={compactValue ? value : undefined}
      >
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-[var(--color-muted)]">{hint}</div>}
    </div>
  );
}

/** A compact secondary stat with an optional (i) explanation. */
export function MiniStat({
  label,
  value,
  info,
  raw,
  hideWhenZero,
}: {
  label: string;
  value: string;
  info?: MetricDoc;
  raw?: number;
  hideWhenZero?: boolean;
}) {
  if (hideWhenZero && raw === 0) return null;
  return (
    <div className="panel px-4 py-3">
      <div className="flex items-center justify-between gap-1">
        <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-muted)]">
          {label}
        </div>
        {info && <InfoButton doc={info} />}
      </div>
      <div className="mt-1 text-xl font-semibold tabular-nums text-[var(--color-text)]">
        {value}
      </div>
    </div>
  );
}
