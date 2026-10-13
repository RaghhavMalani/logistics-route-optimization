import { useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  resultUrl,
  usePublicResearch,
  type PublicResearch as ResearchData,
} from "@/services/public-research";
import { DataState, LinePlot, PublicShell } from "./PublicShell";
import { fmt, utc } from "./format";
import { PublicPortCases } from "./PublicPortCases";

const pct = (n?: number | null) =>
  n == null ? "Unavailable" : `${fmt(n * 100)}%`;
function HistoricalResults({ data }: { data: ResearchData }) {
  const [model, setModel] = useState("GBM quantile"),
    [horizon, setHorizon] = useState(1);
  const [showBounds, setShowBounds] = useState(true);
  const chosen = data.models.find((m) => m.model === model) ?? data.models[0];
  const horizons = data.horizons
    .filter((m) => m.model === chosen?.model)
    .sort((a, b) => (a.horizon_day ?? 0) - (b.horizon_day ?? 0));
  const baseline = data.horizons
    .filter((m) => m.model === "Naive persistence")
    .sort((a, b) => (a.horizon_day ?? 0) - (b.horizon_day ?? 0));
  const series = data.series
    .filter((s) => s.model === chosen?.model && s.horizon_day === horizon)
    .sort((a, b) => a.target_date.localeCompare(b.target_date));
  const calibration = data.calibration?.models[chosen?.model ?? ""] ?? [];
  const selected = data.horizons.find(
    (m) => m.model === chosen?.model && m.horizon_day === horizon,
  );
  return (
    <>
      <section className="public-research-intro">
        <span className="public-badge">
          Historical benchmark / congestion proxy
        </span>
        <p>{data.datasetMeaning}</p>
        <p className="public-note">
          The reporting holdout has been examined previously. This release adds
          feature ablations; it does not create a new untouched trial. These
          errors are congestion-index points, not vessel waiting hours.
        </p>
        <div className="public-facts">
          <span>
            Published<strong>{utc(data.generatedAt)}</strong>
          </span>
          <span>
            Dataset rows
            <strong>{fmt(data.reproducibility?.datasetRows, 0)}</strong>
          </span>
          <span>
            Protocol<strong>{data.evaluationProtocol}</strong>
          </span>
        </div>
      </section>
      <section>
        <div className="public-section-title">
          <div>
            <p className="public-eyebrow">01 / Chronological comparison</p>
            <h2>Models against simple baselines</h2>
          </div>
          <a
            className="public-download"
            href={resultUrl("model_benchmark.csv", data.releaseId)}
          >
            Download metrics ↓
          </a>
        </div>
        <p className="public-note">
          MAE and RMSE: lower is better. Signed bias = observed − predicted; a
          positive value means underprediction. Coverage is the share inside the
          nominal 80% interval.
        </p>
        <div className="public-table-wrap">
          <table>
            <caption className="public-sr-only">
              Historical model performance on the same reporting rows
            </caption>
            <thead>
              <tr>
                <th scope="col">Model</th>
                <th scope="col">MAE</th>
                <th scope="col">RMSE</th>
                <th scope="col">Signed bias</th>
                <th scope="col">80% coverage</th>
                <th scope="col">Interval width</th>
                <th scope="col">Rows</th>
              </tr>
            </thead>
            <tbody>
              {data.models.map((m) => (
                <tr key={m.model}>
                  <th scope="row">{m.model}</th>
                  <td>{fmt(m.mae, 3)}</td>
                  <td>{fmt(m.rmse, 3)}</td>
                  <td>{fmt(m.signed_bias, 3)}</td>
                  <td>{pct(m.coverage_80pct)}</td>
                  <td>{fmt(m.interval_width, 2)}</td>
                  <td>{fmt(m.n, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section>
        <div className="public-section-title">
          <div>
            <p className="public-eyebrow">02 / Forecast horizons</p>
            <h2>Where the error changes</h2>
          </div>
          <label>
            Compare model
            <select
              aria-label="Compare model"
              value={chosen?.model ?? ""}
              onChange={(e) => setModel(e.target.value)}
            >
              {data.models.map((m) => (
                <option key={m.model}>{m.model}</option>
              ))}
            </select>
          </label>
        </div>
        <LinePlot
          title="MAE across forecast horizons, congestion-index points"
          max={
            Math.max(
              1,
              ...horizons.map((h) => h.mae),
              ...baseline.map((h) => h.mae),
            ) * 1.15
          }
          labels={horizons.map((h) => `D${h.horizon_day}`)}
          lines={[
            {
              name: chosen?.model ?? "Model",
              values: horizons.map((h) => h.mae),
              color: "#235d50",
            },
            {
              name: "Naive persistence",
              values: baseline.map((h) => h.mae),
              color: "#b07044",
            },
          ]}
        />
        <div className="public-section-title">
          <h3>Predicted versus observed</h3>
          <label>
            Reporting horizon
            <select
              aria-label="Reporting horizon"
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
            >
              {Array.from({ length: 10 }, (_, i) => (
                <option key={i} value={i + 1}>
                  Day {i + 1}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p className="public-note">
          This plot averages ports on each target date for display. The
          row-level errors in the tables and downloads are computed before
          averaging.
        </p>
        <label className="public-bounds-toggle">
          <input
            type="checkbox"
            checked={showBounds}
            onChange={(e) => setShowBounds(e.target.checked)}
          />{" "}
          Show published quantile bounds
        </label>
        <LinePlot
          title="Predicted versus observed cross-port mean congestion proxy"
          labels={series.map((s) => s.target_date.slice(5, 10))}
          band={
            showBounds && series.some((s) => s.low != null && s.high != null)
              ? {
                  name: "Mean published lower / upper bounds",
                  low: series.map((s) => s.low),
                  high: series.map((s) => s.high),
                }
              : undefined
          }
          lines={[
            {
              name: "Observed proxy",
              values: series.map((s) => s.observed),
              color: "#b07044",
            },
            {
              name: "Predicted median",
              values: series.map((s) => s.predicted),
              color: "#235d50",
            },
          ]}
        />
        <p className="public-note">
          Shading averages individual ports’ lower and upper quantiles. It is
          not a calibrated confidence interval for the cross-port mean. Coverage
          in the table uses individual prediction rows.
        </p>
        <div className="public-facts">
          <span>
            Day {horizon} MAE<strong>{fmt(selected?.mae, 3)}</strong>
          </span>
          <span>
            Day {horizon} bias<strong>{fmt(selected?.signed_bias, 3)}</strong>
          </span>
          <span>
            Day {horizon} coverage
            <strong>{pct(selected?.coverage_80pct)}</strong>
          </span>
        </div>
        <a href={resultUrl("holdout_predictions.csv", data.releaseId)}>
          Download individual predictions and observations ↓
        </a>
      </section>
      <div className="public-research-grid">
        <section>
          <p className="public-eyebrow">03 / Interval calibration</p>
          <h2>Coverage against its target</h2>
          {calibration.length ? (
            <>
              <LinePlot
                title="Nominal versus empirical interval coverage in percent"
                labels={calibration.map((c) => pct(c.nominal))}
                lines={[
                  {
                    name: "Nominal coverage",
                    values: calibration.map((c) => c.nominal * 100),
                    color: "#b07044",
                  },
                  {
                    name: "Empirical coverage",
                    values: calibration.map((c) => c.empirical * 100),
                    color: "#235d50",
                  },
                ]}
              />
              <p className="public-note">
                Calibration uses the earlier calibration period. This chart
                reports coverage on the later reporting period, without
                recalibrating on it.
              </p>
            </>
          ) : (
            <p className="public-note">
              This baseline has no interval forecast; coverage is unavailable.
            </p>
          )}
        </section>
        <section>
          <p className="public-eyebrow">04 / Feature ablations</p>
          <h2>What changes without feature groups</h2>
          <div className="public-table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">GBM feature set</th>
                  <th scope="col">MAE</th>
                  <th scope="col">Change vs full</th>
                </tr>
              </thead>
              <tbody>
                {data.ablations.map((a) => (
                  <tr key={a.model}>
                    <th scope="row">
                      {a.model === "GBM quantile"
                        ? "Full origin-time features"
                        : a.model.replace("GBM ", "")}
                    </th>
                    <td>{fmt(a.mae, 3)}</td>
                    <td>{fmt(a.mae_change_vs_full_gbm, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="public-note">
            Common chronological rows and model settings. Feature removal can
            reveal predictive association; it does not identify a causal weather
            or event effect. Future weather without issue-time archives stays
            excluded.
          </p>
        </section>
      </div>
      <section>
        <p className="public-eyebrow">05 / Reproduce and inspect</p>
        <h2>The evidence behind the comparison</h2>
        <ol className="public-partitions">
          <li>
            <strong>Weight fitting</strong>Through{" "}
            {utc(data.partitions?.weightFitThrough)}
          </li>
          <li>
            <strong>Interval calibration</strong>
            {utc(data.partitions?.calibrationFrom)} →{" "}
            {utc(data.partitions?.calibrationThrough)}
          </li>
          <li>
            <strong>Reporting holdout</strong>
            {utc(data.partitions?.holdoutFrom)} →{" "}
            {utc(data.partitions?.holdoutThrough)}
          </li>
        </ol>
        <p className="public-note">
          Expanding-window base-model training precedes each fold. Labels
          crossing partition boundaries are purged; full-history regime features
          are excluded.
        </p>
        <details className="public-version-details">
          <summary>Dataset, code and model versions</summary>
          <dl>
            <dt>Release</dt>
            <dd>{data.releaseId}</dd>
            <dt>Protocol / model configuration</dt>
            <dd>
              {data.evaluationProtocol} ·{" "}
              {JSON.stringify(data.reproducibility?.configuration)}
            </dd>
            <dt>Dataset SHA-256</dt>
            <dd>{data.reproducibility?.datasetSha256}</dd>
            <dt>Forecast code SHA-256</dt>
            <dd>{data.reproducibility?.forecastCodeSha256}</dd>
            <dt>Base Git revision</dt>
            <dd>
              {data.reproducibility?.codeRevision} (code hash identifies local
              evaluation changes)
            </dd>
            <dt>Runtime dependencies</dt>
            <dd>{JSON.stringify(data.reproducibility?.dependencies)}</dd>
          </dl>
        </details>
        <div className="public-downloads">
          {data.downloads.map((d) => (
            <a key={d.name} href={resultUrl(d.name, data.releaseId)}>
              <strong>{d.name} ↓</strong>
              <span>
                {fmt(d.bytes / 1024, 1)} KB · SHA-256 {d.sha256}
              </span>
            </a>
          ))}
        </div>
        <ul className="public-limit-list">
          {data.limits.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      </section>
    </>
  );
}
export function PublicResearch() {
  const query = usePublicResearch(),
    data = query.data;
  return (
    <PublicShell section="research">
      <section className="public-hero">
        <div>
          <p className="public-eyebrow">Research, open to inspection</p>
          <h1>
            Show the forecast.
            <br />
            Measure the error.
          </h1>
          <p>
            Explore chronological comparisons, uncertainty and reproducible
            results. Historical benchmarks, route simulations and operational
            observations each carry their own evidence.
          </p>
        </div>
        <aside className="public-hero-aside">
          <strong>Evidence before claims</strong>
          <span>Versioned results and raw predictions</span>
          <Link to="/explore">Explore the shipping scenarios ↗</Link>
        </aside>
      </section>
      <PublicPortCases />
      {query.isPending || query.isError ? (
        <DataState
          pending={query.isPending}
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      ) : (
        data && (
          <div className="public-research-body">
            {data.available ? (
              <HistoricalResults data={data} />
            ) : (
              <section>
                <h2>Historical results unavailable</h2>
                <p>{data.reason}</p>
              </section>
            )}
            <section>
              <p className="public-eyebrow">Weather forecast correction</p>
              <h2>Errors by variable and horizon</h2>
              <p>{data.weather.method}</p>
              <div className="public-facts">
                <span>
                  Immutable forecasts
                  <strong>{fmt(data.weather.total, 0)}</strong>
                </span>
                <span>
                  Resolved against observations
                  <strong>{fmt(data.weather.resolved, 0)}</strong>
                </span>
                <span>
                  Awaiting observations
                  <strong>{fmt(data.weather.pending, 0)}</strong>
                </span>
              </div>
              {data.weather.scores.length ? (
                <div className="public-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">Port / variable</th>
                        <th scope="col">Horizon</th>
                        <th scope="col">Raw MAE</th>
                        <th scope="col">Corrected MAE</th>
                        <th scope="col">Raw bias</th>
                        <th scope="col">Corrected bias</th>
                        <th scope="col">Pairs</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.weather.scores.map((s) => (
                        <tr
                          key={`${s.portCode}-${s.variable}-${s.provider}-${s.horizonDays}`}
                        >
                          <th scope="row">
                            {s.portCode} / {s.variable} ({s.unit})
                          </th>
                          <td>{s.horizonDays} days</td>
                          <td>{fmt(s.rawMae, 3)}</td>
                          <td>{fmt(s.correctedMae, 3)}</td>
                          <td>{fmt(s.rawBias, 3)}</td>
                          <td>{fmt(s.correctedBias, 3)}</td>
                          <td>{s.samples}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="public-note">
                  {data.weather.available
                    ? "No resolved public forecast–observation pairs are available. Measured weather improvement cannot yet be reported."
                    : "Weather feedback is unavailable. Historical results and their downloads remain available independently."}
                </p>
              )}
              <p className="public-note">
                {data.weather.note} Correction version: {data.weather.version}.
                Reanalysis remains distinct from station measurements; these
                availability-filtered paired scores are descriptive and are not
                an untouched weather holdout.
              </p>
            </section>
            <section>
              <p className="public-eyebrow">Measured operational outcomes</p>
              <h2>Public port-call collection continues</h2>
              <p>{data.operational.meaning}</p>
              {!data.operational.available && (
                <p className="public-note public-warning" role="status">
                  {data.operational.reason}
                </p>
              )}
              <div className="public-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Port</th>
                      <th scope="col">Frozen ETAs</th>
                      <th scope="col">Matched arrivals</th>
                      <th scope="col">Complete calls</th>
                      <th scope="col">Ambiguous</th>
                      <th scope="col">Pending</th>
                      <th scope="col">Last collection</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.operational.ports.map((p) => (
                      <tr key={p.portCode}>
                        <th scope="row">{p.portCode}</th>
                        <td>{p.frozen}</td>
                        <td>{p.matchedArrivals}</td>
                        <td>{p.complete}</td>
                        <td>{p.ambiguous}</td>
                        <td>{p.pending}</td>
                        <td>
                          {utc(p.lastSuccessfulCollectionAt)}
                          {p.collectionFailed && (
                            <strong className="public-warning">
                              {" "}
                              · Latest run failed
                            </strong>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="public-note">
                Collection counts are not performance scores. Cohort enrollment,
                outcome availability and chronological minimum counts must
                qualify before operational evaluation. JNPA’s verified operator
                workflow remains available separately.
              </p>
            </section>
            <section className="public-limits">
              <h2>Simulations remain separate</h2>
              <p>{data.simulationMeaning}</p>
              <Link to="/explore">
                Inspect distance, speed and cost assumptions →
              </Link>
              <p className="public-note">
                Neural fusion and reinforcement learning remain deferred. No
                measured operational savings are claimed.
              </p>
            </section>
          </div>
        )
      )}
    </PublicShell>
  );
}
