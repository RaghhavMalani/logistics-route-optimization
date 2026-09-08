import { Link, createFileRoute } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";

import { BarRanking, SeriesChart } from "@/components/kit/charts";
import {
  Page,
  PageBody,
  PageHeader,
  Panel,
  SegmentedControl,
  StatStrip,
} from "@/components/kit/layout";
import {
  KeyValue,
  MiniBar,
  Num,
  Pill,
  ProvenanceTag,
  formatUtc,
  statusTone,
} from "@/components/kit/primitives";
import { EmptyState, ScreenFallback } from "@/components/kit/states";
import { DataTable, type Column } from "@/components/kit/table";
import { cn } from "@/lib/utils";
import { useBenchmark, usePipeline, useProvenance } from "@/services/hooks";
import type { BenchmarkRow, PipelineNode } from "@/types/portwatch";

export const Route = createFileRoute("/admin/model")({ component: ModelIntelligence });

type Drilldown = "horizon" | "port" | "regime";

/* ------------------------------------------------------------ flow stage -- */

interface Stage {
  key: string;
  label: string;
  caption: string;
  nodes: PipelineNode[];
  /** Inputs has no pipeline nodes; it counts the feed roster instead. */
  count?: number;
  available?: number;
}

function StageColumn({
  stage,
  active,
  onSelect,
  isLast,
}: {
  stage: Stage;
  active: boolean;
  onSelect: () => void;
  isLast: boolean;
}) {
  const total = stage.count ?? stage.nodes.length;
  const available = stage.available ?? stage.nodes.filter((node) => node.available).length;
  const meanConfidence = stage.nodes.length
    ? stage.nodes.reduce((sum, node) => sum + (node.confidence ?? 0), 0) / stage.nodes.length
    : null;

  return (
    <>
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "flex min-w-0 flex-1 flex-col gap-1.5 rounded-[3px] border px-3 py-2.5 text-left transition-colors",
          active
            ? "border-[var(--info)] bg-[var(--info-dim)]"
            : "border-[var(--line)] bg-[var(--panel-2)] hover:border-[var(--line-strong)]",
        )}
      >
        <span className="eyebrow truncate" style={active ? { color: "var(--info)" } : undefined}>
          {stage.label}
        </span>
        <span className="text-[12px] leading-snug text-[var(--text-2)]">{stage.caption}</span>
        <span className="mt-auto flex items-baseline gap-2 pt-1">
          <span className="metric-lg text-[var(--text)]">{total}</span>
          <span className="text-[10.5px] text-[var(--text-3)]">
            {total === 0
              ? "none registered"
              : available === total
                ? "all available"
                : `${available} of ${total} available`}
          </span>
        </span>
        {meanConfidence != null ? (
          <span className="w-full">
            <MiniBar value={meanConfidence} tone={meanConfidence >= 0.7 ? "ok" : "warn"} />
          </span>
        ) : null}
      </button>
      {isLast ? null : (
        <ChevronRight size={14} className="shrink-0 text-[var(--text-3)]" aria-hidden />
      )}
    </>
  );
}

/* ------------------------------------------------------------------ page -- */

