import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { useAuth } from "@/auth/AuthProvider";
import { getJson } from "@/services/api";
import { formatUtc } from "@/components/kit/primitives";
import { Button } from "@/components/ui/button";

const metrics = z.object({
  bias: z.number(),
  mae: z.number(),
  rmse: z.number(),
  underpredictions: z.number(),
  overpredictions: z.number(),
  exact: z.number(),
});
const comparison = z
  .object({
    raw: metrics.extend({ count: z.number() }),
    corrected: metrics.extend({
      count: z.number(),
      intervalCoverage: z.number().optional(),
      nominalCoverage: z.number().optional(),
    }),
    passes: z.boolean(),
  })
  .nullable()
  .optional();
const target = z
  .object({
    targetId: z.string(),
    predictionId: z.string(),
    issuedAt: z.string(),
    validAt: z.string(),
    targetDate: z.string(),
    availableAt: z.string(),
    leadTimeHours: z.number(),
    raw: z.number(),
    outcome: z.number(),
    error: z.number(),
    forecastResponseSha256: z.string(),
    outcomeResponseSha256: z.string(),
    measurementWindow: z.object({
      from: z.string(),
      through: z.string(),
      definition: z.string(),
    }),
  })
  .passthrough();
const schema = z
  .object({
    asOf: z.string(),
    mode: z.literal("SHADOW_ONLY"),
    decisionEligible: z.literal(false),
    errorConvention: z.string(),
    horizonDefinition: z.string(),
    selectionPolicy: z.string(),
    analysisVersion: z.string(),
    reportId: z.string(),
    summary: z
      .object({
        resolvedSnapshots: z.number(),
        qualifiedSnapshots: z.number(),
        independentTargets: z.number(),
        duplicateSnapshots: z.number(),
        excludedSnapshots: z.number(),
        contexts: z.number(),
        targetDates: z.number(),
        cohortMemberships: z.number(),
      })
      .passthrough(),
    contexts: z.array(
      z
        .object({
          id: z.string(),
          portCode: z.string(),
          variable: z.string(),
          provider: z.string(),
          horizonDays: z.number(),
          outcomeSource: z.string(),
          outcomeKind: z.string(),
          season: z.string(),
          unit: z.string(),
          statistic: z.string(),
          aggregation: z.string(),
          requestedLocation: z.object({ lat: z.number(), lon: z.number() }),
          forecastLocation: z.object({ lat: z.number(), lon: z.number() }),
          outcomeLocation: z.object({ lat: z.number(), lon: z.number() }),
          independentTargets: z.number(),
          forecastSnapshots: z.number(),
          metrics,
          systematicMiss: z
            .object({
              direction: z.string(),
              share: z.number(),
              descriptiveOnly: z.literal(true),
            })
            .passthrough(),
          readiness: z
            .object({
              status: z.string(),
              minimumIndependentTargets: z.number(),
              minimumPerPartition: z.number(),
              partitions: z.record(z.number()),
              purged: z.number(),
              shortfalls: z.record(z.number()),
              reasons: z.array(z.string()),
            })
            .passthrough(),
          shadow: z
            .object({
              status: z.string(),
              decisionEligible: z.literal(false),
              biasAdjustment: z.number().nullable(),
              correctionId: z.string().nullable(),
              adoptionCriteria: z.record(z.unknown()),
              adoptionCriteriaText: z.array(z.string()),
              validation: comparison,
              evaluation: comparison,
            })
            .passthrough(),
          targets: z.array(target),
        })
        .passthrough(),
    ),
    exclusions: z.array(
      z.object({ predictionId: z.string(), reason: z.string() }).passthrough(),
    ),
  })
  .passthrough();
const number = (value: number) => value.toFixed(2);

