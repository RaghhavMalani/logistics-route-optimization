import { lazy, Suspense, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getJson, postJson } from "@/services/api";
import { formatUtc } from "@/components/kit/primitives";
import { CargoCard, Source } from "./CargoCard";
import { money, percent, tone } from "./view-model";
import type {
  Interval,
  RiskOption,
  RiskReport,
  RiskResponse,
  Rule,
} from "./types";
import "./cargo-risk.css";

const CargoMiniature = lazy(() => import("./CargoMiniature"));
const SEED = 20261112;

function isRiskReport(value: RiskResponse | undefined): value is RiskReport {
  return value?.status === "SHADOW";
}
const RULES: Record<Rule, string> = {
  R1: "Expected cost",
  R2: "Deadline chance limit (10%)",
  R3: "Tail cost (CVaR95)",
  R4: "Minimax cost regret",
  R5: "Hybrid (90% and tail check)",
};

const hour = (value: number) => value.toFixed(1) + " h";
const intervalTitle = (interval: Interval, unit: (value: number) => string) =>
  "95% simulation interval " +
  unit(interval.lower95) +
  "–" +
  unit(interval.upper95);

function StudyCharts({ report }: { report: RiskReport }) {
  const arrivals = report.options.flatMap((option) => option.arrival.hours);
  const first = Math.min(...arrivals);
  const last = Math.max(...arrivals);
  const arrivalPosition = (value: number) =>
    percent((value - first) / Math.max(last - first, 1));
  const priced = report.options.flatMap((option) => [
    ...option.cost.dots,
    option.cost.knownSubtotal?.cvar95 ?? 0,
  ]);
  const min = Math.min(...priced);
  const max = Math.max(...priced);
  const costPosition = (value: number) =>
    percent((value - min) / Math.max(max - min, 1));
  const price = (value: number) => money(value, report.currency);

  return (
    <>
      <section className="cargo-risk-section">
        <h3>
          Arrival fan <Source>MODELLED · P10–P90 hours after decision</Source>
        </h3>
        {report.options.map((option) => {
          const [low, median, high] = option.arrival.hours;
          return (
            <div key={option.id} className="cargo-chart-row">
              <div>
                <b>{option.label}</b>
                <span>
                  {hour(low)} / <strong>{hour(median)}</strong> / {hour(high)}
                </span>
              </div>
              <div
                className="cargo-plot"
                role="img"
                aria-label={
                  "P10 " +
                  hour(low) +
                  ", P50 " +
                  hour(median) +
                  ", P90 " +
                  hour(high)
                }
              >
                <span
                  className="cargo-fan"
                  style={{
                    left: arrivalPosition(low),
                    width: arrivalPosition(high - low + first),
                  }}
                />
                <i
                  className="cargo-p50"
                  style={{ left: arrivalPosition(median) }}
                />
              </div>
            </div>
          );
        })}
      </section>
      <section className="cargo-risk-section">
        <h3>
          Cost distribution <Source>MODELLED · paired cost quantiles</Source>
        </h3>
        {report.options.map((option) => {
          const subtotal = option.cost.knownSubtotal;
          const uncertainty = option.cost.uncertainty;
          return (
            <div key={option.id} className="cargo-chart-row">
              <div>
                <b>{option.label}</b>
                <span>{option.cost.scope}</span>
              </div>
              {subtotal && uncertainty ? (
                <>
                  <div
                    className="cargo-plot"
                    role="img"
                    aria-label="Cost quantiles, mean and tail mean on a common scale"
                  >
                    {option.cost.dots.map((dot, index) => (
                      <i
                        className="cargo-dot"
                        style={{
                          left: costPosition(dot),
                          top: 5 + 4 * (index % 3),
                        }}
                        key={index}
                      />
                    ))}
                    <i
                      className="cargo-mean"
                      style={{ left: costPosition(subtotal.expected) }}
                    />
                    <i
                      className="cargo-tail"
                      style={{ left: costPosition(subtotal.cvar95) }}
                    />
                  </div>
                  <div>
                    <span title={intervalTitle(uncertainty.mean, price)}>
                      Mean <b>{price(subtotal.expected)}</b>
                    </span>
                    <span title={intervalTitle(uncertainty.cvar95, price)}>
                      CVaR95 <b>{price(subtotal.cvar95)}</b>
                    </span>
                  </div>
                </>
              ) : (
                <p>Cost unknown</p>
              )}
            </div>
          );
        })}
      </section>
    </>
  );
}