function ModelIntelligence() {
  const pipeline = usePipeline();
  const benchmark = useBenchmark();
  const provenance = useProvenance();
  const [drilldown, setDrilldown] = useState<Drilldown>("horizon");
  const [stageKey, setStageKey] = useState<string>("experts");

  const feeds = Object.values(provenance.data?.sources ?? {});

  const stages = useMemo<Stage[]>(() => {
    const nodes = pipeline.data ?? [];
    const experts = nodes.filter((node) => node.kind !== "model" && node.kind !== "decision");
    const models = nodes.filter((node) => node.kind === "model");
    const decisions = nodes.filter((node) => node.kind === "decision");
    const regime = models.filter((node) => /regime|hsmm/i.test(node.key + node.name));
    const forecast = models.filter((node) => !/regime|hsmm/i.test(node.key + node.name));

    return [
      {
        key: "inputs",
        label: "Inputs",
        caption: "Live and cached feeds entering the panel",
        nodes: [],
        count: feeds.length,
        available: feeds.filter((source) => source.status !== "UNAVAILABLE").length,
      },
      {
        key: "experts",
        label: "Specialists",
        caption: "Bounded features per port and day",
        nodes: experts,
      },
      {
        key: "regime",
        label: "Regime",
        caption: "HSMM operating state and expected dwell",
        nodes: regime,
      },
      {
        key: "forecast",
        label: "Forecast",
        caption: "Quantile members over the horizon",
        nodes: forecast,
      },
      {
        key: "decision",
        label: "Decision",
        caption: "Bounded action with drivers and fallback",
        nodes: decisions,
      },
    ];
  }, [feeds, pipeline.data]);

  if (pipeline.isLoading || pipeline.isError) {
    return (
      <ScreenFallback
        title="Model Intelligence"
        context={<span>What the system runs, and what it measured itself at</span>}
        isLoading={pipeline.isLoading}
        error={pipeline.error}
        retry={() => void pipeline.refetch()}
        label="Loading model artefacts"
      />
    );
  }

  const bench = benchmark.data;
  const summary = bench?.summary;
  const weights = bench?.ensembleWeights;
  const sources = provenance.data?.sources ?? {};
  const sourceCount = Object.keys(sources).length;

  const activeStage = stages.find((stage) => stage.key === stageKey) ?? stages[1];
  const drilldownRows: BenchmarkRow[] =
    (drilldown === "horizon"
      ? bench?.byHorizon
      : drilldown === "port"
        ? bench?.byPort
        : bench?.byRegime) ?? [];
  const drilldownKey =
    drilldown === "horizon" ? "horizon_day" : drilldown === "port" ? "port_id" : "regime";

  const modelColumns: Array<Column<BenchmarkRow>> = [
    {
      key: "model",
      header: "Model",
      render: (row) => (
        <span className="flex items-center gap-2">
          <span
            className={
              row.model === summary?.bestModel
                ? "font-medium text-[var(--text)]"
                : "text-[var(--text-2)]"
            }
          >
            {row.model}
          </span>
          {row.model === summary?.bestModel ? <Pill tone="ok">leader</Pill> : null}
        </span>
      ),
      sort: (row) => row.model,
    },
    { key: "n", header: "n", align: "right", width: 82, render: (row) => <Num value={row.n} digits={0} />, sort: (row) => row.n },
    { key: "mae", header: "MAE", align: "right", width: 92, render: (row) => <Num value={row.mae} digits={3} />, sort: (row) => row.mae },
    { key: "rmse", header: "RMSE", align: "right", width: 92, render: (row) => <Num value={row.rmse} digits={3} />, sort: (row) => row.rmse },
    { key: "mape", header: "MAPE %", align: "right", width: 96, render: (row) => <Num value={row.mape_pct} digits={2} />, sort: (row) => row.mape_pct },
    { key: "p10", header: "Pinball q10", align: "right", width: 110, render: (row) => <Num value={row.pinball_q10} digits={3} />, sort: (row) => row.pinball_q10 },
    { key: "p50", header: "Pinball q50", align: "right", width: 110, render: (row) => <Num value={row.pinball_q50} digits={3} />, sort: (row) => row.pinball_q50 },
    { key: "p90", header: "Pinball q90", align: "right", width: 110, render: (row) => <Num value={row.pinball_q90} digits={3} />, sort: (row) => row.pinball_q90 },
    {
      key: "cov",
      header: "80% coverage",
      align: "right",
      width: 124,
      hint: "Empirical share of outcomes inside the nominal 80% band",
      render: (row) => (
        <Num
          value={row.coverage_80pct}
          digits={3}
          tone={
            row.coverage_80pct == null
              ? undefined
              : Math.abs(row.coverage_80pct - 0.8) <= 0.05
                ? "ok"
                : "crit"
          }
        />
      ),
      sort: (row) => row.coverage_80pct,
    },
    { key: "width", header: "Band width", align: "right", width: 108, render: (row) => <Num value={row.interval_width} digits={2} />, sort: (row) => row.interval_width },
    { key: "cal", header: "Calib. error", align: "right", width: 110, render: (row) => <Num value={row.calibration_error} digits={3} />, sort: (row) => row.calibration_error },
  ];

  return (
    <Page>
      <PageHeader
        title="Model Intelligence"
        context={<span>What the system runs, and what it measured itself at</span>}
        meta={
          <>
            <span className="num">{bench?.version ?? "no benchmark"}</span>
            <span className="num">generated {formatUtc(bench?.generatedAt ?? null)}</span>
          </>
        }
      />

      <StatStrip
        size="sm"
        items={[
          {
            label: "Leading model",
            value: summary?.bestModel ?? "n/a",
            tone: "ok",
            note: summary ? `${summary.folds} expanding walk-forward folds` : "benchmark not run",
          },
          {
            label: "MAE",
            value: summary?.bestMae?.toFixed(3) ?? "n/a",
            note: `naive ${summary?.naiveMae?.toFixed(3) ?? "n/a"}`,
          },
          {
            label: "Skill vs naive",
            value:
              summary?.skillVsNaive == null
                ? "n/a"
                : `${(summary.skillVsNaive * 100).toFixed(1)}%`,
            tone: (summary?.skillVsNaive ?? 0) > 0 ? "ok" : "warn",
            note: "lower MAE than persistence is better",
          },
          {
            label: "80% coverage",
            value: summary?.bestCoverage80?.toFixed(3) ?? "n/a",
            tone:
              summary?.bestCoverage80 == null
                ? "neutral"
                : Math.abs(summary.bestCoverage80 - 0.8) <= 0.05
                  ? "ok"
                  : "warn",
            note: "nominal 0.800",
          },
          {
            label: "Out-of-fold rows",
            value: summary?.testRows?.toLocaleString() ?? "n/a",
            note: `target ${bench?.target ?? "n/a"} · horizon ${bench?.horizonDays ?? "n/a"}d`,
          },
          {
            label: "Deep model",
            value: summary?.tftEvaluated ? "evaluated" : "not evaluated",
            tone: summary?.tftEvaluated ? "info" : "neutral",
            note: summary?.tftEvaluated
              ? "TFT scored on the same folds"
              : "install the TFT extras to include it",
          },
        ]}
      />

      <PageBody className="flex flex-col gap-3 [&>*]:shrink-0">
        {/* ------------------------------------------------ pipeline flow -- */}
        <Panel title="Pipeline">
          <div className="p-3">
            <div className="flex items-stretch gap-2">
              {stages.map((stage, index) => (
                <StageColumn
                  key={stage.key}
                  stage={stage}
                  active={activeStage?.key === stage.key}
                  onSelect={() => setStageKey(stage.key)}
                  isLast={index === stages.length - 1}
                />
              ))}
            </div>

            {/* Inputs has no pipeline nodes of its own; it is the feed roster. */}
            {activeStage?.key === "inputs" ? (
              <div className="mt-3 border-t border-[var(--line)] pt-3">
                <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 xl:grid-cols-3">
                  {Object.values(sources).map((source) => (
                    <div key={source.source} className="flex items-baseline justify-between gap-2">
                      <span className="min-w-0 truncate text-[11.5px] text-[var(--text-2)]">
                        {source.source}
                      </span>
                      <ProvenanceTag status={source.status} ageHours={source.ageHours} />
                    </div>
                  ))}
                </div>
                <p className="mt-2 text-[11.5px] text-[var(--text-3)]">
                  {sourceCount} feeds. Full provenance is on{" "}
                  <Link to="/admin/data" className="text-[var(--info)] hover:underline">
                    Data Sources
                  </Link>
                  .
                </p>
              </div>
            ) : activeStage && activeStage.nodes.length ? (
              <div className="mt-3 grid grid-cols-1 gap-x-5 gap-y-2 border-t border-[var(--line)] pt-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {activeStage.nodes.map((node) => (
                  <div key={node.key} className="min-w-0 border-b border-[var(--line)]/50 pb-2">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-[12px] font-medium text-[var(--text)]">
                        {node.name}
                      </span>
                      <ProvenanceTag status={node.dataStatus} ageHours={node.ageHours} />
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <span className="w-14 text-[10.5px] text-[var(--text-3)]">signal</span>
                      <span className="flex-1">
                        <MiniBar
                          value={node.score}
                          tone={
                            (node.score ?? 0) >= 0.7
                              ? "crit"
                              : (node.score ?? 0) >= 0.45
                                ? "warn"
                                : "info"
                          }
                        />
                      </span>
                      <Num value={node.score} digits={3} className="w-12 text-right text-[11px]" />
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <span className="w-14 text-[10.5px] text-[var(--text-3)]">confidence</span>
                      <span className="flex-1">
                        <MiniBar value={node.confidence} tone="ok" />
                      </span>
                      <Num
                        value={node.confidence}
                        digits={2}
                        className="w-12 text-right text-[11px]"
                      />
                    </div>
                    <p className="mt-1 text-[11px] leading-snug text-[var(--text-3)]">
                      {node.effectOnForecast}
                    </p>
                    <p className="num mt-0.5 text-[10px] text-[var(--text-3)]">
                      {node.rows} rows · {formatUtc(node.observedAt)}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-3 border-t border-[var(--line)] pt-3 text-[11.5px] text-[var(--text-3)]">
                No pipeline node is registered for this stage in the current run.
              </p>
            )}
          </div>
        </Panel>

        {/* --------------------------------------------------- benchmark -- */}
        {bench?.available ? (
          <>
            <Panel
              title="Model comparison · identical folds, identical supervised frame"
              note={`${summary?.folds ?? 0} folds`}
              className="min-h-[240px]"
            >
              <DataTable
                rows={bench.models ?? []}
                columns={modelColumns}
                rowKey={(row) => row.model}
                initialSort="mae"
                initialDirection="asc"
                rowTone={(row) => (row.model === summary?.bestModel ? "var(--ok)" : null)}
              />
              <p className="border-t border-[var(--line)] px-3 py-2 text-[11.5px] leading-snug text-[var(--text-3)]">
                {bench.protocol ?? "Expanding-window walk-forward."} A training row is used
                only where its label was observable at the fold cutoff, and every model in
                this table saw the same frame.
              </p>
            </Panel>

            <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1.4fr_1fr]">
              <Panel
                title="Accuracy drilldown"
                actions={
                  <SegmentedControl
                    ariaLabel="Drilldown dimension"
                    value={drilldown}
                    onChange={setDrilldown}
                    options={[
                      { value: "horizon", label: "Horizon" },
                      { value: "port", label: "Port" },
                      { value: "regime", label: "Regime" },
                    ]}
                  />
                }
                className="min-h-[280px]"
              >
                {drilldownRows.length === 0 ? (
                  <EmptyState
                    title="No drilldown"
                    detail="The benchmark did not export this breakdown."
                  />
                ) : (
                  <DataTable
                    rows={drilldownRows}
                    columns={[
                      {
                        key: "bucket",
                        header:
                          drilldown === "horizon" ? "Horizon" : drilldown === "port" ? "Port" : "Regime",
                        width: 110,
                        render: (row) => (
                          <span className="num text-[var(--text-2)]">
                            {drilldown === "horizon"
                              ? `+${row.horizon_day}d`
                              : String(row[drilldownKey as keyof BenchmarkRow] ?? "n/a")}
                          </span>
                        ),
                        sort: (row) =>
                          drilldown === "horizon"
                            ? (row.horizon_day ?? null)
                            : String(row[drilldownKey as keyof BenchmarkRow] ?? ""),
                      },
                      {
                        key: "model",
                        header: "Model",
                        render: (row) => <span className="text-[var(--text-2)]">{row.model}</span>,
                        sort: (row) => row.model,
                      },
                      { key: "mae", header: "MAE", align: "right", width: 90, render: (row) => <Num value={row.mae} digits={3} />, sort: (row) => row.mae },
                      { key: "rmse", header: "RMSE", align: "right", width: 90, render: (row) => <Num value={row.rmse} digits={3} />, sort: (row) => row.rmse },
                      {
                        key: "cov",
                        header: "80% coverage",
                        align: "right",
                        width: 118,
                        render: (row) => <Num value={row.coverage_80pct} digits={3} />,
                        sort: (row) => row.coverage_80pct,
                      },
                    ]}
                    rowKey={(row) =>
                      `${row.model}-${row.horizon_day ?? ""}-${row.port_id ?? ""}-${row.regime ?? ""}`
                    }
                    initialSort="bucket"
                    initialDirection="asc"
                  />
                )}
              </Panel>

              <div className="flex min-w-0 flex-col gap-3">
                <Panel title="Interval calibration · nominal versus empirical">
                  {bench.calibration ? (
                    <div className="p-3">
                      <table className="data-grid">
                        <thead>
                          <tr>
                            <th className="border-b border-[var(--line)] px-2 py-[5px] text-left text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-3)]">
                              Model
                            </th>
                            {bench.calibration.levels.map((level) => (
                              <th
                                key={level}
                                className="num border-b border-[var(--line)] px-2 py-[5px] text-right text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-3)]"
                              >
                                {(level * 100).toFixed(0)}%
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(bench.calibration.models).map(([model, entries]) => (
                            <tr key={model} className="border-b border-[var(--line)]/45 last:border-0">
                              <td className="px-2 py-[5px] text-[11.5px] text-[var(--text-2)]">
                                {model}
                              </td>
                              {entries.map((entry) => (
                                <td key={entry.nominal} className="px-2 py-[5px] text-right">
                                  <Num
                                    value={entry.empirical}
                                    digits={3}
                                    tone={Math.abs(entry.error) <= 0.05 ? "ok" : "crit"}
                                  />
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11.5px] leading-snug text-[var(--text-3)]">
                        A well-calibrated model sits on the header value. Green is within
                        five points of nominal.
                      </p>
                    </div>
                  ) : (
                    <EmptyState title="Not exported" detail="The benchmark carried no calibration table." />
                  )}
                </Panel>

                <Panel title="Ensemble policy" note={weights?.fitted ? "fitted" : "default"}>
                  {weights ? (
                    <div className="p-3">
                      <BarRanking
                        items={weights.members.map((member) => ({
                          label: member,
                          value: weights.globalWeights[member] ?? null,
                          tone: "info" as const,
                        }))}
                        valueFormatter={(value) => `${(value * 100).toFixed(0)}%`}
                      />
                      <div className="mt-3 border-t border-[var(--line)] pt-2">
                        <SeriesChart
                          height={120}
                          yUnit="conformal offset by horizon"
                          series={[
                            {
                              name: "Conformal offset",
                              tone: "unc",
                              area: true,
                              points: Object.entries(weights.conformalByHorizon)
                                .sort((a, b) => Number(a[0]) - Number(b[0]))
                                .map(([day, value]) => ({ label: `+${day}`, value })),
                            },
                          ]}
                        />
                      </div>
                      <div className="mt-2 border-t border-[var(--line)] pt-2">
                        <KeyValue label="Second opinion" dense>
                          <span className="num text-[11.5px]">
                            {weights.secondOpinionModel ?? "none"}
                          </span>
                        </KeyValue>
                        <KeyValue label="Fitted on" dense>
                          <span className="num text-[11.5px]">{weights.folds} folds</span>
                        </KeyValue>
                        <KeyValue label="Source" dense>
                          <span className="text-[11px]">{weights.source}</span>
                        </KeyValue>
                      </div>
                    </div>
                  ) : (
                    <EmptyState title="No weights" detail="The run carried no ensemble weight artefact." />
                  )}
                </Panel>
              </div>
            </div>
          </>
        ) : (
          <Panel title="Walk-forward benchmark">
            <EmptyState
              tone="warn"
              title="Benchmark not run"
              detail={
                bench?.reason ??
                "No benchmark artefacts found for this run. The comparison table stays empty rather than showing an unvalidated claim."
              }
            />
          </Panel>
        )}

        {/* ------------------------------------------------- provenance -- */}
        <Panel title="Artefact provenance" note={`readiness ${((provenance.data?.readiness ?? 0) * 100).toFixed(0)}%`}>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 p-3 lg:grid-cols-3 2xl:grid-cols-4">
            {Object.values(sources).map((source) => (
              <div key={source.source} className="min-w-0">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-[11.5px] text-[var(--text-2)]">
                    {source.source}
                  </span>
                  <Pill tone={statusTone(source.status)}>{source.status}</Pill>
                </div>
                <p className="num mt-0.5 truncate text-[10px] text-[var(--text-3)]">
                  {source.rows ?? "n/a"} rows · observed {formatUtc(source.observed_at)}
                </p>
              </div>
            ))}
          </div>
        </Panel>
      </PageBody>
    </Page>
  );
}
