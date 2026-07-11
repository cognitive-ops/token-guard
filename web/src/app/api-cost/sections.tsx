import { getApiCost } from "@/lib/data/api-cost";
import { formatUsd, formatCompact, formatInt } from "@/lib/format";
import { KpiCard } from "@/components/kpi-card";
import { Panel, SectionHeading } from "@/components/ui/card";
import { DataGrid, type Column } from "@/components/data-grid";
import { LazyDonutChart, LazyBarChart, LazyTimeSeriesChart } from "@/components/charts/lazy";
import { METRIC_DOCS as M } from "@/lib/metric-docs";
import type { ClientCost } from "@/lib/data/api-cost";

const clientColumns: Column<ClientCost>[] = [
  { key: "client", header: "Workspace", align: "left", render: (r) => r.client },
  { key: "cost", header: "Cost", align: "right", render: (r) => formatUsd(r.cost) },
  { key: "share", header: "Share", align: "right", render: (r) => `${(r.share * 100).toFixed(1)}%` },
];

export async function ApiCostSection({ month }: { month: string }) {
  const d = await getApiCost(month);

  if (!d.configured) {
    return (
      <Panel title="Admin API key not configured">
        <p className="text-sm text-[var(--color-muted)]">
          The API Cost dashboard reads the Anthropic <strong>Admin Cost Report API</strong>. Set{" "}
          <code className="rounded bg-[var(--color-panel-2)] px-1">ADMIN_KEY</code> (an{" "}
          <code className="rounded bg-[var(--color-panel-2)] px-1">sk-ant-admin…</code> key) or{" "}
          <code className="rounded bg-[var(--color-panel-2)] px-1">ADMIN_KEY_PATH</code> (a mounted
          file, like the billing-exporter) on the web service, then reload.
        </p>
      </Panel>
    );
  }

  if (d.error) {
    return (
      <Panel title="Couldn't load API cost">
        <p className="text-sm text-[var(--color-muted)]">
          The Anthropic Admin API request failed: <code className="text-[var(--color-bad)]">{d.error}</code>
        </p>
      </Panel>
    );
  }

  const momUp = (d.momPct ?? 0) >= 0;
  const clientBars = d.clients.map((c) => ({ label: c.client, value: c.cost }));

  return (
    <>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="API Cost" info={M.apiTotalCost} value={formatUsd(d.totalCost)} hint={d.label} />
        <KpiCard
          label="Month / Month"
          info={M.apiMoM}
          value={d.momPct === null ? "—" : `${momUp ? "+" : ""}${d.momPct.toFixed(0)}%`}
          hint={`prev ${formatUsd(d.prevTotalCost)}`}
          accent={d.momPct === null ? "var(--color-muted)" : momUp ? "var(--color-bad)" : "var(--color-good)"}
        />
        <KpiCard label="Daily average" info={M.apiDailyAvg} value={formatUsd(d.dailyAvg)} hint="billed / day so far" accent="var(--color-teal)" />
        <KpiCard label="Projected" info={M.apiProjected} value={formatUsd(d.projected)} hint="month-end run-rate" accent="var(--color-violet)" />
        <KpiCard label="Top workspace" info={M.costByClient} value={d.clients[0]?.client ?? "—"} hint={d.clients[0] ? formatUsd(d.clients[0].cost) : ""} accent="var(--color-violet)" compactValue />
        <KpiCard label="Total Tokens" info={M.tokensByModelMix} value={formatCompact(d.totalTokens)} hint="usage view" accent="var(--color-teal)" />
        <KpiCard label="Blended $ / 1M tok" info={M.apiBlended} value={formatUsd(d.blendedPerMtok)} hint="effective price" accent="#22a7c4" />
        <KpiCard label="Cache-read share" info={M.apiCacheShare} value={`${(d.cacheReadShare * 100).toFixed(0)}%`} hint="of input tokens" accent="#22a7c4" />
      </div>

      <SectionHeading title="Cost by workspace" hint={`${d.label} · billed USD`} info={M.costByClient} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel
          title="Cost per workspace"
          subtitle={`${d.clients.length} workspaces · ${formatUsd(d.totalCost)} total`}
          action={
            <a
              href={`/api-cost/export?month=${d.month}`}
              className="rounded-md border border-[var(--color-scopic)] px-3 py-1 text-xs font-semibold text-[var(--color-scopic)] transition-colors hover:bg-[var(--color-scopic)]/10"
            >
              ↓ CSV
            </a>
          }
        >
          <DataGrid rows={d.clients} columns={clientColumns} getKey={(r) => r.workspaceId} />
        </Panel>
        <Panel title="Cost share by workspace" info={M.costByClient}>
          <LazyBarChart data={clientBars} valuePrefix="$" decimals={0} maxBars={20} ariaLabel="Cost by workspace" />
        </Panel>
      </div>

      <SectionHeading title="Trend & breakdown" hint="daily billed cost; cost & token volume by model/tier" info={M.apiCostByModel} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Cost over the month" info={M.costTrend} className="lg:col-span-2">
          <LazyTimeSeriesChart points={d.dailyTrend} kind="bar" stack={false} unitPrefix="$" decimals={0} ariaLabel="Daily API cost" categoryDay />
        </Panel>
        <Panel title="Cost by model" subtitle="real billed $ — authoritative" info={M.apiCostByModel}>
          <LazyDonutChart data={d.modelCost} valuePrefix="$" ariaLabel="Cost by model" />
        </Panel>
        <Panel title="Tokens by model" subtitle="usage volume" info={M.tokensByModelMix}>
          <LazyDonutChart data={d.modelTokens} ariaLabel="Tokens by model" />
        </Panel>
        <Panel title="Tokens by service tier" info={M.tokensByTier}>
          <LazyDonutChart data={d.tierTokens} ariaLabel="Tokens by service tier" />
        </Panel>
      </div>

      <p className="mt-6 text-xs text-[var(--color-muted)]">
        All cost figures are authoritative billed USD from the Anthropic Cost Report API (amounts are
        reported in cents and converted here). Cost is attributed by workspace and by model; the service-tier
        panel is a token-volume view. {formatInt(d.totalTokens)} tokens this month.
      </p>
    </>
  );
}
