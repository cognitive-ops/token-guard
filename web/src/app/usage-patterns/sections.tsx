import {
  getLeaderboard,
  getPerDevBars,
  getDonuts,
  getCraftStats,
  getPerDevTables,
  getPromptVolume,
  getRefactorStats,
  type LeaderboardRow,
  type TwoLabelRow,
} from "@/lib/data/usage-patterns";
import { formatUsd, formatCompact, formatInt } from "@/lib/format";
import { KpiCard } from "@/components/kpi-card";
import { Panel, SectionHeading } from "@/components/ui/card";
import { DataGrid, type Column } from "@/components/data-grid";
import type { LabelledValue } from "@/lib/prometheus/reduce";
import {
  LazyDonutChart,
  LazyBarChart,
  LazyTimeSeriesChart,
} from "@/components/charts/lazy";
import { METRIC_DOCS as M } from "@/lib/metric-docs";

// --- Engagement leaderboard ---

export async function LeaderboardSection({ token }: { token: string }) {
  const rows = await getLeaderboard(token);
  const columns: Column<LeaderboardRow>[] = [
    { key: "email", header: "Developer", render: (r) => <span className="font-mono text-xs">{r.email || "(none)"}</span> },
    { key: "prompts", header: "Prompts", align: "right", render: (r) => formatInt(r.prompts) },
    { key: "sessions", header: "Sessions", align: "right", render: (r) => formatInt(r.sessions) },
    { key: "activeHours", header: "Active h", align: "right", render: (r) => r.activeHours.toFixed(1) },
    { key: "commits", header: "Commits", align: "right", render: (r) => formatInt(r.commits) },
    { key: "prs", header: "PRs", align: "right", render: (r) => formatInt(r.prs) },
    { key: "locAdded", header: "LOC+", align: "right", render: (r) => formatCompact(r.locAdded) },
    { key: "tokens", header: "Tokens", align: "right", render: (r) => formatCompact(r.tokens) },
    { key: "cacheEff", header: "Cache eff", align: "right", render: (r) => `${r.cacheEff.toFixed(1)}×` },
  ];
  return (
    <Panel title="Engagement leaderboard" info={M.leaderboard} subtitle="top 30 by prompts, joined per developer">
      <DataGrid rows={rows} columns={columns} getKey={(r) => r.email} />
    </Panel>
  );
}

// --- What it's used for ---

export async function WhatForSection({ token }: { token: string }) {
  const [d, craft] = await Promise.all([getDonuts(token), getCraftStats(token)]);
  return (
    <>
      <SectionHeading title="What it's used for" hint="local classifier · org-wide" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Panel title="Intent mix" info={M.intentMix}><LazyDonutChart data={d.intentMix} ariaLabel="Intent mix" /></Panel>
        <Panel title="Behaviors" info={M.behaviors}><LazyDonutChart data={d.behaviors} ariaLabel="Behaviors" /></Panel>
        <Panel title="Slash commands" info={M.slashCommands}><LazyDonutChart data={d.slashCommands} ariaLabel="Slash commands" /></Panel>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="Well-specified" info={M.wellSpecified} value={`${craft.wellSpecified.pct.toFixed(0)}%`} hint={`${formatInt(craft.wellSpecified.count)} prompts`} accent="var(--color-good)" />
        <KpiCard label="Verifies output" info={M.verifiesOutput} value={`${craft.verifiesOutput.pct.toFixed(0)}%`} hint={`${formatInt(craft.verifiesOutput.count)} prompts`} accent="var(--color-teal)" />
        <KpiCard label="Underspecified" info={M.underspecified} value={`${craft.underspecified.pct.toFixed(0)}%`} hint={`${formatInt(craft.underspecified.count)} prompts`} accent="var(--color-violet)" />
        <KpiCard label="Stuck / looping" info={M.stuckLooping} value={`${craft.stuckLooping.pct.toFixed(0)}%`} hint={`${formatInt(craft.stuckLooping.count)} prompts`} accent="var(--color-bad)" />
      </div>
    </>
  );
}

// --- Workflow style ---

export async function WorkflowStyleSection({ token }: { token: string }) {
  const d = await getDonuts(token);
  return (
    <>
      <SectionHeading title="Workflow style" hint="how work is delegated and run" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Panel title="Tool usage" info={M.toolUsage}><LazyDonutChart data={d.toolUsage} ariaLabel="Tool usage" /></Panel>
        <Panel title="Request source" info={M.requestSource}><LazyDonutChart data={d.requestSource} valuePrefix="$" ariaLabel="Request source" /></Panel>
        <Panel title="Effort level" info={M.effort}><LazyDonutChart data={d.effort} valuePrefix="$" ariaLabel="Effort level" /></Panel>
        <Panel title="Cost by model" info={M.costByModel}><LazyDonutChart data={d.costByModel} valuePrefix="$" ariaLabel="Cost by model" /></Panel>
        <Panel title="Subagent type usage" info={M.subagentType}><LazyDonutChart data={d.subagentType} valuePrefix="$" ariaLabel="Subagent type usage" /></Panel>
        <Panel title="Session start type" info={M.sessionStart}><LazyDonutChart data={d.sessionStart} ariaLabel="Session start type" /></Panel>
      </div>
    </>
  );
}

