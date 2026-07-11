"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { MetricDoc } from "@/lib/metric-docs";

/**
 * An accessible "(i)" button that reveals a small popover explaining a metric:
 * what it measures, where the data comes from, and how it's calculated.
 *
 * The popover is rendered in a portal on <body> with fixed positioning, so it
 * is never clipped by an ancestor's `overflow-hidden` (e.g. KPI cards) — which
 * otherwise made it look nested/cut-off inside the card.
 */
export function InfoButton({ doc }: { doc: MetricDoc }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; right: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Position the portal popover under the button, right-aligned to it.
  useLayoutEffect(() => {
    if (!open || !btnRef.current) return;
    const r = btnRef.current.getBoundingClientRect();
    setPos({ top: r.bottom + 6, right: Math.max(8, window.innerWidth - r.right) });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      const t = e.target as Node;
      if (btnRef.current?.contains(t) || panelRef.current?.contains(t)) return;
      setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    // A scroll moves the anchor; close rather than let the popover detach.
    function onScroll() {
      setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [open]);

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        aria-label={`About: ${doc.title}`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-[var(--color-panel-border)] text-[10px] font-bold leading-none text-[var(--color-muted)] transition-colors hover:border-[var(--color-scopic)] hover:text-[var(--color-scopic)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-scopic)]"
      >
        i
      </button>
      {open &&
        pos &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            ref={panelRef}
            role="dialog"
            style={{ position: "fixed", top: pos.top, right: pos.right }}
            className="z-[100] w-72 rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] p-3 text-left shadow-xl"
          >
            <p className="text-sm font-semibold text-[var(--color-text)]">{doc.title}</p>
            <p className="mt-1 text-xs leading-relaxed text-[var(--color-muted)]">{doc.what}</p>
            <dl className="mt-2 space-y-1.5 text-xs">
              <div>
                <dt className="font-medium text-[var(--color-scopic)]">Source</dt>
                <dd className="text-[var(--color-muted)]">{doc.source}</dd>
              </div>
              <div>
                <dt className="font-medium text-[var(--color-scopic)]">How it&apos;s calculated</dt>
                <dd className="text-[var(--color-muted)]">{doc.calc}</dd>
              </div>
              {doc.query && (
                <div>
                  <dt className="font-medium text-[var(--color-scopic)]">Query</dt>
                  <dd>
                    <code className="block break-words rounded bg-[var(--color-panel-2)] px-1.5 py-1 font-mono text-[10px] text-[var(--color-text)]">
                      {doc.query}
                    </code>
                  </dd>
                </div>
              )}
            </dl>
          </div>,
          document.body,
        )}
    </>
  );
}