function ClosureQuestion({ report }: { report: RiskReport }) {
  const [index, setIndex] = useState(0);
  const { grid, flips, basis } = report.closureSensitivity;
  const point = grid[index] ?? grid[0];
  if (!point) return null;
  const label = (id: string | null) =>
    report.options.find((option) => option.id === id)?.label ??
    "No comparable option";
  return (
    <section className="cargo-risk-section">
      <h3>
        What would change the decision?{" "}
        <Source>MODELLED · closure held fixed across paired futures</Source>
      </h3>
      <label className="cargo-range">
        Closure duration <b>{hour(point.closureHours)}</b>
        <input
          type="range"
          min={0}
          max={grid.length - 1}
          step={1}
          value={index}
          aria-valuetext={hour(point.closureHours)}
          onChange={(event) => setIndex(Number(event.target.value))}
        />
      </label>
      <p>
        At this duration <strong>{label(point.optionId)}</strong>.
      </p>
      {flips.length ? (
        <ul className="cargo-sources">
          {flips.map((flip) => (
            <li key={flip.lowerHours}>
              {hour(flip.lowerHours)}–{hour(flip.upperHours)} ·{" "}
              {label(flip.fromOptionId)} → {label(flip.toOptionId)}
            </li>
          ))}
        </ul>
      ) : (
        <p>No break-even in the tested range.</p>
      )}
      <small>{basis}</small>
    </section>
  );
}