// --- Per-developer ---

function TwoLabelTable({ rows, header2 }: { rows: TwoLabelRow[]; header2: string }) {
  const columns: Column<TwoLabelRow>[] = [
    { key: "key1", header: "Developer", render: (r) => <span className="font-mono text-xs">{r.key1 || "(none)"}</span> },
    { key: "key2", header: header2, render: (r) => r.key2 || "(none)" },
    { key: "value", header: "Count", align: "right", render: (r) => formatInt(r.value) },
  ];
  return <DataGrid rows={rows} columns={columns} getKey={(r, i) => `${r.key1}-${r.key2}-${i}`} />;
}

export async function PerDeveloperSection({ token }: { token: string }) {
  const [tables, bars] = await Promise.all([getPerDevTables(token), getPerDevBars(token)]);
  return (
    <>
      <SectionHeading title="Per-developer" hint="intent, behaviors, language and engagement by developer" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title="Intent by developer" info={M.intentByDeveloper}><TwoLabelTable rows={tables.intentByDeveloper} header2="Intent" /></Panel>
        <Panel title="Behaviors by developer" info={M.behaviorsByDeveloper}><TwoLabelTable rows={tables.behaviorsByDeveloper} header2="Behavior" /></Panel>
        <Panel title="Prompt language by developer" info={M.promptLangByDeveloper}><TwoLabelTable rows={tables.promptLangByDeveloper} header2="Language" /></Panel>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title="Prompts per developer" info={M.promptsPerDev}><LazyBarChart data={bars.promptsPerDev} maxBars={30} ariaLabel="Prompts per developer" /></Panel>
        <Panel title="Active hours per developer" info={M.activeHoursPerDev}><LazyBarChart data={bars.activeHoursPerDev} valueSuffix=" h" decimals={1} maxBars={30} ariaLabel="Active hours per developer" /></Panel>
        <Panel title="Cache efficiency per developer" info={M.cacheEffPerDev}><LazyBarChart data={bars.cacheEffPerDev} valueSuffix="×" decimals={1} maxBars={30} ariaLabel="Cache efficiency per developer" /></Panel>
      </div>
    </>
  );
}

// --- Prompt volume ---

export async function PromptVolumeSection({ token }: { token: string }) {
  const [v, d] = await Promise.all([getPromptVolume(token), getDonuts(token)]);
  return (
    <>
      <SectionHeading title="Prompt volume" hint="trends and language distribution" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title="Prompts over time" info={M.promptsOverTime} className="lg:col-span-2">
          <LazyTimeSeriesChart points={v.promptsOverTime} kind="bar" stack={false} decimals={0} ariaLabel="Prompts over time" />
        </Panel>
        <Panel title="Prompt language distribution" info={M.promptLanguage}>
          <LazyDonutChart data={d.promptLanguage} ariaLabel="Prompt language distribution" />
        </Panel>
      </div>
    </>
  );
}

// --- Prompt refactoring linter ---

export async function RefactorSection({ token }: { token: string }) {
  const rs = await getRefactorStats(token);
  const overall = rs.scoresByAxis.find((s) => s.label === "overall")?.value ?? 0;
  const columns: Column<LabelledValue>[] = [
    { key: "label", header: "Developer", render: (r) => <span className="font-mono text-xs">{r.label || "(none)"}</span> },
    { key: "value", header: "Rephrase pairs", align: "right", render: (r) => formatInt(r.value) },
  ];
  return (
    <>
      <SectionHeading
        title="Prompt refactoring"
        hint="rule-based lint score · same-session rephrase pairs · estimated savings"
      />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="Rephrase pairs" value={formatInt(rs.pairsTotal)} info={M.refactorPairs} />
        <KpiCard
          label="Est. $ saved"
          value={formatUsd(rs.savedUsdEstimate)}
          hint="estimated from token-count delta, not measured"
          accent="var(--color-good)"
          info={M.refactorSavedUsd}
        />
        <KpiCard
          label="Est. latency saved"
          value={`${rs.savedSecondsEstimate.toFixed(0)}s`}
          hint="estimated, not measured"
          info={M.refactorSavedSeconds}
        />
        <KpiCard label="Avg overall score" value={overall.toFixed(0)} hint="0-100, rule-based" info={M.refactorScore} />
      </div>
      <div className="mt-4">
        <Panel title="Top rephrasers" info={M.refactorTopRephrasers}>
          <DataGrid rows={rs.topRephrasers} columns={columns} getKey={(r) => r.label} />
        </Panel>
      </div>
    </>
  );
}
