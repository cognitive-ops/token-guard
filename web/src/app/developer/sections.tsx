import {
  getDevKpis,
  getDevBreakdowns,
  getDevPromptPatterns,
  getDevOverTime,
  getDevActivity,
} from "@/lib/data/developer";
import { formatUsd, formatCompact, formatInt } from "@/lib/format";
import { KpiCard, MiniStat } from "@/components/kpi-card";
import { Panel, SectionHeading } from "@/components/ui/card";
import {
  LazyDonutChart,
  LazyTimeSeriesChart,
  LazyBarChart,
  LazyActivityHeatmap,
} from "@/components/charts/lazy";
import { METRIC_DOCS as M } from "@/lib/metric-docs";

const pct = (n: number) => `${(n * 100).toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
const ratio = (n: number) => `${n.toLocaleString("en-US", { maximumFractionDigits: 1 })}×`;

export async function SummarySection({ user, token }: { user: string; token: string }) {
  const k = await getDevKpis(user, token);
  return (
    <>
      <SectionHeading title={`${user} — summary`} />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        <KpiCard label="Total Cost" info={M.otelEstimate} value={formatUsd(k.totalCost)} hint="estimate" accent="var(--color-violet)" />
        <KpiCard label="Total Tokens" info={M.totalTokens} value={formatCompact(k.totalTokens)} />
        <KpiCard label="Sessions" info={M.sessions} value={formatInt(k.sessions)} raw={k.sessions} hideWhenZero accent="var(--color-teal)" />
        <KpiCard label="Prompts" info={M.totalPrompts} value={formatInt(k.prompts)} hint="from Loki" accent="#22a7c4" />
        <KpiCard label="Commits" info={M.commits} value={formatInt(k.commits)} raw={k.commits} hideWhenZero />
        <KpiCard label="Pull Requests" info={M.pullRequests} value={formatInt(k.pullRequests)} raw={k.pullRequests} hideWhenZero />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <MiniStat label="% Code that is New" info={M.pctNewCode} value={pct(k.pctNewCode)} />
        <MiniStat label="Cost per Commit" info={M.costPerCommit} value={formatUsd(k.costPerCommit)} />
        <MiniStat label="Cost per Prompt" info={M.costPerPrompt} value={formatUsd(k.costPerPrompt)} />
        <MiniStat label="Cache Efficiency" info={M.cacheEfficiency} value={ratio(k.cacheEfficiency)} />
        <MiniStat label="Commits per PR" info={M.commitsPerPr} value={ratio(k.commitsPerPr)} />
        <MiniStat label="LOC Added" info={M.linesOfCode} value={formatCompact(k.locAdded)} />
      </div>
    </>
  );
}

export async function BreakdownsSection({ user, token }: { user: string; token: string }) {
  const b = await getDevBreakdowns(user, token);
  return (
    <>
      <SectionHeading title="Breakdowns" hint="raw OTEL usage" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <Panel title="Token Usage by Type" info={M.tokensByType}><LazyDonutChart data={b.tokensByType} ariaLabel="Token usage by type" /></Panel>
        <Panel title="Cost by Model" info={M.costByModel}><LazyDonutChart data={b.costByModel} valuePrefix="$" ariaLabel="Cost by model" /></Panel>
        <Panel title="Cost by Repository" info={M.costByRepo}><LazyDonutChart data={b.costByRepo} valuePrefix="$" ariaLabel="Cost by repository" /></Panel>
        <Panel title="Cost by Terminal / IDE" info={M.costByTerminal}><LazyDonutChart data={b.costByTerminal} valuePrefix="$" ariaLabel="Cost by terminal" /></Panel>
        <Panel title="Prompt Language" info={M.promptLanguage}><LazyDonutChart data={b.promptLanguage} ariaLabel="Prompt language" /></Panel>
      </div>
    </>
  );
}

export async function OverTimeSection({ user, token }: { user: string; token: string }) {
  const t = await getDevOverTime(user, token);
  return (
    <>
      <SectionHeading title="Over time" hint="estimate" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Cost over time" info={M.costOverTime} subtitle="by model, stacked">
          <LazyTimeSeriesChart points={t.costOverTime} unitPrefix="$" decimals={2} ariaLabel="Cost over time by model" />
        </Panel>
        <Panel title="Prompts over time" info={M.promptsOverTime}>
          <LazyTimeSeriesChart points={t.promptsOverTime} kind="bar" stack={false} decimals={0} ariaLabel="Prompts over time" />
        </Panel>
        <Panel title="LOC over time" info={M.locOverTime} subtitle="by type">
          <LazyTimeSeriesChart points={t.locOverTime} decimals={0} ariaLabel="Lines of code over time by type" />
        </Panel>
        <Panel title="Repositories worked in" info={M.projectTimeline} subtitle="tokens by repository, stacked">
          <LazyTimeSeriesChart points={t.projectTimeline} decimals={0} stack={true} ariaLabel="Repositories worked in over time" />
        </Panel>
      </div>
    </>
  );
}

export async function ActivitySection({ user, token }: { user: string; token: string }) {
  const a = await getDevActivity(user, token);
  return (
    <>
      <SectionHeading title="Activity" hint="UTC" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Activity heatmap" info={M.activityHeatmap} subtitle="tokens by hour-of-day × weekday, summed over the period (UTC) — cool→warm = low→high" className="lg:col-span-2">
          <LazyActivityHeatmap cells={a.cells} ariaLabel="Activity heatmap by hour and weekday" />
        </Panel>
        <Panel title="Activity by hour of day" info={M.activityByHour}>
          <LazyBarChart data={a.byHour} valueSuffix="" decimals={0} maxBars={24} ariaLabel="Activity by hour of day" />
        </Panel>
        <Panel title="Activity by weekday" info={M.activityByWeekday}>
          <LazyBarChart data={a.byWeekday} valueSuffix="" decimals={0} maxBars={7} ariaLabel="Activity by weekday" />
        </Panel>
      </div>
    </>
  );
}

export async function PromptPatternsSection({ user, token }: { user: string; token: string }) {
  const p = await getDevPromptPatterns(user, token);
  return (
    <>
      <SectionHeading title="Prompt patterns" hint="local classifier" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Panel title="Intent mix" info={M.intentMix}><LazyDonutChart data={p.intentMix} ariaLabel="Intent mix" /></Panel>
        <Panel title="Behaviors" info={M.behaviors}><LazyDonutChart data={p.behaviors} ariaLabel="Behaviors" /></Panel>
        <Panel title="Slash commands" info={M.slashCommands}><LazyDonutChart data={p.slashCommands} ariaLabel="Slash commands" /></Panel>
      </div>
    </>
  );
}
