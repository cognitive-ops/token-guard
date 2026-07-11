"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Wraps a table with a live search box that filters rows by their text content
 * — works for any table without knowing its columns (matches on each row's
 * textContent). Server components can pass a server-rendered <table> as
 * children; only the filtering runs on the client.
 */
export function TableFilterShell({
  children,
  placeholder = "Filter…",
  count,
}: {
  children: ReactNode;
  placeholder?: string;
  count?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [q, setQ] = useState("");
  const [shown, setShown] = useState<number | null>(null);

  useEffect(() => {
    const rows = ref.current?.querySelectorAll<HTMLElement>("tbody tr");
    if (!rows) return;
    const needle = q.trim().toLowerCase();
    let visible = 0;
    rows.forEach((tr) => {
      const match = !needle || (tr.textContent ?? "").toLowerCase().includes(needle);
      tr.style.display = match ? "" : "none";
      if (match) visible++;
    });
    setShown(needle ? visible : null);
  }, [q]);

  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <div className="relative flex-1">
          <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-muted)]">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
            </svg>
          </span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={placeholder}
            className="w-full rounded-md border border-[var(--color-panel-border)] bg-[var(--color-bg)] py-1.5 pl-8 pr-3 text-sm outline-none focus:border-[var(--color-scopic)]"
          />
        </div>
        <span className="shrink-0 text-xs text-[var(--color-muted)]">
          {shown !== null ? `${shown} match${shown === 1 ? "" : "es"}` : count != null ? `${count} rows` : ""}
        </span>
      </div>
      <div ref={ref}>{children}</div>
    </div>
  );
}
