import {
  getKpis,
  getBreakdowns,
  getTables,
  getPromptLangByDeveloper,
  getLeaderboard,
  getCostOverTime,
} from "@/lib/data/overview";
import { formatUsd, formatCompact, formatInt } from "@/lib/format";
import { KpiCard, MiniStat } from "@/components/kpi-card";
import { Panel, SectionHeading } from "@/components/ui/card";
import { UsageTable } from "@/components/data-table";
import { DataGrid, type Column } from "@/components/data-grid";
import { LazyDonutChart, LazyTimeSeriesChart } from "@/components/charts/lazy";
import { METRIC_DOCS as M } from "@/lib/metric-docs";
import type { LeaderboardRow, PromptLangRow } from "@/lib/data/overview";

export async function KpiSection({ token }: { token: string }) {
  const k = await getKpis(token);
  return (
    <>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
        <KpiCard label="Total Cost" info={M.otelEstimate} value={formatUsd(k.totalCost)} hint="OTEL estimate — not the bill" accent="var(--color-violet)" />
        <KpiCard label="Active Users" info={M.activeUsers} value={formatInt(k.activeUsers)} accent="var(--color-teal)" />
        <KpiCard label="Total Tokens" info={M.totalTokens} value={formatCompact(k.totalTokens)} />
        <KpiCard label="Lines of Code" info={M.linesOfCode} value={formatCompact(k.linesOfCode)} />
        <KpiCard label="Total Prompts" info={M.totalPrompts} value={formatInt(k.totalPrompts)} hint="from Loki" accent="#22a7c4" />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MiniStat label="Cost / 1000 LOC" info={M.costPer1kLoc} value={formatUsd(k.costPer1kLoc)} />
        <MiniStat label="Avg Cost / User" info={M.avgCostPerUser} value={formatUsd(k.avgCostPerUser)} />
        <MiniStat label="Cost / Prompt" info={M.costPerPrompt} value={formatUsd(k.costPerPrompt)} />
        <MiniStat label="Cost / Active Hour" info={M.costPerActiveHour} value={formatUsd(k.costPerActiveHour)} />
      </div>
    </>
  );
}

export async function BreakdownsSection({ token }: { token: string }) {
  const b = await getBreakdowns(token);
  return (
    <>
      <SectionHeading title="Breakdowns" hint="OTEL usage; cost is an estimate" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <Panel title="Cost by Model" info={M.costByModel}><LazyDonutChart data={b.costByModel} valuePrefix="$" ariaLabel="Cost by model" /></Panel>
        <Panel title="Token Usage by Type" info={M.tokensByType}><LazyDonutChart data={b.tokensByType} ariaLabel="Token usage by type" /></Panel>
        <Panel title="Cost by Repository" info={M.costByRepo}><LazyDonutChart data={b.costByRepo} valuePrefix="$" ariaLabel="Cost by repository" /></Panel>
        <Panel title="Tokens by Repository" info={M.tokensByRepo}><LazyDonutChart data={b.tokensByRepo} ariaLabel="Tokens by repository" /></Panel>
        <Panel title="Cost by Git Host" info={M.costByGitHost}><LazyDonutChart data={b.costByGitHost} valuePrefix="$" ariaLabel="Cost by git host" /></Panel>
        <Panel title="Cost by Terminal / IDE" info={M.costByTerminal}><LazyDonutChart data={b.costByTerminal} valuePrefix="$" ariaLabel="Cost by terminal" /></Panel>
        <Panel title="Tool Usage" info={M.toolUsage}><LazyDonutChart data={b.toolUsage} ariaLabel="Tool usage" /></Panel>
        <Panel title="Request Source" info={M.requestSource}><LazyDonutChart data={b.requestSource} valuePrefix="$" ariaLabel="Request source" /></Panel>
        <Panel title="Effort Level" info={M.effort}><LazyDonutChart data={b.effort} valuePrefix="$" ariaLabel="Effort level" /></Panel>
        <Panel title="Intent Mix" info={M.intentMix}><LazyDonutChart data={b.intentMix} ariaLabel="Intent mix" /></Panel>
        <Panel title="Prompt Language" info={M.promptLanguage}><LazyDonutChart data={b.promptLanguage} ariaLabel="Prompt language" /></Panel>
      </div>
    </>
  );
}

export async function LeaderboardSection({ token }: { token: string }) {
  const rows = await getLeaderboard(token);
  const columns: Column<LeaderboardRow>[] = [
    { key: "user", header: "Developer", align: "left", render: (r) => <span className="font-mono text-xs">{r.user || "(none)"}</span> },
    { key: "prompts", header: "Prompts", align: "right", render: (r) => formatInt(r.prompts) },
    { key: "sessions", header: "Sessions", align: "right", render: (r) => formatInt(r.sessions) },
    { key: "commits", header: "Commits", align: "right", render: (r) => formatInt(r.commits) },
    { key: "cacheEff", header: "Cache eff (×)", align: "right", render: (r) => r.cacheEff.toFixed(1) },
  ];
  return (
    <Panel title="Developer Leaderboard" info={M.leaderboard} subtitle="top 30 by prompts">
      <DataGrid rows={rows} columns={columns} getKey={(r) => r.user} />
    </Panel>
  );
}

export async function CostByUserSection({ token }: { token: string }) {
  const t = await getTables(token);
  return (
    <Panel title="Cost by User" info={M.avgCostPerUser} subtitle="OTEL estimate">
      <UsageTable rows={t.costByUser} unit="OTEL $" format={formatUsd} />
    </Panel>
  );
}

export async function LocByTypeSection({ token }: { token: string }) {
  const t = await getTables(token);
  return (
    <Panel title="Lines of Code by Type" info={M.locByType}>
      <UsageTable rows={t.locByType} unit="Lines" format={formatCompact} />
    </Panel>
  );
}

export async function PromptLangByDeveloperSection({ token }: { token: string }) {
  const rows = await getPromptLangByDeveloper(token);
  const columns: Column<PromptLangRow>[] = [
    { key: "user", header: "Developer", align: "left", render: (r) => <span className="font-mono text-xs">{r.user || "(none)"}</span> },
    { key: "language", header: "Language", align: "left", render: (r) => r.language },
    { key: "count", header: "Count", align: "right", render: (r) => formatInt(r.count) },
  ];
  return (
    <Panel title="Prompt Language by Developer" info={M.promptLangByDeveloper}>
      <DataGrid rows={rows} columns={columns} getKey={(r, i) => `${r.user}-${r.language}-${i}`} />
    </Panel>
  );
}

export async function OverTimeSection({ token }: { token: string }) {
  const points = await getCostOverTime(token);
  return (
    <>
      <SectionHeading title="Over time" hint="estimate" />
      <Panel title="Cost Over Time by User" info={M.costOverTime} subtitle="by user, stacked">
        <LazyTimeSeriesChart points={points} unitPrefix="$" decimals={2} stack ariaLabel="Cost over time by user" />
      </Panel>
    </>
  );
}