export function WeatherShadowPanel({
  portCode,
  variable,
}: {
  portCode?: string;
  variable?: string;
}) {
  const { identityHeaders } = useAuth();
  const [opened, setOpened] = useState(false);
  const [selected, setSelected] = useState("");
  const [source, setSource] = useState<string | null>(null);
  const [portFilter, setPortFilter] = useState(portCode ?? "");
  const [variableFilter, setVariableFilter] = useState(variable ?? "");
  const [providerFilter, setProviderFilter] = useState("");
  const [horizonFilter, setHorizonFilter] = useState("");
  const q = useQuery({
    queryKey: ["weather-shadow", identityHeaders],
    queryFn: async ({ signal }) => {
      const parsed = schema.safeParse(
        await getJson<unknown>("/weather/shadow", identityHeaders, {
          signal,
          timeoutMs: 60000,
        }),
      );
      if (!parsed.success)
        throw new Error(
          "Shadow-analysis response is malformed; no candidate is usable.",
        );
      return parsed.data;
    },
    enabled: opened,
    staleTime: 60000,
    retry: 1,
  });
  const raw = useQuery({
    queryKey: ["weather-shadow-original", source, identityHeaders],
    queryFn: ({ signal }) =>
      getJson(`/weather/evidence/${source}`, identityHeaders, { signal }),
    enabled: !!source,
  });
  const visible =
    q.data?.contexts.filter(
      (c) =>
        (!portFilter || c.portCode === portFilter) &&
        (!variableFilter || c.variable === variableFilter) &&
        (!providerFilter || c.provider === providerFilter) &&
        (!horizonFilter || String(c.horizonDays) === horizonFilter),
    ) ?? [];
  const cell = visible.find((c) => c.id === selected) ?? visible[0];
  function download() {
    if (!q.data) return;
    const blob = new Blob([JSON.stringify(q.data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `weather-shadow-${q.data.reportId}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <details
      className="border border-[var(--line)] p-2 my-2 text-[11px]"
      data-testid="weather-shadow-analysis"
    >
      <summary className="cursor-pointer" onClick={() => setOpened(true)}>
        Matched error analysis and daily correction shadow readiness
      </summary>
      <p>
        Daily research only. Candidate comparisons do not adopt a correction,
        alter hourly gust/visibility gates or promote neural/RL models.
      </p>
      {q.isPending && opened ? (
        <p>
          Checking retained matched evidence and chronological availability…
        </p>
      ) : null}
      {q.isError ? <p role="alert">{q.error.message}</p> : null}
      {q.data ? (
        <>
          <p>
            As of {formatUtc(q.data.asOf)} · {q.data.mode}.{" "}
            {q.data.errorConvention}
          </p>
          <p>
            {q.data.summary.independentTargets} independent outcome targets
            across {q.data.summary.targetDates} dates ·{" "}
            {q.data.summary.contexts} analysis contexts ·{" "}
            {q.data.summary.qualifiedSnapshots} qualified snapshots ·{" "}
            {q.data.summary.duplicateSnapshots} repeated context snapshots ·{" "}
            {q.data.summary.excludedSnapshots} excluded. The same weather
            outcome may be compared at several horizons; context memberships are
            not extra outcomes or independent days.
          </p>
          <p>Selection: {q.data.selectionPolicy}</p>
          <p>
            Nearby ports and weather variables can share weather patterns;
            logical target counts do not establish statistical independence
            across ports or variables.
          </p>
          <p>{q.data.horizonDefinition}</p>
          <div className="flex flex-wrap gap-2">
            <label>
              Port{" "}
              <select
                className="bg-[var(--panel)]"
                value={portFilter}
                onChange={(e) => setPortFilter(e.target.value)}
              >
                <option value="">All ports</option>
                {Array.from(new Set(q.data.contexts.map((c) => c.portCode)))
                  .sort()
                  .map((v) => (
                    <option key={v}>{v}</option>
                  ))}
              </select>
            </label>
            <label>
              Variable{" "}
              <select
                className="bg-[var(--panel)]"
                value={variableFilter}
                onChange={(e) => setVariableFilter(e.target.value)}
              >
                <option value="">All variables</option>
                {Array.from(new Set(q.data.contexts.map((c) => c.variable)))
                  .sort()
                  .map((v) => (
                    <option key={v} value={v}>
                      {v.replaceAll("_", " ")}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Provider{" "}
              <select
                className="bg-[var(--panel)] max-w-full"
                value={providerFilter}
                onChange={(e) => setProviderFilter(e.target.value)}
              >
                <option value="">All providers</option>
                {Array.from(new Set(q.data.contexts.map((c) => c.provider)))
                  .sort()
                  .map((v) => (
                    <option key={v}>{v}</option>
                  ))}
              </select>
            </label>
            <label>
              Horizon{" "}
              <select
                className="bg-[var(--panel)]"
                value={horizonFilter}
                onChange={(e) => setHorizonFilter(e.target.value)}
              >
                <option value="">All horizons</option>
                {Array.from(new Set(q.data.contexts.map((c) => c.horizonDays)))
                  .sort((a, b) => a - b)
                  .map((v) => (
                    <option key={v} value={v}>
                      +{v}d
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <p>
            Showing {visible.length} contexts. Global outcome counts above are
            not the sum of these horizon comparisons.
          </p>
          <div className="overflow-auto max-h-60 my-2">
            <table className="w-full text-left text-[10.5px] num">
              <caption className="text-left">
                Port / variable / provider / horizon. Bias and errors use
                independent targets within each context.
              </caption>
              <thead>
                <tr>
                  {[
                    "Context",
                    "Targets / snapshots",
                    "Bias",
                    "MAE",
                    "Under / over",
                    "Readiness",
                  ].map((h) => (
                    <th className="p-1 font-normal" key={h}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((c) => (
                  <tr className="border-t border-[var(--line)]" key={c.id}>
                    <td className="p-1">
                      <button
                        className="underline text-left"
                        onClick={() => {
                          setSelected(c.id);
                          setSource(null);
                        }}
                      >
                        {c.portCode} · {c.variable.replaceAll("_", " ")} ·{" "}
                        {c.provider} · +{c.horizonDays}d
                      </button>
                    </td>
                    <td className="p-1">
                      {c.independentTargets} / {c.forecastSnapshots}
                    </td>
                    <td className="p-1">
                      {number(c.metrics.bias)} {c.unit}
                    </td>
                    <td className="p-1">
                      {number(c.metrics.mae)} {c.unit}
                    </td>
                    <td className="p-1">
                      {c.metrics.underpredictions} / {c.metrics.overpredictions}
                    </td>
                    <td className="p-1">
                      {c.readiness.status} · {c.shadow.status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {visible.length === 0 ? (
            <p>
              No evidence-qualified matched context is available for this
              selection. Missing outcomes and unsupported variables remain
              unscored.
            </p>
          ) : null}
          {cell ? (
            <section
              className="border border-[var(--line)] p-2 space-y-2"
              aria-label="Selected shadow context"
            >
              <p>
                <strong>
                  {cell.portCode} · {cell.variable.replaceAll("_", " ")} ·{" "}
                  {cell.provider} · +{cell.horizonDays}d
                </strong>
              </p>
              <p>
                {cell.outcomeSource}. {cell.statistic} · {cell.aggregation} ·{" "}
                {cell.season}.
              </p>
              <p>
                Requested port coordinate {cell.requestedLocation.lat},{" "}
                {cell.requestedLocation.lon}; forecast grid{" "}
                {cell.forecastLocation.lat}, {cell.forecastLocation.lon};
                outcome grid {cell.outcomeLocation.lat},{" "}
                {cell.outcomeLocation.lon}. Gridded reanalysis is not a
                port-station measurement.
              </p>
              <p>
                {cell.independentTargets} independent targets from{" "}
                {cell.forecastSnapshots} snapshots. RMSE{" "}
                {number(cell.metrics.rmse)} {cell.unit}. Observed pattern:{" "}
                {cell.systematicMiss.direction},{" "}
                {(100 * cell.systematicMiss.share).toFixed(0)}% of these
                targets. This is descriptive evidence; a small sample cannot
                establish a stable systematic error.
              </p>
              <p>
                Chronological readiness:{" "}
                <strong>{cell.readiness.status}</strong>. Nominal minimum{" "}
                {cell.readiness.minimumIndependentTargets} targets; at least{" "}
                {cell.readiness.minimumPerPartition} in each fitting,
                validation, calibration and subsequent evaluation block after
                availability purging. A total of 32 alone is insufficient.
              </p>
              <div className="overflow-auto">
                <table className="w-full text-left num">
                  <caption className="text-left">
                    Chronological blocks · {cell.readiness.purged} targets
                    excluded by outcome availability
                  </caption>
                  <thead>
                    <tr>
                      <th>Block</th>
                      <th>Available targets</th>
                      <th>Current block shortfall</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(cell.readiness.partitions).map(
                      ([name, count]) => (
                        <tr key={name}>
                          <td>{name}</td>
                          <td>{count}</td>
                          <td>{cell.readiness.shortfalls[name] ?? 0}</td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
              <ul className="list-disc pl-4">
                {cell.readiness.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
              <p>
                Daily candidate: <strong>{cell.shadow.status}</strong>.
                Fitting-only median residual adjustment:{" "}
                {cell.shadow.biasAdjustment == null
                  ? "unavailable"
                  : `${number(cell.shadow.biasAdjustment)} ${cell.unit}`}
                . Candidate {cell.shadow.correctionId ?? "not yet created"};
                adoption: NOT ADOPTED.
              </p>
              {cell.shadow.validation || cell.shadow.evaluation ? (
                <div className="overflow-auto">
                  <table className="w-full text-left num">
                    <caption className="text-left">
                      Eligible daily shadow replay · {cell.unit}
                    </caption>
                    <thead>
                      <tr>
                        <th>Block</th>
                        <th>Independent targets</th>
                        <th>Raw MAE</th>
                        <th>Shadow MAE</th>
                        <th>MAE criterion</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(
                        [
                          ["Validation", cell.shadow.validation],
                          ["Subsequent evaluation", cell.shadow.evaluation],
                        ] as const
                      ).map(([name, block]) =>
                        block ? (
                          <tr key={name}>
                            <td>{name}</td>
                            <td>{block.raw.count}</td>
                            <td>{number(block.raw.mae)}</td>
                            <td>{number(block.corrected.mae)}</td>
                            <td>{block.passes ? "Pass" : "Reject"}</td>
                          </tr>
                        ) : null,
                      )}
                    </tbody>
                  </table>
                  {cell.shadow.evaluation?.corrected.intervalCoverage !=
                  null ? (
                    <p>
                      Held-out interval coverage:{" "}
                      {(
                        100 * cell.shadow.evaluation.corrected.intervalCoverage
                      ).toFixed(0)}
                      % of {cell.shadow.evaluation.corrected.count} targets
                      (nominal 80%; no future guarantee).
                    </p>
                  ) : null}
                </div>
              ) : (
                <p>
                  No eligible raw-versus-corrected validation/evaluation
                  comparison yet. The raw daily forecast remains consumed.
                </p>
              )}
              <details>
                <summary>Explicit adoption criteria</summary>
                <ul className="list-disc pl-4">
                  {cell.shadow.adoptionCriteriaText.map((criterion) => (
                    <li key={criterion}>{criterion}</li>
                  ))}
                </ul>
                <p>
                  Passing retrospective shadow replay alone does not adopt a
                  model. This version has no adoption action.
                </p>
              </details>
              <details>
                <summary>Independent targets and retained evidence</summary>
                {cell.targets.map((t) => (
                  <div
                    className="border-t border-[var(--line)] py-2"
                    key={t.targetId}
                  >
                    <p>
                      UTC target {t.targetDate} · raw {number(t.raw)} → outcome{" "}
                      {number(t.outcome)} {cell.unit}; error {number(t.error)}.
                      Forecast received {formatUtc(t.issuedAt)}, outcome
                      available {formatUtc(t.availableAt)}.
                    </p>
                    <p>
                      Receipt-to-target-start lead: {number(t.leadTimeHours)}{" "}
                      hours.
                    </p>
                    <p className="break-all">
                      Forecast {t.predictionId}. Target {t.targetId}.
                    </p>
                    <p>
                      Measurement window {formatUtc(t.measurementWindow.from)} →{" "}
                      {formatUtc(t.measurementWindow.through)}.{" "}
                      {t.measurementWindow.definition}
                    </p>
                    <button
                      className="underline mr-2"
                      onClick={() => setSource(t.forecastResponseSha256)}
                    >
                      Inspect original forecast
                    </button>
                    <button
                      className="underline"
                      onClick={() => setSource(t.outcomeResponseSha256)}
                    >
                      Inspect later outcome
                    </button>
                  </div>
                ))}
              </details>
            </section>
          ) : null}
          <details>
            <summary>Excluded records and policy trace</summary>
            <p className="break-all">
              Analysis {q.data.analysisVersion} · {q.data.reportId}
            </p>
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all">
              {JSON.stringify(q.data.exclusions, null, 2)}
            </pre>
          </details>
          <Button size="sm" variant="outline" onClick={download}>
            Download shadow audit JSON
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => void q.refetch()}
            disabled={q.isFetching}
          >
            Refresh shadow analysis
          </Button>
        </>
      ) : null}
      {source ? (
        <details open className="max-h-56 overflow-auto">
          <summary>Retained original · {source}</summary>
          {raw.isError ? (
            <p role="alert">
              Original unavailable; no replacement is substituted.
            </p>
          ) : (
            <pre className="whitespace-pre-wrap break-all">
              {JSON.stringify(raw.data, null, 2)}
            </pre>
          )}
        </details>
      ) : null}
    </details>
  );
}
