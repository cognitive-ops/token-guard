import { Suspense } from "react";
import { env } from "@/lib/env";
import { rangeTokenFromParams, resolveRange } from "@/lib/time-range";
import { AppShell, PageHeader } from "@/components/app-shell";
import { TimePicker } from "@/components/time-picker";
import { UserSelect } from "@/components/user-select";
import { Panel } from "@/components/ui/card";
import { getUserList } from "@/lib/data/users";
import {
  SummarySection,
  BreakdownsSection,
  OverTimeSection,
  ActivitySection,
  PromptPatternsSection,
} from "./sections";
import { KpiSkeleton, GridSkeleton, PanelSkeleton } from "./skeletons";

export const metadata = { title: "Developer · Token Guard Claude Analytics" };
export const dynamic = "force-dynamic";

export default async function DeveloperPage({
  searchParams,
}: {
  searchParams: Promise<{ range?: string; from?: string; to?: string; user?: string }>;
}) {
  const sp = await searchParams;
  const token = rangeTokenFromParams(sp) ?? `${env.DEFAULT_RANGE_DAYS}d`;
  const range = resolveRange(token, Math.floor(Date.now() / 1000));
  const users = await getUserList();

  if (users.length === 0) {
    return (
      <AppShell controls={<TimePicker activeToken={range.token} activeLabel={range.label} />}>
        <PageHeader title="Developer" tagline="per-developer drilldown" />
        <Panel title="No developers found">
          <p className="text-sm text-[var(--color-muted)]">
            No developer activity in the selected window.
          </p>
        </Panel>
      </AppShell>
    );
  }

  const user: string = sp.user && users.includes(sp.user) ? sp.user : users[0]!;
  const key = user + token;

  return (
    <AppShell
      controls={
        <>
          <UserSelect users={users} active={user} />
          <TimePicker activeToken={range.token} activeLabel={range.label} />
        </>
      }
    >
      <PageHeader title="Developer" tagline={user}>
        A single developer&apos;s Claude Code usage. Cost figures are the{" "}
        <strong className="text-[var(--color-text)]">OTEL estimate</strong>, not the bill. Tap any{" "}
        <span className="font-semibold text-[var(--color-brand)]">ⓘ</span> for details.
      </PageHeader>

      <Suspense key={`summary-${key}`} fallback={<KpiSkeleton />}>
        <SummarySection user={user} token={token} />
      </Suspense>

      <Suspense key={`breakdowns-${key}`} fallback={<div className="mt-8"><GridSkeleton count={5} /></div>}>
        <BreakdownsSection user={user} token={token} />
      </Suspense>

      <Suspense
        key={`overtime-${key}`}
        fallback={
          <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <PanelSkeleton height="h-80" />
            <PanelSkeleton height="h-80" />
            <PanelSkeleton height="h-80" />
            <PanelSkeleton height="h-80" />
          </div>
        }
      >
        <OverTimeSection user={user} token={token} />
      </Suspense>

      <Suspense
        key={`activity-${key}`}
        fallback={
          <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <PanelSkeleton height="h-64 lg:col-span-2" />
            <PanelSkeleton height="h-80" />
            <PanelSkeleton height="h-80" />
          </div>
        }
      >
        <ActivitySection user={user} token={token} />
      </Suspense>

      <Suspense key={`prompts-${key}`} fallback={<div className="mt-8"><GridSkeleton count={3} /></div>}>
        <PromptPatternsSection user={user} token={token} />
      </Suspense>
    </AppShell>
  );
}
