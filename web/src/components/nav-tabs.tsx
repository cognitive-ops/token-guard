"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/overview", label: "Overview" },
  { href: "/real-cost", label: "Real Cost" },
  { href: "/api-cost", label: "API Cost" },
  { href: "/usage-patterns", label: "Usage Patterns" },
  { href: "/developer", label: "Developer" },
] as const;

/** Top navigation tabs across the five dashboards, with active state. */
export function NavTabs() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1 overflow-x-auto">
      {TABS.map((t) => {
        const active = pathname.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            prefetch
            className={`whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              active
                ? "bg-[var(--color-scopic)]/12 text-[var(--color-scopic)]"
                : "text-[var(--color-muted)] hover:bg-[var(--color-panel-2)] hover:text-[var(--color-text)]"
            }`}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
