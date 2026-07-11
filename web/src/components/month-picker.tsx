"use client";

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";

/** Month selector for the API Cost dashboard — writes `?month=YYYY-MM`. */
export function MonthPicker({
  months,
  active,
}: {
  months: { token: string; label: string }[];
  active: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const activeLabel = months.find((m) => m.token === active)?.label ?? active;

  function select(token: string) {
    const next = new URLSearchParams(params);
    next.set("month", token);
    router.push(`${pathname}?${next.toString()}`);
  }

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        aria-label="Month"
        className="flex items-center gap-2 rounded-md border border-[var(--color-panel-border)] bg-[var(--color-panel)] px-3 py-1.5 text-sm font-medium text-[var(--color-text)] transition-colors hover:border-[var(--color-scopic)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-scopic)]"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <rect x="3" y="4" width="18" height="18" rx="2" /><path d="M3 10h18M8 2v4M16 2v4" />
        </svg>
        {activeLabel}
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="text-[var(--color-muted)]"><path d="m6 9 6 6 6-6" /></svg>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6} className="z-50 max-h-80 w-48 overflow-auto rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] p-1 shadow-xl">
          {months.map((m) => (
            <DropdownMenu.Item
              key={m.token}
              onSelect={() => select(m.token)}
              className={`cursor-pointer rounded-md px-2.5 py-1.5 text-sm outline-none data-[highlighted]:bg-[var(--color-panel-2)] ${
                m.token === active ? "font-semibold text-[var(--color-scopic)]" : "text-[var(--color-text)]"
              }`}
            >
              {m.label}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
