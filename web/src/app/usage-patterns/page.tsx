import { Suspense } from "react";
import { env } from "@/lib/env";
import { rangeTokenFromParams, resolveRange } from "@/lib/time-range";
import { AppShell, PageHeader } from "@/components/app-shell";
import { TimePicker } from "@/components/time-picker";
import {
  LeaderboardSection,
  WhatForSection,
  WorkflowStyleSection,
  PerDeveloperSection,
  PromptVolumeSection,
} from "./sections";
import { PanelSkeleton, GridSkeleton } from "./skeletons";

export const metadata = { title: "Usage Patterns · Scopic Claude Analytics" };
export const dynamic = "force-dynamic";

export default async function UsagePatternsPage({
  searchParams,
}: {
  searchParams: Promise<{ range?: string; from?: string; to?: string }>;
}) {
  const sp = await searchParams;
  const token = rangeTokenFromParams(sp) ?? `${env.DEFAULT_RANGE_DAYS}d`;
  const range = resolveRange(token, Math.floor(Date.now() / 1000));

  return (
    <AppShell controls={<TimePicker activeToken={range.token} activeLabel={range.label} />}>
      <PageHeader title="Usage Patterns" tagline="how developers actually use Claude Code">
        Engagement, prompt craft, and workflow style across the team — what it&apos;s used for,
        how work gets delegated, and who&apos;s most active. Tap any{" "}
        <span className="font-semibold text-[var(--color-scopic)]">ⓘ</span> for details.
      </PageHeader>

      <Suspense fallback={<PanelSkeleton height="h-96" />}>
        <LeaderboardSection token={token} />
      </Suspense>

      <Suspense fallback={<div className="mt-8"><GridSkeleton count={3} /></div>}>
        <WhatForSection token={token} />
      </Suspense>

      <Suspense fallback={<div className="mt-8"><GridSkeleton count={6} /></div>}>
        <WorkflowStyleSection token={token} />
      </Suspense>

      <Suspense fallback={<div className="mt-8"><GridSkeleton count={6} /></div>}>
        <PerDeveloperSection token={token} />
      </Suspense>

      <Suspense fallback={<div className="mt-8"><PanelSkeleton height="h-80" /></div>}>
        <PromptVolumeSection token={token} />
      </Suspense>
    </AppShell>
  );
}
