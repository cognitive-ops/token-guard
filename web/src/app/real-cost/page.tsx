import { Suspense } from "react";
import { env } from "@/lib/env";
import { rangeTokenFromParams, resolveRange } from "@/lib/time-range";
import { AppShell, PageHeader } from "@/components/app-shell";
import { TimePicker } from "@/components/time-picker";
import { SectionHeading } from "@/components/ui/card";
import {
  KpiSection, DevelopersSection, CostByModelSection, BreakdownsSection,
  PerUserSection, OverTimeSection, ExporterHealthSection,
} from "./sections";
import { KpiSkeleton, PanelSkeleton, GridSkeleton } from "./skeletons";

export const metadata = { title: "Real Cost · Token Guard Claude Analytics" };
export const dynamic = "force-dynamic";

export default async function RealCostPage({
  searchParams,
}: {
  searchParams: Promise<{ range?: string; from?: string; to?: string }>;
}) {
  const sp = await searchParams;
  const token = rangeTokenFromParams(sp) ?? `${env.DEFAULT_RANGE_DAYS}d`;
  const range = resolveRange(token, Math.floor(Date.now() / 1000));

  return (
    <AppShell controls={<TimePicker activeToken={range.token} activeLabel={range.label} />}>
      <PageHeader title="Real Cost" tagline="what Claude Code actually costs">
        <strong className="text-[var(--color-text)]">Real cost is not the OTEL estimate.</strong>{" "}
        Seat developers&apos; real cost is the flat seat fee plus metered overage; service keys are
        billed at API rates from the Cost Report API. Tap any{" "}
        <span className="font-semibold text-[var(--color-brand)]">ⓘ</span> for details.
      </PageHeader>

      <Suspense fallback={<KpiSkeleton />}>
        <KpiSection token={token} />
      </Suspense>

      <SectionHeading title="Cost attribution" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Suspense fallback={<PanelSkeleton height="h-96" />}><DevelopersSection token={token} /></Suspense>
        <Suspense fallback={<PanelSkeleton height="h-96" />}><CostByModelSection token={token} /></Suspense>
      </div>

      <Suspense fallback={<div className="mt-8"><GridSkeleton /></div>}>
        <BreakdownsSection token={token} />
      </Suspense>

      <SectionHeading title="Over time" hint="estimate" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Suspense fallback={<PanelSkeleton height="h-80 lg:col-span-2" />}><OverTimeSection token={token} /></Suspense>
        <Suspense fallback={<PanelSkeleton height="h-80" />}><ExporterHealthSection token={token} /></Suspense>
      </div>

      <Suspense fallback={<div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-2"><PanelSkeleton height="h-96" /><PanelSkeleton height="h-96" /></div>}>
        <PerUserSection token={token} />
      </Suspense>
    </AppShell>
  );
}
