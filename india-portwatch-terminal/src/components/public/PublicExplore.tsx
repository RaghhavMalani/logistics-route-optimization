import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { usePublicExplore } from "@/services/public-research";
import { DataState, LinePlot, PublicShell } from "./PublicShell";
import { fmt, utc } from "./format";
import { PublicPortCases } from "./PublicPortCases";

export function PublicExplore() {
  const query = usePublicExplore();
  const [eventId, setEventId] = useState<string | null>(null),
    [portCode, setPortCode] = useState<string | null>(null),
    [horizon, setHorizon] = useState(1),
    [search, setSearch] = useState(""),
    [speed, setSpeed] = useState(16),
    [dailyCost, setDailyCost] = useState(30000);
  const data = query.data,
    event = data?.events.find((e) => e.eventId === eventId) ?? data?.events[0];
  const port =
    data?.ports.find(
      (p) => p.code === (portCode ?? event?.ports[0]?.portCode),
    ) ?? data?.ports[0];
  const forecast = port?.forecasts.find((f) => f.day === horizon),
    lane =
      event?.lanes.find((l) => l.indiaPorts.includes(port?.code ?? "")) ??
      event?.lanes[0];
  const validInputs =
    Number.isFinite(speed) &&
    speed >= 10 &&
    speed <= 22 &&
    Number.isFinite(dailyCost) &&
    dailyCost >= 0 &&
    dailyCost <= 1000000;
  const detour =
    validInputs && lane?.detourNm != null ? lane.detourNm / speed : null;
  const linked = event?.ports.some((p) => p.portCode === port?.code);
  return (
    <PublicShell section="explore">
      <section className="public-hero">
        <div>
          <p className="public-eyebrow">Explore without an account</p>
          <h1>
            Follow a disruption
            <br />
            from report to route.
          </h1>
          <p>
            Trace sourced events, exposed ports and model forecasts. Compare
            possible shipping actions with their assumptions in view.
          </p>
        </div>
        <aside className="public-hero-aside">
          <strong>13 Indian ports</strong>
          <span>Read-only research preview</span>
          <Link to="/research">How well do the forecasts perform? ↗</Link>
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
          <>
            <ol className="public-journey" aria-label="Evidence journey">
              {[
                "Global event",
                "Affected ports",
                "Forecast",
                "Shipping consequence",
                "Alternative actions",
              ].map((s, i) => (
                <li key={s}>
                  <span>0{i + 1}</span>
                  {s}
                </li>
              ))}
            </ol>
            <div className="public-explore-grid">
              <aside className="public-events">
                <div className="public-section-title">
                  <h2>Global reports</h2>
                  <span>{data.events.length} sourced events</span>
                </div>
                <label className="public-search">
                  Find an event
                  <input
                    type="search"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Region, category or report"
                  />
                </label>
                <div className="public-event-list">
                  {data.events
                    .filter((e) =>
                      `${e.title} ${e.region} ${e.categoryLabel}`
                        .toLowerCase()
                        .includes(search.toLowerCase()),
                    )
                    .map((e) => (
                      <button
                        type="button"
                        className={
                          event?.eventId === e.eventId ? "selected" : ""
                        }
                        key={e.eventId}
                        aria-pressed={event?.eventId === e.eventId}
                        onClick={() => {
                          setEventId(e.eventId);
                          setPortCode(null);
                        }}
                      >
                        <small>
                          {e.categoryLabel} · {e.status.toLowerCase()}
                        </small>
                        <strong>{e.title}</strong>
                        <span>
                          {e.region || "Location not established"} ·{" "}
                          {e.ports.length} linked ports
                        </span>
                      </button>
                    ))}
                </div>
                {!data.events.length && (
                  <p className="public-note">
                    {data.eventReason ??
                      "No sourced event is currently available. Port forecasts remain separately explorable."}
                  </p>
                )}
              </aside>
              <article className="public-story">
                <section className="public-evidence">
                  <p className="public-eyebrow">01 / Source evidence</p>
                  <h2>{event?.title ?? "Port evidence"}</h2>
                  {event ? (
                    <>
                      <div className="public-facts">
                        <span>
                          First reported <strong>{utc(event.firstSeen)}</strong>
                        </span>
                        <span>
                          Latest report <strong>{utc(event.lastSeen)}</strong>
                        </span>
                        <span>
                          Corroboration score{" "}
                          <strong>{fmt(event.confidence, 2)} / 1</strong>
                        </span>
                      </div>
                      <p className="public-note">{event.confidenceMeaning}</p>
                      <div className="public-source-links">
                        {event.sources
                          .filter((s) => s.url)
                          .map((s, i) => (
                            <a
                              key={i}
                              href={s.url!}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {s.outlet || `Source ${i + 1}`} ↗
                            </a>
                          ))}
                      </div>
                    </>
                  ) : (
                    <p className="public-note">
                      An event-to-port attribution is unavailable without
                      sourced event evidence.
                    </p>
                  )}
                </section>
                <section>
                  <div className="public-section-title">
                    <div>
                      <p className="public-eyebrow">02 / Affected ports</p>
                      <h2>Choose a port</h2>
                    </div>
                    <label>
                      Port
                      <select
                        aria-label="Port"
                        value={port?.code ?? ""}
                        onChange={(e) => setPortCode(e.target.value)}
                      >
                        {data.ports.map((p) => (
                          <option key={p.code} value={p.code}>
                            {p.name} · {p.code}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="public-port-links">
                    {event?.ports.map((p) => (
                      <button
                        type="button"
                        key={p.portCode}
                        aria-pressed={p.portCode === port?.code}
                        onClick={() => setPortCode(p.portCode)}
                      >
                        {p.portName}
                        <span>Exposure score {fmt(p.exposure, 2)}</span>
                      </button>
                    ))}
                  </div>
                  <p className="public-note">
                    {linked
                      ? "Linked through the trade-lane catalogue. Exposure is not a measured arrival delay."
                      : "This port is not linked to the selected event. Its forecast is shown independently."}
                  </p>
                </section>
                <section className="public-forecast">
                  <div className="public-section-title">
                    <div>
                      <p className="public-eyebrow">
                        03 / Forecast with uncertainty
                      </p>
                      <h2>{port?.name}</h2>
                    </div>
                    <label>
                      Forecast horizon
                      <select
                        aria-label="Forecast horizon"
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
                  {forecast ? (
                    <>
                      <div className="public-prediction">
                        <div>
                          <strong>{fmt(forecast.q50)}</strong>
                          <span>Congestion-index proxy / 100</span>
                        </div>
                        <dl>
                          <dt>Nominal 80% model interval</dt>
                          <dd>
                            {fmt(forecast.q10)} – {fmt(forecast.q90)}
                          </dd>
                          <dt>Forecast origin</dt>
                          <dd>{utc(forecast.originDate)}</dd>
                          <dt>Target</dt>
                          <dd>{utc(forecast.targetDate)}</dd>
                          <dt>Snapshot status</dt>
                          <dd
                            className={
                              forecast.status === "STALE"
                                ? "public-warning"
                                : ""
                            }
                          >
                            {forecast.status.toLowerCase()} ·{" "}
                            {forecast.source ?? "Model unavailable"}
                          </dd>
                          <dt>Modelled delay proxy</dt>
                          <dd>{fmt(forecast.delayHoursP50)} h · unconfirmed</dd>
                        </dl>
                      </div>
                      {forecast.status === "STALE" && (
                        <p className="public-note public-warning">
                          This is an old forecast snapshot. Check its origin and
                          target before using it; it is not a current arrival
                          forecast.
                        </p>
                      )}
                      <LinePlot
                        title={`${port?.name} forecast across horizons; congestion-index proxy`}
                        labels={port?.forecasts.map((f) => `D${f.day}`) ?? []}
                        lines={[
                          {
                            name: "Median",
                            values: port?.forecasts.map((f) => f.q50) ?? [],
                            color: "#235d50",
                          },
                          {
                            name: "10th quantile",
                            values: port?.forecasts.map((f) => f.q10) ?? [],
                            color: "#839f96",
                          },
                          {
                            name: "90th quantile",
                            values: port?.forecasts.map((f) => f.q90) ?? [],
                            color: "#839f96",
                          },
                        ]}
                      />
                      <p className="public-note">
                        {port?.delayMeaning} Interval coverage is evaluated
                        historically on the{" "}
                        <Link to="/research">research page</Link>.
                      </p>
                    </>
                  ) : (
                    <p className="public-note">
                      No forecast snapshot is available for this port and
                      horizon.
                    </p>
                  )}
                </section>
                <section className="public-consequences">
                  <p className="public-eyebrow">
                    04–05 / Shipping consequences and alternatives
                  </p>
                  <h2>Compare a route scenario</h2>
                  <p>
                    {lane
                      ? `${lane.laneName}. Catalogue alternative: ${lane.alternative ?? "unavailable"}.`
                      : "No exposed route with an alternative is available for this event."}
                  </p>
                  <div className="public-assumptions">
                    <label>
                      Assumed service speed (kn)
                      <input
                        aria-label="Assumed service speed (kn)"
                        type="number"
                        min="10"
                        max="22"
                        step="1"
                        value={Number.isNaN(speed) ? "" : speed}
                        onChange={(e) =>
                          setSpeed(
                            e.target.value === ""
                              ? NaN
                              : Number(e.target.value),
                          )
                        }
                      />
                    </label>
                    <label>
                      Assumed operating cost (USD/day)
                      <input
                        type="number"
                        min="0"
                        max="1000000"
                        step="1000"
                        value={Number.isNaN(dailyCost) ? "" : dailyCost}
                        onChange={(e) =>
                          setDailyCost(
                            e.target.value === ""
                              ? NaN
                              : Number(e.target.value),
                          )
                        }
                      />
                    </label>
                  </div>
                  {!validInputs && (
                    <p role="alert">
                      Use a speed from 10–22 kn and a cost from USD
                      0–1,000,000/day.
                    </p>
                  )}
                  <div className="public-action-comparison">
                    <article>
                      <small>Keep the current route</small>
                      <h3>Monitor and coordinate</h3>
                      <p>
                        Confirm restrictions with the carrier and destination
                        port. Event-caused waiting time and cost are
                        unavailable.
                      </p>
                    </article>
                    <article>
                      <small>Catalogue diversion scenario</small>
                      <h3>{lane?.alternative ?? "No alternative recorded"}</h3>
                      <p className="public-scenario-value">
                        {fmt(detour)} <span>extra passage hours</span>
                      </p>
                      <p>
                        Extra distance: {fmt(lane?.detourNm, 0)} nm. Assumed
                        additional operating cost:{" "}
                        {detour == null
                          ? "unavailable"
                          : `USD ${fmt((detour / 24) * dailyCost, 0)}`}
                        .
                      </p>
                      {lane?.detourNm != null && (
                        <p>
                          Speed sensitivity: {fmt(lane.detourNm / 22)}–
                          {fmt(lane.detourNm / 10)} h at 22–10 kn. This is an
                          assumption range, not a confidence interval.
                        </p>
                      )}
                    </article>
                  </div>
                  <p className="public-note">{data.simulation.meaning}</p>
                </section>
                <section className="public-limits">
                  <h3>What this chain establishes</h3>
                  <p>{data.limits}</p>
                  <p>
                    Data view assembled {utc(data.asOf)}. Source collection
                    times and forecast origins are shown separately.
                  </p>
                  <div className="public-source-links">
                    {data.sources.map((s) => (
                      <span className="public-source-detail" key={s.name}>
                        <a href={s.url} target="_blank" rel="noreferrer">
                          {s.name} ↗
                        </a>
                        <small>
                          {s.status.toLowerCase()} · collected{" "}
                          {utc(s.collectedAt)}
                        </small>
                        <small>Source observation {utc(s.observedAt)}</small>
                      </span>
                    ))}
                  </div>
                </section>
              </article>
            </div>
          </>
        )
      )}
    </PublicShell>
  );
}
