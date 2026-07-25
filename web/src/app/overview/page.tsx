import { Suspense } from "react";
import { env } from "@/lib/env";
import { rangeTokenFromParams, resolveRange } from "@/lib/time-range";
import { AppShell, PageHeader } from "@/components/app-shell";
import { TimePicker } from "@/components/time-picker";
import { SectionHeading } from "@/components/ui/card";
import {
  KpiSection,
  BreakdownsSection,
  LeaderboardSection,
  CostByUserSection,
  LocByTypeSection,
  PromptLangByDeveloperSection,
  OverTimeSection,
} from "./sections";
import { KpiSkeleton, PanelSkeleton, GridSkeleton } from "./skeletons";

export const metadata = { title: "Overview · Token Guard Claude Analytics" };
export const dynamic = "force-dynamic";

export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<{ range?: string; from?: string; to?: string }>;
}) {
  const sp = await searchParams;
  const token = rangeTokenFromParams(sp) ?? `${env.DEFAULT_RANGE_DAYS}d`;
  const range = resolveRange(token, Math.floor(Date.now() / 1000));

  return (
    <AppShell controls={<TimePicker activeToken={range.token} activeLabel={range.label} />}>
      <PageHeader title="Overview" tagline="adoption, cost & activity at a glance">
        A bird&apos;s-eye view of Claude Code adoption across the org. Cost figures use the{" "}
        <strong className="text-[var(--color-text)]">OTEL estimate</strong> (tokens × list price) — an
        estimate, not the actual bill; see Real Cost for the authoritative figure. Tap any{" "}
        <span className="font-semibold text-[var(--color-brand)]">ⓘ</span> for details.
      </PageHeader>

      <SectionHeading title="Adoption & cost" />
      <Suspense fallback={<KpiSkeleton />}>
        <KpiSection token={token} />
      </Suspense>

      <Suspense fallback={<div className="mt-8"><GridSkeleton count={8} /></div>}>
        <BreakdownsSection token={token} />
      </Suspense>

      <SectionHeading title="Leaderboard & tables" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Suspense fallback={<PanelSkeleton height="h-96 lg:col-span-2" />}>
          <div className="lg:col-span-2"><LeaderboardSection token={token} /></div>
        </Suspense>
        <Suspense fallback={<PanelSkeleton height="h-96" />}><CostByUserSection token={token} /></Suspense>
        <Suspense fallback={<PanelSkeleton height="h-96" />}><LocByTypeSection token={token} /></Suspense>
        <Suspense fallback={<PanelSkeleton height="h-96 lg:col-span-2" />}>
          <div className="lg:col-span-2"><PromptLangByDeveloperSection token={token} /></div>
        </Suspense>
      </div>

      <Suspense fallback={<div className="mt-8"><PanelSkeleton height="h-80" /></div>}>
        <OverTimeSection token={token} />
      </Suspense>
    </AppShell>
  );
}
