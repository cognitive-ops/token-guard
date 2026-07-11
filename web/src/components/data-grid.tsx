import type { ReactNode } from "react";
import { TableFilterShell } from "@/components/table-filter-shell";

export interface Column<T> {
  key: string;
  header: string;
  align?: "left" | "right";
  /** Render a cell; defaults to the raw value. */
  render: (row: T) => ReactNode;
}

/**
 * Generic, theme-aware table with a sticky header and scroll — used for the
 * leaderboard, intent-by-developer, language-by-developer, etc. Keeps markup in
 * one place so every table looks consistent.
 */
export function DataGrid<T>({
  rows,
  columns,
  getKey,
  maxHeight = "max-h-[460px]",
  emptyLabel = "No data.",
  searchable,
  searchPlaceholder = "Filter rows…",
}: {
  rows: T[];
  columns: Column<T>[];
  getKey: (row: T, i: number) => string;
  maxHeight?: string;
  emptyLabel?: string;
  /** Show a live filter box. Defaults on for tables with more than 10 rows. */
  searchable?: boolean;
  searchPlaceholder?: string;
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-[var(--color-muted)]">{emptyLabel}</p>;
  }
  const withFilter = searchable ?? rows.length > 10;
  const table = (
    <div className={`overflow-auto ${maxHeight}`}>
      <table className="w-full text-sm">
        <thead className="sticky top-0 z-10 bg-[var(--color-panel)]">
          <tr className="border-b border-[var(--color-panel-border)] text-xs uppercase tracking-wide text-[var(--color-muted)]">
            {columns.map((c) => (
              <th
                key={c.key}
                className={`py-2 pr-4 font-medium ${c.align === "right" ? "text-right" : "text-left"}`}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={getKey(row, i)}
              className="border-b border-[var(--color-panel-border)]/40 last:border-0 hover:bg-[var(--color-panel-2)]/50"
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={`py-2 pr-4 tabular-nums ${c.align === "right" ? "text-right" : "text-left"}`}
                >
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  if (!withFilter) return table;
  return (
    <TableFilterShell placeholder={searchPlaceholder} count={rows.length}>
      {table}
    </TableFilterShell>
  );
}
