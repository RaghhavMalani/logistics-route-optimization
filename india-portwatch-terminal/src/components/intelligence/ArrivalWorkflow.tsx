import { useState, type FormEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { Panel } from "@/components/kit/layout";
import {
  arrivalWrite,
  useArrivals,
  type ArrivalOperation,
} from "@/services/arrivals";
import { postJson } from "@/services/api";
import { useWorldClock } from "@/services/lenses";
import ArrivalCollection from "./ArrivalCollection";

const hours = (n: number | null) =>
  n == null ? "Unavailable" : `${n.toFixed(2)} h`;
const time = (s: string) => new Date(s).toLocaleString();
const inputClass =
  "w-full rounded border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5 text-sm";
const buttonClass =
  "rounded border border-[var(--line)] px-3 py-1.5 text-xs disabled:opacity-40";
function Fields({ children }: { children: ReactNode }) {
  return <div className="grid gap-3 sm:grid-cols-2">{children}</div>;
}
function Field({
  name,
  label,
  type = "text",
  required = true,
  ...props
}: {
  name: string;
  label: string;
  type?: string;
  required?: boolean;
  min?: string;
  max?: string;
  step?: string;
  pattern?: string;
}) {
  return (
    <label className="grid gap-1 text-xs">
      {label}
      <input
        name={name}
        type={type}
        required={required}
        className={inputClass}
        step={type === "datetime-local" ? "1" : undefined}
        {...props}
      />
    </label>
  );
}
function payload(form: HTMLFormElement, timestamps: string[] = []) {
  const data = Object.fromEntries(new FormData(form));
  for (const field of timestamps)
    data[field] = new Date(String(data[field])).toISOString();
  return data;
}
type Write = (
  path: string,
  body?: unknown,
  advisory?: boolean,
) => Promise<void>;

export default function ArrivalWorkflow({ portCode }: { portCode: string }) {
  const { session } = useAuth();
  const clock = useWorldClock();
  const queries = useQueryClient();
  const [selected, select] = useState<string | null>(null);
  const [create, showCreate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const supported = portCode === "INNSA",
    verified = session?.mode === "production",
    live = clock.data?.mode === "LIVE";
  const query = useArrivals(
    portCode,
    `${clock.data?.mode}:${clock.data?.anchor ?? ""}`,
    supported && verified && !!clock.data,
  );
  const state = query.data;
  const current =
    state?.operations.find((c) => c.operationId === selected) ??
    state?.operations[0];
  const write: Write = async (path, data = {}, advisory = false) => {
    setBusy(true);
    setError(null);
    try {
      const result = advisory
        ? await postJson(`/advisories/${path}`, data)
        : await arrivalWrite(path, data);
      if (result && typeof result === "object" && "operationId" in result)
        select(String(result.operationId));
      await queries.invalidateQueries({ queryKey: ["arrivals"] });
      await queries.invalidateQueries({ queryKey: ["advisories"] });
      showCreate(false);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Unable to record arrival workflow",
      );
    } finally {
      setBusy(false);
    }
  };
  const submitCreate = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const data = payload(e.currentTarget, [
      "plannedArrivalAt",
      "baselineEstimatedAt",
      "baselineAvailableAt",
    ]);
    void write("operations", {
      ...data,
      baselineWaitHours: Number(data.baselineWaitHours),
      routeRevision: data.routeRevision || null,
    });
  };
  return (
    <Panel title="Arrival evidence → measured outcome">
      <div className="space-y-4 p-4 text-sm" data-testid="arrival-workflow">
        <p className="text-xs text-[var(--text-3)]">
          JNPA pilot · anchorage arrival to all-fast, hours. Approval and
          acceptance are separate from actual action and measured savings.
        </p>
        {!supported ? (
          <p>
            The first measured workflow covers JNPA (INNSA). Select JNPA to
            inspect it.
          </p>
        ) : !verified ? (
          <p>A verified operator session is required for arrival evidence.</p>
        ) : query.isError ? (
          <div role="alert">
            {query.error.message}{" "}
            <button
              className={buttonClass}
              onClick={() => void query.refetch()}
            >
              Retry arrival workflow
            </button>
          </div>
        ) : !state ? (
          <p>Loading recorded arrivals…</p>
        ) : (
          <>
            <ArrivalCollection
              state={state}
              live={live}
              busy={busy}
              start={() => void write("collection")}
            />
            <div className="flex flex-wrap items-center gap-3">
              <span>{state.measuredCount} complete measured arrivals</span>
              <button
                className={buttonClass}
                disabled={!live || busy}
                onClick={() => showCreate(!create)}
              >
                Register arrival evidence
              </button>
              <button
                className={buttonClass}
                disabled={
                  !live ||
                  busy ||
                  (state.collection.cohort
                    ? !state.collection.evaluationReady
                    : state.evaluationEligibleCount < 60)
                }
                onClick={() => void write("benchmark")}
              >
                Seal later-period evaluation
              </button>
            </div>
            {!live && (
              <p>
                Historical view: only evidence recorded by this instant is
                shown. Writes require the live clock.
              </p>
            )}
            {error && (
              <p role="alert" className="text-[var(--crit)]">
                {error}
              </p>
            )}
            {create && (
              <form
                onSubmit={submitCreate}
                className="space-y-3 border border-[var(--line)] p-3"
              >
                <Fields>
                  <Field
                    name="operationRef"
                    label="Arrival / booking reference"
                  />
                  <Field
                    name="mmsi"
                    label="Observed vessel MMSI"
                    pattern="[1-9][0-9]{8}"
                  />
                  <Field name="vesselName" label="Vessel name" />
                  <Field
                    name="recipientOrganisation"
                    label="Recipient organisation"
                  />
                  <Field
                    name="plannedArrivalAt"
                    label="Planned anchorage arrival"
                    type="datetime-local"
                  />
                  <Field
                    name="routeRevision"
                    label="Route revision (if known)"
                    required={false}
                  />
                  <Field
                    name="baselineWaitHours"
                    label="Incumbent scheduled wait, hours"
                    type="number"
                    min="0"
                    max="720"
                    step="0.01"
                  />
                  <Field
                    name="baselineSource"
                    label="Incumbent schedule source / reference"
                  />
                  <Field
                    name="baselineRef"
                    label="Individual scheduler reference"
                  />
                  <Field
                    name="baselineEstimatedAt"
                    label="Scheduler estimate issued at"
                    type="datetime-local"
                  />
                  <Field
                    name="baselineAvailableAt"
                    label="Scheduler estimate available at"
                    type="datetime-local"
                  />
                </Fields>
                <p className="text-xs">
                  Use the scheduler's estimate for this specific call. Aggregate
                  congestion and generated twin queues do not provide this
                  baseline. Weather and AIS references are joined on the server.
                </p>
                <button className={buttonClass} disabled={busy || !live}>
                  Freeze evidence and create review
                </button>
              </form>
            )}
            {!state.operations.length && (
              <p>
                No arrival operations recorded. Register a planned arrival with
                its MMSI and incumbent schedule reference.
              </p>
            )}
            {!!state.operations.length && (
              <label className="grid max-w-xl gap-1 text-xs">
                Arrival operation
                <select
                  aria-label="Arrival operation"
                  className={inputClass}
                  value={current?.operationId ?? ""}
                  onChange={(e) => select(e.target.value)}
                >
                  {state.operations.map((c) => (
                    <option key={c.operationId} value={c.operationId}>
                      {c.operationRef} · {c.vesselName} ·{" "}
                      {c.outcome ? "Observed" : "Pending outcome"}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {current && (
              <Case
                key={current.operationId}
                value={current}
                live={live}
                busy={busy}
                write={write}
              />
            )}
            <div
              className="border-t border-[var(--line)] pt-3"
              data-testid="arrival-benchmark"
            >
              <h3 className="mb-2 font-medium">
                Untouched later-period benchmark
              </h3>
              {state.benchmark ? (
                <>
                  <p>
                    {state.benchmark.fitCount} fit ·{" "}
                    {state.benchmark.calibrationCount} calibration ·{" "}
                    {state.benchmark.holdoutCount} holdout
                  </p>
                  <p className="text-xs">
                    Fit through {time(state.benchmark.fitThrough)}; calibration{" "}
                    {time(state.benchmark.calibrationFrom)}–
                    {time(state.benchmark.calibrationThrough)}; holdout{" "}
                    {time(state.benchmark.holdoutFrom)}–
                    {time(state.benchmark.holdoutThrough)}.
                  </p>
                  {state.benchmark.metrics && (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs">
                        <caption className="py-2 text-left">
                          Same untouched calls; bias = observed − predicted; 80%
                          intervals calibrated separately
                        </caption>
                        <thead>
                          <tr>
                            <th>Estimator</th>
                            <th>MAE (h)</th>
                            <th>Signed bias (h)</th>
                            <th>Coverage</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(state.benchmark.metrics).map(
                            ([name, m]) => (
                              <tr key={name}>
                                <td>{name.replaceAll("_", " ")}</td>
                                <td>{m.maeHours.toFixed(2)}</td>
                                <td>{m.signedBiasHours.toFixed(2)}</td>
                                <td>
                                  {(100 * m.intervalCoverage).toFixed(1)}%
                                </td>
                              </tr>
                            ),
                          )}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {state.benchmark.incrementalValue && (
                    <p className="text-xs">
                      Weather/AIS MAE reduction vs scheduler-only GBM:{" "}
                      {hours(
                        state.benchmark.incrementalValue
                          .weatherAndAisMaeReductionHours,
                      )}
                      ; weather given AIS:{" "}
                      {hours(
                        state.benchmark.incrementalValue
                          .weatherGivenAisMaeReductionHours,
                      )}
                      ; AIS given weather:{" "}
                      {hours(
                        state.benchmark.incrementalValue
                          .aisGivenWeatherMaeReductionHours,
                      )}
                      . Positive means lower error.{" "}
                      {state.benchmark.incrementalValue.interpretation}.
                    </p>
                  )}
                  <p>
                    GBM MAE {hours(state.benchmark.gbmMaeHours)} · incumbent MAE{" "}
                    {hours(state.benchmark.baselineMaeHours)} · historical
                    median MAE {hours(state.benchmark.historicalMedianMaeHours)}
                  </p>
                  <p>
                    GBM 80% interval coverage:{" "}
                    {(100 * state.benchmark.intervalCoverage).toFixed(1)}%.
                    Calibration-selected model: {state.benchmark.promotion}.
                  </p>
                  <p className="text-xs">
                    {state.benchmark.limitations} Dataset{" "}
                    {state.benchmark.datasetHash.slice(0, 16)}.
                  </p>
                </>
              ) : (
                <p>{state.reason}. No measured model accuracy is available.</p>
              )}
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}

function Case({
  value: c,
  live,
  busy,
  write,
}: {
  value: ArrivalOperation;
  live: boolean;
  busy: boolean;
  write: Write;
}) {
  const root = `operations/${c.operationId}`,
    issued = c.advisory?.audit.some((a) => a.to_state === "issued");
  const chain = [
    [
      "Signal",
      `${c.evidence.weather.length} weather forecasts · ${c.evidence.tracks.length} observed AIS reports`,
    ],
    [
      "Decision",
      `${c.approved ? "Approved" : "Awaiting review"} · ${c.decisionId}`,
    ],
    [
      "Advisory",
      c.advisory ? `${c.advisory.state} · ${c.advisory.id}` : "Not drafted",
    ],
    ["Actual action", c.actualAction?.actualAction ?? "Not recorded"],
    [
      "Outcome",
      c.outcome
        ? `${hours(c.outcome.waitHours)} · ${c.outcome.source}`
        : "Awaiting confirmed port-call times",
    ],
  ];
  return (
    <div className="space-y-4" data-testid="arrival-case">
      <dl className="grid gap-3 sm:grid-cols-3">
        <div>
          <dt className="text-xs">Expected waiting</dt>
          <dd>{hours(c.prediction.value)}</dd>
          <dd className="text-xs">
            {c.prediction.low == null
              ? "Uncertainty unavailable until calibration"
              : `80% interval ${hours(c.prediction.low)}–${hours(c.prediction.high)}`}
          </dd>
        </div>
        <div>
          <dt className="text-xs">Frozen incumbent</dt>
          <dd>{hours(c.baselineWaitHours)}</dd>
          <dd className="text-xs">{c.baselineSource}</dd>
          {c.baselineRef && (
            <dd className="text-xs">
              {c.baselineRef}; estimate issued {time(c.baselineEstimatedAt!)};
              available {time(c.baselineAvailableAt!)}.
            </dd>
          )}
        </div>
        <div>
          <dt className="text-xs">Observed waiting / error</dt>
          <dd>
            {hours(c.outcome?.waitHours ?? null)} / {hours(c.errorHours)}
          </dd>
          <dd className="text-xs">
            {c.withinInterval == null
              ? "Coverage pending"
              : c.withinInterval
                ? "Within predicted interval"
                : "Outside predicted interval"}
            ; error = observed − predicted
          </dd>
        </div>
      </dl>
      <ol
        className="grid gap-3 md:grid-cols-5"
        aria-label="Arrival evidence chain"
      >
        {chain.map(([label, detail]) => (
          <li
            key={label}
            className="min-w-0 border-l-2 border-[var(--line)] pl-2"
          >
            <strong className="text-xs">{label}</strong>
            <p className="break-words text-xs text-[var(--text-3)]">{detail}</p>
          </li>
        ))}
      </ol>
      <p className="text-xs">
        {c.recommendation}. Planned arrival {time(c.plannedArrivalAt)}; frozen{" "}
        {time(c.issuedAt)}.
      </p>
      <details>
        <summary className="cursor-pointer text-xs">
          Evidence, missing inputs and audit
        </summary>
        <div className="space-y-3 pt-3 text-xs">
          <p>
            {c.evidence.matchRationale}. MMSI {c.mmsi}; route revision{" "}
            {c.routeRevision ?? "unavailable"}.
          </p>
          <p>{c.evidence.camera.reason}.</p>
          <ul className="list-inside list-disc">
            {c.missingEvidence.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
          {c.evidence.weather.map((w) => (
            <p key={w.id}>
              {w.variable}: original {w.original.toFixed(2)}, consumed{" "}
              {w.consumed.toFixed(2)} {w.unit}; {w.source}; issued{" "}
              {time(w.issuedAt)}, target ends {time(w.validAt)}, recorded{" "}
              {time(w.recordedAt)}, available {time(w.availableAt)}.{" "}
              <span className="break-all">{w.id}</span>
            </p>
          ))}
          <p>
            {c.evidence.tracks.length} archived AIS reports{" "}
            {c.evidence.tracks[0] &&
              `from ${time(c.evidence.tracks[0].observedAt)} to ${time(c.evidence.tracks.at(-1)!.observedAt)}`}
            .
          </p>
          {c.evidence.tracks.slice(-3).map((t) => (
            <p key={t.id}>
              {t.source} · {t.rawRef} · {t.lat.toFixed(4)}, {t.lon.toFixed(4)} ·
              observed {time(t.observedAt)} · available {time(t.availableAt)} ·
              recorded {time(t.recordedAt)}
            </p>
          ))}
          {c.events.map((e) => (
            <p key={e.kind}>
              {e.kind} · {time(e.recordedAt)} · {e.actor}
            </p>
          ))}
          {c.advisory?.audit.map((a, i) => (
            <p key={i}>
              Advisory {a.to_state} · {time(a.at)} · {a.actor}
            </p>
          ))}
          {c.actualAction && (
            <p>
              Action: {c.actualAction.source}; occurred{" "}
              {time(c.actualAction.occurredAt)}, available{" "}
              {time(c.actualAction.availableAt)}.
            </p>
          )}
          {c.outcome && (
            <p>
              {c.outcome.berthRef}: arrival {time(c.outcome.arrivedAt)},
              all-fast {time(c.outcome.berthedAt)}, available{" "}
              {time(c.outcome.availableAt)}, recorded{" "}
              {time(c.outcome.recordedAt)}.
            </p>
          )}
        </div>
      </details>
      {c.disposition && (
        <p className="text-xs">
          Excluded: {c.disposition.reason} · {c.disposition.source}
        </p>
      )}
      {live && !c.outcome && !c.disposition && (
        <div className="space-y-3">
          {!c.approved && (
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                void write(`${root}/approve`, payload(e.currentTarget));
              }}
            >
              <Field name="note" label="Arrival review note" />
              <button className={buttonClass} disabled={busy}>
                Approve arrival review
              </button>
            </form>
          )}
          {c.approved && !c.advisory && (
            <button
              className={buttonClass}
              disabled={busy}
              onClick={() => void write(`${root}/advisory`)}
            >
              Create arrival review advisory
            </button>
          )}
          {c.advisory?.state === "draft" && (
            <button
              className={buttonClass}
              disabled={busy}
              onClick={() =>
                void write(
                  `${c.advisory!.id}/transition`,
                  { target: "under_review" },
                  true,
                )
              }
            >
              Review arrival advisory
            </button>
          )}
          {c.advisory?.state === "under_review" && (
            <button
              className={buttonClass}
              disabled={busy}
              onClick={() =>
                void write(
                  `${c.advisory!.id}/transition`,
                  { target: "issued" },
                  true,
                )
              }
            >
              Approve and issue arrival advisory
            </button>
          )}
          {issued && !c.actualAction && (
            <form
              className="space-y-3 border border-[var(--line)] p-3"
              onSubmit={(e) => {
                e.preventDefault();
                void write(
                  `${root}/action`,
                  payload(e.currentTarget, ["occurredAt", "availableAt"]),
                );
              }}
            >
              <Fields>
                <Field
                  name="actualAction"
                  label="Actual action taken / declined"
                />
                <label className="grid gap-1 text-xs">
                  Action status
                  <select className={inputClass} name="actionState">
                    <option value="taken">Taken</option>
                    <option value="modified">Modified</option>
                    <option value="not_taken">Not taken</option>
                  </select>
                </label>
                <Field
                  name="occurredAt"
                  label="Action occurred at"
                  type="datetime-local"
                />
                <Field
                  name="availableAt"
                  label="Action evidence available at"
                  type="datetime-local"
                />
                <Field name="source" label="Actual action source / reference" />
              </Fields>
              <button className={buttonClass} disabled={busy}>
                Record actual action
              </button>
            </form>
          )}
          {
            <form
              className="space-y-3 border border-[var(--line)] p-3"
              onSubmit={(e) => {
                e.preventDefault();
                void write(
                  `${root}/outcome`,
                  payload(e.currentTarget, [
                    "arrivedAt",
                    "berthedAt",
                    "availableAt",
                    "arrivalAvailableAt",
                    "allFastAvailableAt",
                  ]),
                );
              }}
            >
              <Fields>
                <Field
                  name="arrivedAt"
                  label="Confirmed anchorage arrival"
                  type="datetime-local"
                />
                <Field
                  name="berthedAt"
                  label="Confirmed all-fast time"
                  type="datetime-local"
                />
                <Field
                  name="availableAt"
                  label="Outcome evidence available at"
                  type="datetime-local"
                />
                <Field
                  name="berthRef"
                  label="Berth / port-call log reference"
                />
                <Field name="source" label="Outcome source" />
                <Field
                  name="sourceRef"
                  label="Outcome log / confirmation reference"
                />
                <Field
                  name="arrivalAvailableAt"
                  label="Anchorage record available at"
                  type="datetime-local"
                />
                <Field
                  name="allFastAvailableAt"
                  label="All-fast record available at"
                  type="datetime-local"
                />
                <label className="grid gap-1 text-xs">
                  Outcome evidence kind
                  <select className={inputClass} name="kind">
                    <option value="port_call_log">Port-call log</option>
                    <option value="operator_confirmed">
                      Operator confirmed
                    </option>
                  </select>
                </label>
              </Fields>
              <button className={buttonClass} disabled={busy}>
                Resolve measured waiting
              </button>
              <p className="text-xs">
                Measurements can be collected without an advisory. Missing
                action evidence remains missing; no decision or operational
                benefit is inferred.
              </p>
            </form>
          }
          {c.cohortId && (
            <details>
              <summary className="cursor-pointer text-xs">
                Resolve a cancelled or duplicate call
              </summary>
              <form
                className="space-y-3 pt-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = payload(e.currentTarget, ["availableAt"]);
                  void write(`${root}/disposition`, {
                    ...data,
                    duplicateOf: data.duplicateOf || null,
                  });
                }}
              >
                <Fields>
                  <label className="grid gap-1 text-xs">
                    Exclusion reason
                    <select className={inputClass} name="reason">
                      <option value="cancelled">Confirmed cancelled</option>
                      <option value="duplicate">Duplicate call</option>
                    </select>
                  </label>
                  <Field
                    name="duplicateOf"
                    label="Canonical operation ID (duplicates only)"
                    required={false}
                  />
                  <Field
                    name="source"
                    label="Cancellation / duplicate evidence reference"
                  />
                  <Field
                    name="availableAt"
                    label="Disposition evidence available at"
                    type="datetime-local"
                  />
                </Fields>
                <button className={buttonClass} disabled={busy}>
                  Record call disposition
                </button>
              </form>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
