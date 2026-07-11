import {
  getKpis,
  getDevelopers,
  getBreakdowns,
  getCostOverTime,
  getExporterHealth,
} from "@/lib/data/real-cost";
import { formatUsd, formatCompact, formatInt, formatAgo } from "@/lib/format";
import { KpiCard, MiniStat } from "@/components/kpi-card";
import { Panel, SectionHeading } from "@/components/ui/card";
import { DeveloperCostTable, UsageTable } from "@/components/data-table";
import {
  LazyDonutChart,
  LazyTimeSeriesChart,
} from "@/components/charts/lazy";
import { METRIC_DOCS as M } from "@/lib/metric-docs";

export async function KpiSection({ token }: { token: string }) {
  const k = await getKpis(token);
  const seats = Object.fromEntries(k.seatsByType.map((s) => [s.label, s.value]));
  return (
    <>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        <KpiCard label="Org Real Cost" info={M.orgRealCost} value={k.orgRealCost === null ? "—" : formatUsd(k.orgRealCost)} hint="seat fees + overage" />
        <KpiCard label="Service Billed" info={M.serviceBilled} value={k.serviceBilled === null ? "—" : formatUsd(k.serviceBilled)} hint="Cost Report API" />
        <KpiCard label="OTEL Estimate" info={M.otelEstimate} value={formatUsd(k.otelEstimate)} hint="not the bill" accent="var(--color-violet)" />
        <KpiCard label="Seats" info={M.seats} value={`${formatInt(seats.premium ?? 0)} / ${formatInt(seats.standard ?? 0)}`} hint="premium / standard" />
        <KpiCard label="Active Users" info={M.activeUsers} value={formatInt(k.activeUsers)} accent="var(--color-teal)" />
        <KpiCard label="Total Prompts" info={M.totalPrompts} value={formatInt(k.totalPrompts)} hint="from Loki" accent="#22a7c4" />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <MiniStat label="Tokens" info={M.totalTokens} value={formatCompact(k.totalTokens)} />
        <MiniStat label="Sessions" info={M.sessions} value={formatInt(k.sessions)} raw={k.sessions} hideWhenZero />
        <MiniStat label="Lines of Code" info={M.linesOfCode} value={formatCompact(k.linesOfCode)} />
        <MiniStat label="Commits" info={M.commits} value={formatInt(k.commits)} raw={k.commits} hideWhenZero />
        <MiniStat label="Pull Requests" info={M.pullRequests} value={formatInt(k.pullRequests)} raw={k.pullRequests} hideWhenZero />
        <MiniStat label="Cost / 1M Tokens" info={M.costPerMTokens} value={formatUsd(k.costPerMTokens)} />
      </div>
    </>
  );
}

export async function DevelopersSection({ token }: { token: string }) {
  const { rows, totals } = await getDevelopers(token);
  return (
    <Panel title="Real Cost per Developer" info={M.orgRealCost} subtitle="seat fee + extra usage, joined server-side">
      <DeveloperCostTable rows={rows} />
      <p className="mt-3 text-xs text-[var(--color-muted)]">
        {formatInt(rows.length)} developers · {formatUsd(totals.totalReal)} total · {totals.developersWithOverage} with overage
      </p>
    </Panel>
  );
}

export async function CostByModelSection({ token }: { token: string }) {
  const b = await getBreakdowns(token);
  return (
    <Panel title="OTEL Cost by Model" info={M.costByModel} subtitle="estimate">
      <LazyDonutChart data={b.costByModel} valuePrefix="$" ariaLabel="OTEL cost by model" />
    </Panel>
  );
}

export async function BreakdownsSection({ token }: { token: string }) {
  const b = await getBreakdowns(token);
  return (
    <>
      <SectionHeading title="Breakdowns" hint="raw OTEL usage" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Panel title="Tokens by Type" info={M.tokensByType}><LazyDonutChart data={b.tokensByType} ariaLabel="Tokens by type" /></Panel>
        <Panel title="Cost by Repository" info={M.costByRepo}><LazyDonutChart data={b.costByRepo} valuePrefix="$" ariaLabel="Cost by repository" /></Panel>
        <Panel title="Cost by Terminal / IDE" info={M.costByTerminal}><LazyDonutChart data={b.costByTerminal} valuePrefix="$" ariaLabel="Cost by terminal" /></Panel>
        <Panel title="Prompt Language" info={M.promptLanguage}><LazyDonutChart data={b.promptLanguage} ariaLabel="Prompt language" /></Panel>
      </div>
    </>
  );
}

export async function PerUserSection({ token }: { token: string }) {
  const b = await getBreakdowns(token);
  return (
    <>
      <SectionHeading title="Per-developer usage" hint="pairs with Real Cost per Developer above" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="OTEL Cost by User" info={M.costByModel} subtitle="estimate"><UsageTable rows={b.costByUser} unit="OTEL $" format={formatUsd} /></Panel>
        <Panel title="Tokens by User" info={M.totalTokens}><UsageTable rows={b.tokensByUser} unit="Tokens" format={formatCompact} /></Panel>
      </div>
    </>
  );
}

export async function OverTimeSection({ token }: { token: string }) {
  const points = await getCostOverTime(token);
  return (
    <Panel title="OTEL Cost Over Time" info={M.costOverTime} subtitle="by model, stacked" className="lg:col-span-2">
      <LazyTimeSeriesChart points={points} unitPrefix="$" decimals={2} ariaLabel="OTEL cost over time by model" />
    </Panel>
  );
}

export async function ExporterHealthSection({ token }: { token: string }) {
  const e = await getExporterHealth(token);
  const now = Math.floor(Date.now() / 1000);
  return (
    <Panel title="Exporter Health" info={M.exporterHealth}>
      <dl className="space-y-4 text-sm">
        <div>
          <dt className="text-xs uppercase tracking-wide text-[var(--color-muted)]">Last successful poll</dt>
          <dd className="text-lg font-semibold text-[var(--color-scopic)]">{e.lastSuccess === null ? "—" : formatAgo(e.lastSuccess, now)}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-[var(--color-muted)]">Errors</dt>
          <dd className={`text-lg font-semibold ${(e.errors ?? 0) > 0 ? "text-[var(--color-bad)]" : "text-[var(--color-good)]"}`}>{e.errors === null ? "—" : formatInt(e.errors)}</dd>
        </div>
      </dl>
    </Panel>
  );
}
