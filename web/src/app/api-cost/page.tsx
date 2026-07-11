import { Suspense } from "react";
import { AppShell, PageHeader } from "@/components/app-shell";
import { MonthPicker } from "@/components/month-picker";
import { currentMonth, recentMonths } from "@/lib/data/api-cost";
import { ApiCostSection } from "./sections";
import { KpiSkeleton } from "./skeletons";

export const metadata = { title: "API Cost · Scopic Claude Analytics" };
export const dynamic = "force-dynamic";

export default async function ApiCostPage({
  searchParams,
}: {
  searchParams: Promise<{ month?: string }>;
}) {
  const sp = await searchParams;
  const month = typeof sp.month === "string" && /^\d{4}-\d{2}$/.test(sp.month) ? sp.month : currentMonth();
  const months = recentMonths(12);

  return (
    <AppShell controls={<MonthPicker months={months} active={month} />}>
      <PageHeader title="API Cost" tagline="billed Anthropic spend by workspace">
        Authoritative billed USD from the Anthropic <strong className="text-[var(--color-text)]">Cost Report API</strong>,
        per workspace (one workspace per product/client). Pick a month and{" "}
        <span className="font-semibold text-[var(--color-scopic)]">↓ CSV</span> for a finance report.
      </PageHeader>
      <Suspense key={month} fallback={<KpiSkeleton />}>
        <ApiCostSection month={month} />
      </Suspense>
    </AppShell>
  );
}