function CargoDetail({
  report,
  option,
}: {
  report: RiskReport;
  option: RiskOption;
}) {
  const [atRisk, setAtRisk] = useState(false);
  const [showMiniature, setShowMiniature] = useState(false);
  const slots = useMemo(
    () => option.consignments.slice(0, 12).map(tone),
    [option.consignments],
  );
  const rows = option.consignments.flatMap((loss) => {
    const cargo = report.cargo.find((row) => row.id === loss.id);
    return cargo ? [{ cargo, loss }] : [];
  });
  return (
    <section className="cargo-risk-section">
      <h3>
        Probability of on-time delivery{" "}
        <Source>MODELLED · per consignment</Source>
      </h3>
      <table className="cargo-deadline-table">
        <thead>
          <tr>
            <th scope="col">Consignment</th>
            <th scope="col">On time</th>
            <th scope="col">95% sim. interval</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ cargo, loss }) => (
            <tr key={cargo.id}>
              <th scope="row">{cargo.name}</th>
              <td data-tone={tone(loss)}>
                {loss.onTime ? percent(loss.onTime.estimate) : "Unknown"}
              </td>
              <td>
                {loss.onTime
                  ? percent(loss.onTime.lower95) +
                    "–" +
                    percent(loss.onTime.upper95)
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="cargo-control-row">
        <label>
          <input
            type="checkbox"
            checked={atRisk}
            onChange={(event) => setAtRisk(event.target.checked)}
          />{" "}
          At risk only
        </label>
        <button
          type="button"
          aria-expanded={showMiniature}
          onClick={() => setShowMiniature(!showMiniature)}
        >
          {showMiniature ? "Hide cargo miniature" : "Show cargo miniature"}
        </button>
      </div>
      {showMiniature && (
        <figure className="cargo-model">
          <Suspense fallback={<p>Loading modelled cargo view…</p>}>
            <CargoMiniature slots={slots} />
          </Suspense>
          <figcaption>
            <b>Vessel deck / Port twin</b> · SCHEMATIC{" "}
            <Source>MODELLED · illustrative container locations</Source>
            <small>
              Amber/red mark deadline or spoilage risk. Showing up to 12
              consignments from the selected option.
            </small>
          </figcaption>
        </figure>
      )}
      <div className="cargo-card-grid">
        {rows
          .filter(
            ({ loss }) =>
              !atRisk || tone(loss) === "warn" || tone(loss) === "crit",
          )
          .map(({ cargo, loss }) => (
            <CargoCard
              key={cargo.id}
              cargo={cargo}
              loss={loss}
              currency={report.currency}
            />
          ))}
        {atRisk &&
          !rows.some(
            ({ loss }) => tone(loss) === "warn" || tone(loss) === "crit",
          ) && <p>No consignments cross the modelled risk thresholds.</p>}
      </div>
      {Object.keys(option.cost.unknown).length > 0 && (
        <details>
          <summary>
            Unpriced costs ({Object.keys(option.cost.unknown).length})
          </summary>
          <ul className="cargo-sources">
            {Object.entries(option.cost.unknown).map(([name, reason]) => (
              <li key={name}>
                {name.split("/").at(-1)?.replaceAll("_", " ")} · Unknown.{" "}
                {reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

export function RiskTab({ problemId }: { problemId: string }) {
  const { identityHeaders } = useAuth();
  const [rule, setRule] = useState<Rule>("R1");
  const [jobId, setJobId] = useState(() => crypto.randomUUID());
  const [optionId, setOptionId] = useState<string | null>(null);
  const path =
    "/commercial/comparisons/" + encodeURIComponent(problemId) + "/cargo-risk";
  const study = useQuery({
    queryKey: ["cargo-risk", problemId, rule, SEED, jobId],
    queryFn: ({ signal }) =>
      postJson<RiskResponse>(
        path,
        { rule, seed: SEED, jobId },
        identityHeaders,
        { signal },
      ),
    staleTime: Infinity,
    retry: false,
  });
  const progress = useQuery({
    queryKey: ["cargo-risk-progress", problemId, jobId],
    queryFn: async ({ signal }) => {
      await new Promise<void>((resolve) => setTimeout(resolve, 1500));
      signal.throwIfAborted();
      return getJson<{ progress?: { n: number; difference: Interval | null } }>(
        path + "/jobs/" + jobId,
        identityHeaders,
        { signal, bypassScreen: true },
      );
    },
    enabled: study.isFetching,
    refetchInterval: study.isFetching ? 1000 : false,
    retry: false,
  });
  const report = isRiskReport(study.data) ? study.data : null;
  const option =
    report?.options.find(
      (row) => row.id === (optionId ?? report.decision.optionId),
    ) ?? report?.options[0];

  return (
    <div className="cargo-risk" data-testid="cargo-risk-tab">
      <header className="cargo-risk-lead">
        <div className="cargo-kicker">
          Company private · Modelled shadow study
        </div>
        <h2>Cargo risk</h2>
        {report && (
          <p data-testid="cargo-rule-reason">
            <b>{report.decision.rule}</b> · {report.decision.reason}
          </p>
        )}
        <label className="cargo-rule">
          Decision rule
          <select
            value={rule}
            onChange={(event) => {
              setRule(event.target.value as Rule);
              setJobId(crypto.randomUUID());
              setOptionId(null);
            }}
          >
            {Object.entries(RULES).map(([key, title]) => (
              <option key={key} value={key}>
                {key} · {title}
              </option>
            ))}
          </select>
        </label>
        {study.isPending && (
          <p role="status">
            {progress.data?.progress
              ? progress.data.progress.n.toLocaleString() +
                " paired futures evaluated"
              : "Sampling paired futures…"}
          </p>
        )}
        {study.isError && (
          <p role="alert">
            {study.error.message}{" "}
            <button
              type="button"
              onClick={() => {
                setJobId(crypto.randomUUID());
              }}
            >
              Retry
            </button>
          </p>
        )}
        {study.data?.status === "UNAVAILABLE" && <p>{study.data.reason}</p>}
        {report && (
          <small>
            {report.scope} · {report.diagnostics.n.toLocaleString()} futures ·{" "}
            {report.diagnostics.stop}
            {report.diagnostics.difference &&
              " · paired SE " +
                money(
                  report.diagnostics.difference.standardError,
                  report.currency,
                )}
          </small>
        )}
      </header>
      {report && option && (
        <>
          <StudyCharts report={report} />
          <ClosureQuestion report={report} />
          <label className="cargo-rule">
            Cargo option
            <select
              value={option.id}
              onChange={(event) => setOptionId(event.target.value)}
            >
              {report.options.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.label}
                </option>
              ))}
            </select>
          </label>
          <CargoDetail report={report} option={option} />
          <details className="cargo-risk-section">
            <summary>Sources and reproducibility</summary>
            <ul className="cargo-sources">
              <li>
                As of {formatUtc(report.asOf)} ·{" "}
                <Source>FROZEN COMPARISON</Source>
              </li>
              <li>
                Seed {report.seed} · paired error target{" "}
                {money(report.diagnostics.threshold, report.currency)}
              </li>
              <li className="cargo-hash">Input hash {report.inputHash}</li>
              <li>{report.sourceBasis.closure}</li>
              <li>{report.sourceBasis.handling}</li>
              <li>{report.sourceBasis.fuel ?? "Fuel price basis unknown"}</li>
              <li>
                {report.sourceBasis.fx ?? "Retained FX basis unavailable"}
              </li>
              {Object.entries(report.sourceBasis.options).map(([id, basis]) => (
                <li key={id}>
                  {report.options.find((row) => row.id === id)?.label} ·{" "}
                  {basis.passage} · {basis.weather} · {basis.port}
                </li>
              ))}
              {report.excludedOptions.map((row) => (
                <li key={row.label}>
                  {row.label} · {row.reason}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </div>
  );
}
