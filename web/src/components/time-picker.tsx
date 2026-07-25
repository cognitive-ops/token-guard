"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useState } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { TIME_PRESETS } from "@/lib/time-range";

/**
 * Comprehensive time-range picker: many quick presets (1h → 1 year) plus a
 * custom from/to range. Selection is written to the URL (`?range=` or
 * `?from=&to=`) so the active window is shareable and survives reloads.
 */
export function TimePicker({
  activeToken,
  activeLabel,
}: {
  activeToken: string;
  activeLabel: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  function push(next: URLSearchParams) {
    setOpen(false);
    // Navigate immediately (no startTransition): with a transition the URL
    // change is withheld until the new — heavy — page finishes rendering, which
    // reads as "nothing happened". A direct push updates the URL now and streams
    // the new data in via Suspense.
    router.push(`${pathname}?${next.toString()}`);
  }

  function selectPreset(id: string) {
    const next = new URLSearchParams(params);
    next.set("range", id);
    next.delete("from");
    next.delete("to");
    push(next);
    setOpen(false);
  }

  function applyCustom() {
    const fromSec = Math.floor(new Date(from).getTime() / 1000);
    const toSec = Math.floor(new Date(to).getTime() / 1000);
    if (!Number.isFinite(fromSec) || !Number.isFinite(toSec) || toSec <= fromSec) return;
    const next = new URLSearchParams(params);
    next.set("from", String(fromSec));
    next.set("to", String(toSec));
    next.delete("range");
    push(next);
    setOpen(false);
  }

  return (
    <DropdownMenu.Root open={open} onOpenChange={setOpen}>
      <DropdownMenu.Trigger
        aria-label="Time range"
        className="flex items-center gap-2 rounded-md border border-[var(--color-panel-border)] bg-[var(--color-panel)] px-3 py-1.5 text-sm font-medium text-[var(--color-text)] transition-colors hover:border-[var(--color-brand)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]"
      >
        <ClockIcon />
        {activeLabel}
        <ChevronIcon />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          className="z-50 w-64 rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] p-2 shadow-xl"
        >
          <div className="grid grid-cols-2 gap-1">
            {TIME_PRESETS.map((p) => (
              <DropdownMenu.Item
                key={p.id}
                onSelect={() => selectPreset(p.id)}
                className={`cursor-pointer rounded-md px-2.5 py-1.5 text-sm outline-none data-[highlighted]:bg-[var(--color-panel-2)] ${
                  activeToken === p.id
                    ? "font-semibold text-[var(--color-brand)]"
                    : "text-[var(--color-text)]"
                }`}
              >
                {p.label.replace("Last ", "")}
              </DropdownMenu.Item>
            ))}
          </div>

          <DropdownMenu.Separator className="my-2 h-px bg-[var(--color-panel-border)]" />

          <div className="px-1 pb-1">
            <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-[var(--color-muted)]">
              Custom range
            </p>
            <label className="mb-1 block text-[11px] text-[var(--color-muted)]">From</label>
            <input
              type="datetime-local"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="mb-2 w-full rounded-md border border-[var(--color-panel-border)] bg-[var(--color-bg)] px-2 py-1 text-xs outline-none focus:border-[var(--color-brand)]"
            />
            <label className="mb-1 block text-[11px] text-[var(--color-muted)]">To</label>
            <input
              type="datetime-local"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="mb-2 w-full rounded-md border border-[var(--color-panel-border)] bg-[var(--color-bg)] px-2 py-1 text-xs outline-none focus:border-[var(--color-brand)]"
            />
            <button
              onClick={applyCustom}
              disabled={!from || !to}
              className="w-full rounded-md bg-[var(--color-brand)] px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-40"
            >
              Apply custom range
            </button>
          </div>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function ClockIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}
function ChevronIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--color-muted)]">
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}
