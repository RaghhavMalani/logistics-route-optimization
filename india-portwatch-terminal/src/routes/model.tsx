import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  Bar,
  Chip,
  ErrorState,
  Loading,
  Panel,
  ProvenanceChip,
  Value,
  formatUtc,
} from "@/components/terminal/ui";
import {
  fetchBenchmark,
  fetchPipeline,
  fetchProvenance,
} from "@/services/portwatch";
import type { Benchmark, BenchmarkRow, PipelineNode } from "@/types/portwatch";

export const Route = createFileRoute("/model")({
  validateSearch: (search: Record<string, unknown>) => ({
    port: typeof search.port === "string" ? search.port : "INMAA",
  }),
  component: ModelIntelligence,
});

type Drilldown = "horizon" | "port" | "regime";

/**
 * Model Intelligence. Everything here is read from artefacts the walk-forward
 * benchmark wrote; there are no illustrative numbers, no invented latency
 * counters and no model cards describing architectures this system does not
 * run. If the benchmark has not been executed, the screen says so and prints
 * the command that produces it.
 */
function ModelIntelligence() {
  const [drilldown, setDrilldown] = useState<Drilldown>("horizon");

  const pipelineQuery = useQuery({
    queryKey: ["model-pipeline"],
    queryFn: fetchPipeline,
    staleTime: 60_000,
  });
  const benchmarkQuery = useQuery({
    queryKey: ["benchmark"],
    queryFn: fetchBenchmark,
    staleTime: 120_000,
  });
  const provenanceQuery = useQuery({
    queryKey: ["provenance"],
    queryFn: fetchProvenance,
    staleTime: 60_000,
  });

  if (pipelineQuery.isLoading) return <Loading label="LOADING MODEL ARTEFACTS" />;
  if (pipelineQuery.isError || !pipelineQuery.data) {
    return <ErrorState error={pipelineQuery.error} />;
  }

  const pipeline = pipelineQuery.data;
  const benchmark = benchmarkQuery.data;
  const provenance = provenanceQuery.data;
  const summary = benchmark?.summary;
  const weights = benchmark?.ensembleWeights;

  const experts = pipeline.filter((node) => node.kind !== "model" && node.kind !== "decision");
  const models = pipeline.filter((node) => node.kind === "model" || node.kind === "decision");

  const drilldownRows: BenchmarkRow[] =
    (drilldown === "horizon"
      ? benchmark?.byHorizon
      : drilldown === "port"
        ? benchmark?.byPort
        : benchmark?.byRegime) ?? [];
  const drilldownKey =
    drilldown === "horizon" ? "horizon_day" : drilldown === "port" ? "port_id" : "regime";

  return (
    <div className="h-full overflow-auto p-2 space-y-2">
      {/* Headline: what the benchmark actually measured. */}
      <div className="grid grid-cols-[1fr_320px] gap-2 items-start">
        <Panel title="WALK-FORWARD BENCHMARK" right={benchmark?.version}>
          {benchmark?.available && summary ? (
            <div className="p-3 space-y-2">
              <div className="grid grid-cols-4 gap-2">
                <HeadlineStat
                  label="LEADING MODEL"
                  value={summary.bestModel}
                  tone="mint"
                />
                <HeadlineStat
                  label="MAE"
                  value={fixed(summary.bestMae, 3)}
                  tone="cyan"
                  sub={`naive ${fixed(summary.naiveMae, 3)}`}
                />
                <HeadlineStat
                  label="SKILL VS NAIVE"
                  value={
                    summary.skillVsNaive == null
                      ? "n/a"
                      : `${(summary.skillVsNaive * 100).toFixed(1)}%`
                  }
                  tone={
                    (summary.skillVsNaive ?? 0) > 0 ? "mint" : "amber"
                  }
                  sub="lower MAE is better"
                />
                <HeadlineStat
                  label="80% COVERAGE"
                  value={fixed(summary.bestCoverage80, 3)}
                  tone="cyan"
                  sub="nominal 0.800"
                />
              </div>
              <div className="text-[9px] leading-snug text-[var(--color-muted-foreground)]">
                {summary.folds} expanding walk-forward folds ·{" "}
                {summary.testRows.toLocaleString()} out-of-fold predictions ·
                target {benchmark.target} · horizon {benchmark.horizonDays}d ·
                generated {formatUtc(benchmark.generatedAt ?? null)}
                {summary.tftEvaluated
                  ? " · deep TFT evaluated on the same folds"
                  : " · deep TFT not installed in this environment, so it is not scored"}
                . {benchmark.protocol}
              </div>
            </div>
          ) : (
            <div className="p-3 text-[10px] leading-relaxed text-[var(--color-muted-foreground)]">
              <div className="text-[var(--color-amber)] mb-1">
                No benchmark artefacts in this deployment.
              </div>
              {benchmark?.reason ??
                "Run `python run_award_demo.py --source portwatch --benchmark` to produce them."}
            </div>
          )}
        </Panel>

        <Panel title="ENSEMBLE POLICY">
          {weights?.fitted ? (
            <div className="p-3 space-y-2">
              <div className="space-y-1">
                {Object.entries(weights.globalWeights).map(([member, value]) => (
                  <div key={member}>
                    <div className="flex justify-between text-[10px]">
                      <span className="text-[var(--color-muted-foreground)]">
                        {member}
                      </span>
                      <span className="tabular-nums">{(value * 100).toFixed(0)}%</span>
                    </div>
                    <Bar value={value} tone="cyan" />
                  </div>
                ))}
              </div>
              <div className="text-[9px] leading-snug text-[var(--color-muted-foreground)]">
                {weights.source}
              </div>
              <div className="pt-1 border-t border-[var(--color-line)]/50">
                <div className="label-xs mb-1">WEIGHT BY HORIZON</div>
                <div className="overflow-x-auto">
                  <table className="text-[9px] w-full">
                    <thead>
                      <tr className="text-[var(--color-muted-foreground)]">
                        <th className="text-left font-normal">H</th>
                        {weights.members.map((member) => (
                          <th key={member} className="text-right font-normal">
                            {member.slice(0, 6)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(weights.byHorizon).map(([horizon, row]) => (
                        <tr key={horizon}>
                          <td className="tabular-nums">{horizon}</td>
                          {weights.members.map((member) => (
                            <td
                              key={member}
                              className="text-right tabular-nums"
                              style={{
                                color:
                                  (row[member] ?? 0) >= 0.5
                                    ? "var(--color-cyan)"
                                    : undefined,
                              }}
                            >
                              {((row[member] ?? 0) * 100).toFixed(0)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : (
            <div className="p-3 text-[10px] text-[var(--color-muted-foreground)]">
              The ensemble is running on an explicit equal weighting because no
              fitted policy artefact exists yet.
            </div>
          )}
        </Panel>
      </div>

      {/* Model comparison table. */}
      <Panel
        title="MODEL COMPARISON · IDENTICAL FOLDS, IDENTICAL SUPERVISED FRAME"
        right={summary ? `${summary.folds} folds` : undefined}
      >
        {benchmark?.models?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="label-xs text-left border-b border-[var(--color-line)]">
                  <th className="py-1.5 px-2 font-normal">MODEL</th>
                  <th className="py-1.5 px-2 font-normal text-right">MAE</th>
                  <th className="py-1.5 px-2 font-normal text-right">RMSE</th>
                  <th className="py-1.5 px-2 font-normal text-right">MAPE %</th>
                  <th className="py-1.5 px-2 font-normal text-right">PINBALL Q10</th>
                  <th className="py-1.5 px-2 font-normal text-right">PINBALL Q50</th>
                  <th className="py-1.5 px-2 font-normal text-right">PINBALL Q90</th>
                  <th className="py-1.5 px-2 font-normal text-right">80% COVERAGE</th>
                  <th className="py-1.5 px-2 font-normal text-right">BAND WIDTH</th>
                  <th className="py-1.5 px-2 font-normal text-right">CALIB ERR</th>
                </tr>
              </thead>
              <tbody>
                {benchmark.models.map((row) => {
                  const isLeader = row.model === summary?.bestModel;
                  return (
                    <tr
                      key={row.model}
                      className={`border-b border-[var(--color-line)]/30 ${
                        isLeader ? "bg-[var(--color-mint)]/5" : ""
                      }`}
                    >
                      <td className="py-1.5 px-2">
                        <span
                          className={
                            isLeader ? "text-[var(--color-mint)]" : undefined
                          }
                        >
                          {row.model}
                        </span>
                        {isLeader && (
                          <Chip tone="mint">
                            <span className="ml-1">LEADER</span>
                          </Chip>
                        )}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        <Value value={row.mae} digits={3} />
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        <Value value={row.rmse} digits={3} />
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        <Value value={row.mape_pct} digits={2} />
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        <Value value={row.pinball_q10} digits={3} />
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        <Value value={row.pinball_q50} digits={3} />
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        <Value value={row.pinball_q90} digits={3} />
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        <CoverageCell value={row.coverage_80pct} />
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        <Value value={row.interval_width} digits={2} />
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        <Value value={row.calibration_error} digits={3} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-3 text-[10px] text-[var(--color-muted-foreground)]">
            No model comparison artefact available.
          </div>
        )}
      </Panel>

      <div className="grid grid-cols-[1.35fr_1fr] gap-2">
        <Panel
          title="ACCURACY DRILLDOWN"
          right={
            <span className="flex gap-1">
              {(["horizon", "port", "regime"] as const).map((option) => (
                <button
                  key={option}
                  onClick={() => setDrilldown(option)}
                  className={`px-1.5 py-[1px] border text-[9px] tracking-widest uppercase ${
                    drilldown === option
                      ? "border-[var(--color-cyan)] text-[var(--color-cyan)]"
                      : "border-[var(--color-line-strong)] text-[var(--color-muted-foreground)]"
                  }`}
                >
                  {option}
                </button>
              ))}
            </span>
          }
        >
          {drilldownRows.length ? (
            <DrilldownTable rows={drilldownRows} groupKey={drilldownKey} />
          ) : (
            <div className="p-3 text-[10px] text-[var(--color-muted-foreground)]">
              No {drilldown} breakdown artefact available.
            </div>
          )}
        </Panel>

        <div className="grid grid-rows-2 gap-2 min-h-0">
          <Panel title="INTERVAL CALIBRATION · NOMINAL VS EMPIRICAL">
            {benchmark?.calibration ? (
              <CalibrationTable calibration={benchmark.calibration} />
            ) : (
              <div className="p-3 text-[10px] text-[var(--color-muted-foreground)]">
                No calibration artefact available.
              </div>
            )}
          </Panel>

          <Panel title="SOURCE PROVENANCE">
            {provenance?.sources && Object.keys(provenance.sources).length ? (
              <div className="p-2 space-y-1.5">
                {Object.values(provenance.sources).map((source) => (
                  <div
                    key={source.source}
                    className="border-b border-[var(--color-line)]/30 pb-1.5 last:border-0"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] text-[var(--color-foreground)] truncate">
                        {source.source}
                      </span>
                      <ProvenanceChip
                        status={source.status}
                        ageHours={source.ageHours}
                        detail={source.detail}
                      />
                    </div>
                    <div className="text-[9px] text-[var(--color-muted-foreground)] leading-snug">
                      {source.provider}
                      {source.rows != null && ` · ${source.rows.toLocaleString()} rows`}
                      {source.observed_at &&
                        ` · observed ${formatUtc(source.observed_at)}`}
                    </div>
                    {source.fallback && (
                      <div className="text-[9px] text-[var(--color-amber)]">
                        fallback: {source.fallback}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-3 text-[10px] text-[var(--color-muted-foreground)]">
                {provenance?.reason ?? "No provenance record for this run."}
              </div>
            )}
          </Panel>
        </div>
      </div>

      {/* Pipeline nodes. */}
      <Panel title="INTELLIGENCE PIPELINE · EXPERTS">
        <div className="p-2 grid grid-cols-5 gap-1.5">
          {experts.map((node) => (
            <PipelineCard key={node.key} node={node} />
          ))}
        </div>
      </Panel>

      <Panel title="INTELLIGENCE PIPELINE · MODELS AND DECISION">
        <div className="p-2 grid grid-cols-3 gap-1.5">
          {models.map((node) => (
            <PipelineCard key={node.key} node={node} wide />
          ))}
        </div>
      </Panel>
    </div>
  );
}

function HeadlineStat({
  label,
  value,
  tone,
  sub,
}: {
  label: string;
  value: string;
  tone: "cyan" | "mint" | "amber";
  sub?: string;
}) {
  return (
    <div className="panel px-2.5 py-2">
      <div className="label-xs">{label}</div>
      <div
        className="text-[16px] leading-tight tabular-nums truncate"
        style={{ color: `var(--color-${tone})` }}
        title={value}
      >
        {value}
      </div>
      {sub && (
        <div className="text-[9px] text-[var(--color-muted-foreground)]">{sub}</div>
      )}
    </div>
  );
}

/** Formats a number that the pipeline may legitimately not have produced. */
function fixed(value: number | null | undefined, digits: number): string {
  return value == null || Number.isNaN(value) ? "n/a" : value.toFixed(digits);
}

function CoverageCell({ value }: { value: number | null | undefined }) {
  if (value == null) return <Value value={null} />;
  const error = Math.abs(value - 0.8);
  const tone = error <= 0.03 ? "mint" : error <= 0.08 ? "amber" : "red";
  return (
    <span style={{ color: `var(--color-${tone})` }}>{value.toFixed(3)}</span>
  );
}

function DrilldownTable({
  rows,
  groupKey,
}: {
  rows: BenchmarkRow[];
  groupKey: string;
}) {
  const models = Array.from(new Set(rows.map((row) => row.model)));
  const groups = Array.from(
    new Set(rows.map((row) => String(row[groupKey as keyof BenchmarkRow] ?? ""))),
  ).sort((a, b) => {
    const na = Number(a);
    const nb = Number(b);
    if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
    return a.localeCompare(b);
  });
  const lookup = new Map(
    rows.map((row) => [
      `${row.model}|${String(row[groupKey as keyof BenchmarkRow] ?? "")}`,
      row,
    ]),
  );

  return (
    <div className="overflow-auto">
      <table className="w-full text-[10px]">
        <thead>
          <tr className="label-xs text-left border-b border-[var(--color-line)]">
            <th className="py-1.5 px-2 font-normal">
              {groupKey === "horizon_day"
                ? "HORIZON"
                : groupKey === "port_id"
                  ? "PORT"
                  : "REGIME"}
            </th>
            {models.map((model) => (
              <th
                key={model}
                className="py-1.5 px-2 font-normal text-right whitespace-nowrap"
                title={model}
              >
                {model
                  .replace(" quantile", "")
                  .replace(" (deep)", "")
                  .replace("Naive persistence", "Persistence")
                  .replace("Seasonal naive (7d)", "Seasonal 7d")
                  .replace("Adaptive ensemble", "Ensemble")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => {
            const cells = models.map((model) => lookup.get(`${model}|${group}`));
            const best = cells.reduce<number | null>(
              (min, cell) =>
                cell?.mae != null && (min == null || cell.mae < min)
                  ? cell.mae
                  : min,
              null,
            );
            return (
              <tr key={group} className="border-b border-[var(--color-line)]/30">
                <td className="py-1 px-2 text-[var(--color-muted-foreground)]">
                  {groupKey === "horizon_day" ? `+${group}d` : group}
                </td>
                {cells.map((cell, index) => (
                  <td
                    key={models[index]}
                    className="py-1 px-2 text-right tabular-nums"
                    style={{
                      color:
                        cell?.mae != null && best != null && cell.mae === best
                          ? "var(--color-mint)"
                          : undefined,
                    }}
                    title={
                      cell?.mae == null
                        ? "This model produced no prediction for this cell"
                        : undefined
                    }
                  >
                    {cell?.mae == null ? "—" : cell.mae.toFixed(2)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="px-2 py-1 text-[9px] text-[var(--color-muted-foreground)]">
        Mean absolute error; the lowest value in each row is highlighted.
      </div>
    </div>
  );
}

function CalibrationTable({
  calibration,
}: {
  calibration: NonNullable<Benchmark["calibration"]>;
}) {
  const models = Object.keys(calibration.models);
  return (
    <div className="overflow-auto">
      <table className="w-full text-[10px]">
        <thead>
          <tr className="label-xs text-left border-b border-[var(--color-line)]">
            <th className="py-1.5 px-2 font-normal">MODEL</th>
            {calibration.levels.map((level) => (
              <th key={level} className="py-1.5 px-2 font-normal text-right">
                {(level * 100).toFixed(0)}%
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {models.map((model) => (
            <tr key={model} className="border-b border-[var(--color-line)]/30">
              <td className="py-1 px-2 truncate max-w-[130px]" title={model}>
                {model}
              </td>
              {calibration.models[model].map((entry) => {
                const tone =
                  entry.error <= 0.03
                    ? "mint"
                    : entry.error <= 0.08
                      ? "amber"
                      : "red";
                return (
                  <td
                    key={entry.nominal}
                    className="py-1 px-2 text-right tabular-nums"
                    style={{ color: `var(--color-${tone})` }}
                    title={`error ${entry.error.toFixed(3)} · mean width ${entry.meanWidth.toFixed(1)}`}
                  >
                    {entry.empirical.toFixed(3)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="px-2 py-1 text-[9px] text-[var(--color-muted-foreground)]">
        Empirical coverage against the nominal level. A well-calibrated model
        sits on the header value.
      </div>
    </div>
  );
}

function PipelineCard({ node, wide }: { node: PipelineNode; wide?: boolean }) {
  const tone =
    node.score == null
      ? "muted"
      : node.score > 0.7
        ? "red"
        : node.score > 0.45
          ? "amber"
          : "mint";
  return (
    <div
      className={`panel p-2 min-w-0 ${node.available ? "" : "opacity-60"}`}
      title={node.artefact}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="label-xs truncate">{node.key}</span>
        <ProvenanceChip status={node.dataStatus} />
      </div>
      <div className="mt-0.5 text-[10px] text-[var(--color-foreground)] truncate">
        {node.name}
      </div>
      <div className="mt-1 flex items-baseline justify-between text-[10px]">
        <span className="text-[var(--color-muted-foreground)]">signal</span>
        <span
          className="tabular-nums"
          style={{ color: `var(--color-${tone === "muted" ? "muted-foreground" : tone})` }}
        >
          {node.score == null ? "n/a" : node.score.toFixed(3)}
        </span>
      </div>
      <Bar value={node.score ?? 0} tone={tone === "muted" ? "muted" : tone} />
      <div className="mt-1 flex items-baseline justify-between text-[9px]">
        <span className="text-[var(--color-muted-foreground)]">confidence</span>
        <span className="tabular-nums text-[var(--color-cyan)]">
          {node.confidence == null ? "n/a" : node.confidence.toFixed(2)}
        </span>
      </div>
      <div className="mt-1 text-[9px] leading-snug text-[var(--color-muted-foreground)]">
        {node.inputSignal}
      </div>
      <div
        className={`mt-1 text-[9px] leading-snug text-[var(--color-foreground)]/80 ${wide ? "" : "line-clamp-2"}`}
      >
        {node.effectOnForecast}
      </div>
      <div className="mt-1 pt-1 border-t border-[var(--color-line)]/40 text-[8px] text-[var(--color-muted-foreground)]">
        {node.rows.toLocaleString()} rows
        {node.observedAt && ` · ${formatUtc(node.observedAt)}`}
        {node.modelCard && ` · ${node.modelCard}`}
      </div>
    </div>
  );
}
