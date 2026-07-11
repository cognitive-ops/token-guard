"use client";

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

/**
 * Searchable developer picker (combobox). With dozens of developers a plain
 * dropdown is unwieldy, so this filters as you type. Writes `?user=` to the URL.
 */
export function UserSelect({ users, active }: { users: string[]; active: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? users.filter((u) => u.toLowerCase().includes(q)) : users;
  }, [users, query]);

  function select(email: string) {
    const next = new URLSearchParams(params);
    next.set("user", email);
    setOpen(false);
    setQuery("");
    // Direct push so the URL updates immediately (a transition would withhold it
    // until the heavy developer page finished rendering).
    router.push(`${pathname}?${next.toString()}`);
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label="Developer"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={`flex max-w-[260px] items-center gap-2 rounded-md border border-[var(--color-panel-border)] bg-[var(--color-panel)] px-3 py-1.5 text-sm font-medium text-[var(--color-text)] transition-colors hover:border-[var(--color-scopic)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-scopic)]`}
      >
        <UserIcon />
        <span className="truncate font-mono text-xs">{active || "Select developer"}</span>
        <ChevronIcon />
      </button>
      {open && (
        <div className="absolute right-0 top-10 z-50 w-80 overflow-hidden rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] shadow-xl">
          <div className="border-b border-[var(--color-panel-border)] p-2">
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search developers…"
              className="w-full rounded-md border border-[var(--color-panel-border)] bg-[var(--color-bg)] px-2.5 py-1.5 text-sm outline-none focus:border-[var(--color-scopic)]"
            />
          </div>
          <ul className="max-h-72 overflow-auto p-1">
            {filtered.length === 0 && (
              <li className="px-2.5 py-2 text-sm text-[var(--color-muted)]">No matches</li>
            )}
            {filtered.map((u) => (
              <li key={u}>
                <button
                  type="button"
                  onClick={() => select(u)}
                  className={`w-full truncate rounded-md px-2.5 py-1.5 text-left font-mono text-xs transition-colors hover:bg-[var(--color-panel-2)] ${
                    u === active ? "text-[var(--color-scopic)]" : "text-[var(--color-text)]"
                  }`}
                >
                  {u}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function UserIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" />
    </svg>
  );
}
function ChevronIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="ml-auto text-[var(--color-muted)]">
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}
