import type { DeveloperCostRow } from "@/lib/cost-model";
import type { LabelledValue } from "@/lib/prometheus/reduce";
import { formatUsd } from "@/lib/format";
import { TableFilterShell } from "@/components/table-filter-shell";

/**
 * The joined "Real Cost per Developer" table — seat fee, extra usage, and total
 * in one place. In Grafana this was two separate panels; here the join already
 * happened server-side (see cost-model.ts), so it renders as a single table.
 */
export function DeveloperCostTable({ rows }: { rows: DeveloperCostRow[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-[var(--color-muted)]">No data.</p>;
  }

  return (
    <TableFilterShell placeholder="Filter developers…" count={rows.length}>
    <div className="max-h-[420px] overflow-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-[var(--color-panel)]">
          <tr className="border-b border-[var(--color-panel-border)] text-left text-xs uppercase tracking-wide text-[var(--color-muted)]">
            <th className="py-2 pr-4 font-medium">Developer</th>
            <th className="py-2 pr-4 text-right font-medium">Seat fee</th>
            <th className="py-2 pr-4 text-right font-medium">Extra usage</th>
            <th className="py-2 text-right font-medium">Real cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.email}
              className="border-b border-[var(--color-panel-border)]/40 last:border-0 hover:bg-[var(--color-panel-2)]/40"
            >
              <td className="py-2 pr-4 font-mono text-xs">{r.email}</td>
              <td className="py-2 pr-4 text-right tabular-nums">
                {formatUsd(r.seatFee)}
              </td>
              <td
                className={`py-2 pr-4 text-right tabular-nums ${
                  r.extraUsage > 0 ? "text-[var(--color-violet)]" : "text-[var(--color-muted)]"
                }`}
              >
                {formatUsd(r.extraUsage)}
              </td>
              <td className="py-2 text-right font-semibold tabular-nums text-[var(--color-brand-light)]">
                {formatUsd(r.realCost)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    </TableFilterShell>
  );
}

/**
 * A ranked usage table with an inline proportion bar — for "X by user" lists
 * (the Grafana per-developer usage tables). `format` controls the value render.
 */
export function UsageTable({
  rows,
  unit,
  format,
  limit = 15,
}: {
  rows: LabelledValue[];
  unit: string;
  format: (n: number) => string;
  limit?: number;
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-[var(--color-muted)]">No data.</p>;
  }
  const max = rows[0]?.value || 1;
  const shown = rows.slice(0, limit);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs uppercase tracking-wide text-[var(--color-muted)]">
        <span>Developer</span>
        <span>{unit}</span>
      </div>
      {shown.map((r) => (
        <div key={r.label} className="group">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="truncate font-mono text-xs">{r.label || "(none)"}</span>
            <span className="tabular-nums text-[var(--color-text)]">
              {format(r.value)}
            </span>
          </div>
          <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-[var(--color-panel-2)]">
            <div
              className="h-full rounded-full bg-[var(--color-brand)]"
              style={{ width: `${Math.max(2, (r.value / max) * 100)}%` }}
            />
          </div>
        </div>
      ))}
      {rows.length > limit && (
        <p className="pt-1 text-xs text-[var(--color-muted)]">
          +{rows.length - limit} more
        </p>
      )}
    </div>
  );
}
