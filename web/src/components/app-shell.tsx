import Image from "next/image";
import Link from "next/link";
import { Suspense, type ReactNode } from "react";
import { NavTabs } from "./nav-tabs";
import { ThemeSwitcher } from "./theme-switcher";
import { UserMenu } from "./user-menu";

/**
 * Shared application shell: sticky top bar with the Scopic logo, dashboard
 * tabs, an optional controls slot (time picker / user select), the theme
 * switcher, and the auth user menu. Wraps every dashboard page.
 */
export function AppShell({
  controls,
  children,
}: {
  controls?: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      <header className="sticky top-0 z-30 border-b border-[var(--color-panel-border)] bg-[var(--color-bg)]/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-4 px-4 sm:px-6">
          <Link href="/overview" className="flex shrink-0 items-center gap-2" aria-label="Scopic Claude Analytics">
            <Image
              src="/scopic-icon.png"
              alt="Scopic"
              width={256}
              height={256}
              priority
              unoptimized
              className="h-7 w-7 rounded-md"
            />
            <span className="whitespace-nowrap text-sm font-semibold tracking-tight text-[var(--color-text)]">
              Scopic Claude Analytics
            </span>
          </Link>
          <div className="hidden md:block">
            <NavTabs />
          </div>
          <div className="ml-auto flex items-center gap-2">
            {controls}
            <ThemeSwitcher />
            <Suspense fallback={null}>
              <UserMenu />
            </Suspense>
          </div>
        </div>
        {/* Tabs wrap to a second row on small screens */}
        <div className="border-t border-[var(--color-panel-border)] px-4 py-1.5 md:hidden">
          <NavTabs />
        </div>
      </header>
      <main className="mx-auto max-w-[1600px] px-4 py-6 sm:px-6">{children}</main>
    </>
  );
}

/** A blue-accented page title block with brand aura. */
export function PageHeader({
  title,
  tagline,
  children,
}: {
  title: string;
  tagline?: string;
  children?: ReactNode;
}) {
  return (
    <div className="mb-6">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text)]">{title}</h1>
        {tagline && <span className="text-sm text-[var(--color-muted)]">{tagline}</span>}
      </div>
      {children && <div className="mt-2 text-sm text-[var(--color-muted)]">{children}</div>}
    </div>
  );
}
