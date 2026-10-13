import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  DEFAULT_SCENARIO,
  usePublicWorkspace,
  usePublicScenario,
  usePublicFeedback,
  type ScenarioInputs,
  type SceneLayer,
  type TimeMode,
  type ScenarioOption,
} from "@/services/public-workspace";
import { fmt, utc } from "./format";
import "./workspace.css";

const Globe = lazy(() => import("@/components/intelligence/IntelligenceGlobe"));
const NO_HEADERS = {};
const INITIAL_LAYERS: Record<SceneLayer, boolean> = {
  events: true,
  routes: true,
  vessels: true,
  weather: false,
  economics: false,
  infrastructure: true,
  cameras: false,
};
type Selection = { kind: "event" | "port" | "vessel"; id: string };
const metric = (o: ScenarioOption, key: string) =>
  o.evaluation?.objectives[key]?.value;

export function PublicWorkspace({ embedded = false }: { embedded?: boolean }) {
  // Establish the real scenario clock after hydration. Independently reading
  // the server and browser clocks can produce different UTC footer text when
  // the initial request crosses a minute boundary.
  const [anchor, setAnchor] = useState<string | null>(null);
  useEffect(() => setAnchor(new Date().toISOString()), []);
  const [mode, setMode] = useState<TimeMode>("current"),
    [hours, setHours] = useState(0);
  const [replayDate, setReplayDate] = useState("2026-10-07T12:00");
  const at =
    mode === "replay"
      ? new Date(replayDate + "Z").toISOString()
      : anchor
        ? new Date(new Date(anchor).getTime() + hours * 3600000).toISOString()
        : "";
  const query = usePublicWorkspace(mode, at),
    data = query.data;
  const [selection, setSelection] = useState<Selection | null>(null),
    [eventId, setEventId] = useState<string | null>(null);
  const [portCode, setPort] = useState("INNSA"),
    [search, setSearch] = useState("");
  const [layers, setLayers] = useState(INITIAL_LAYERS),
    [tab, setTab] = useState<"signals" | "actions" | "learning">("signals");
  const [draft, setDraft] = useState(DEFAULT_SCENARIO),
    [submitted, setSubmitted] = useState<ScenarioInputs | null>(null);
  const [optionId, setOptionId] = useState<string | null>(null),
    [variable, setVariable] = useState("wind_speed");
  const [horizon, setHorizon] = useState(1),
    [mobilePane, setMobilePane] = useState("scene");
  const [resetToken, setResetToken] = useState(0);
  const [signalsOpen, setSignalsOpen] = useState(false);
  const scenario = usePublicScenario(submitted, at),
    feedback = usePublicFeedback(portCode, variable, at);
  const event = data?.events.find((e) => e.eventId === eventId);
  const port = data?.ports.find((p) => p.code === portCode);
  const route = data?.routes.find((r) => r.id === draft.laneCode);
  const options = scenario.data?.options ?? [];
  const selectedOption =
    options.find((o) => o.optionId === optionId) ??
    options.find(
      (o) => o.optionId === scenario.data?.recommendation?.optionId,
    ) ??
    options[0];
  const weather = data?.weather.find((w) => w.portCode === portCode);
  const forecast = port?.forecasts.find((f) => f.day === horizon);
  const affected = useMemo(
    () => event?.ports.map((p) => p.portCode) ?? [],
    [event],
  );
  const scene = useMemo(
    () => ({
      ports: layers.infrastructure ? (data?.ports ?? []) : [],
      news: { events: layers.events ? (data?.events ?? []) : [] },
      cameras: layers.cameras ? (data?.cameras ?? []) : [],
    }),
    [data, layers],
  );
  const sceneRoutes = useMemo(
    () =>
      layers.routes
        ? selectedOption
          ? [
              {
                id: selectedOption.optionId,
                name: selectedOption.label,
                positions: selectedOption.geometry,
                selected: true,
              },
            ]
          : (data?.routes ?? [])
              .filter(
                (r) => !event || event.lanes.some((l) => l.laneCode === r.id),
              )
              .map((r) => ({ ...r, selected: r.id === draft.laneCode }))
        : [],
    [layers.routes, selectedOption, data, event, draft.laneCode],
  );
  const vessels = useMemo(
    () =>
      layers.vessels && scenario.data
        ? [
            {
              id: "scenario",
              name: "Scenario vessel · not observed AIS",
              ...scenario.data.position,
            },
          ]
        : [],
    [layers.vessels, scenario.data],
  );
  const markers = useMemo(
    () => [
      ...(layers.infrastructure
        ? (data?.chokepoints ?? []).map((c) => ({
            ...c,
            kind: "chokepoint" as const,
          }))
        : []),
      ...(layers.weather
        ? (data?.weather ?? []).flatMap((w) => {
            const p = data?.ports.find((p) => p.code === w.portCode);
            return p
              ? [
                  {
                    id: `weather:${w.portCode}`,
                    kind: "weather" as const,
                    portCode: p.code,
                    ...p.location,
                    name: `${p.code}: ${fmt(w.windKnots)} kn wind / ${fmt(w.waveHeightM)} m waves`,
                  },
                ]
              : [];
          })
        : []),
    ],
    [data, layers.infrastructure, layers.weather],
  );
  const focus = useMemo(
    () =>
      selection?.kind === "event"
        ? event?.coordinates
        : selection?.kind === "vessel"
          ? scenario.data?.position
          : selection?.kind === "port"
            ? port?.location
            : null,
    [selection, event, scenario.data, port],
  );
  function selectPort(code: string) {
    setPort(code);
    setSelection({ kind: "port", id: code });
    setMobilePane("inspector");
    setTab("signals");
    const lane = route?.portCodes.includes(code)
      ? route
      : data?.routes.find(
          (r) => r.portCodes.includes(code) && r.chokepoints.length,
        );
    if (lane) {
      setDraft((d) => ({
        ...d,
        laneCode: lane.id,
        portCode: code,
        riskChokepoint: lane.chokepoints.includes(d.riskChokepoint)
          ? d.riskChokepoint
          : lane.chokepoints[0],
      }));
      setSubmitted(null);
    }
  }
  function selectEvent(id: string) {
    const e = data?.events.find((row) => row.eventId === id);
    setEventId(id);
    setSelection({ kind: "event", id });
    setTab("signals");
    setMobilePane("inspector");
    const lane = e?.lanes[0],
      p = lane?.indiaPorts.find((code) =>
        data?.ports.some((row) => row.code === code),
      );
    if (p) setPort(p);
    if (lane && p) {
      const geography = data?.routes.find((r) => r.id === lane.laneCode);
      setDraft((d) => ({
        ...d,
        laneCode: lane.laneCode,
        portCode: p,
        riskChokepoint:
          e?.chokepoints.find((c) => geography?.chokepoints.includes(c)) ??
          geography?.chokepoints[0] ??
          "SUEZ",
      }));
      setSubmitted(null);
    }
  }
  function compare() {
    setSubmitted({ ...draft });
    setOptionId(null);
    setTab("actions");
    setSelection({ kind: "vessel", id: "scenario" });
  }
  const valid =
    Object.values(draft).every(
      (v) => typeof v !== "number" || Number.isFinite(v),
    ) &&
    draft.hoursToRisk >= -48 &&
    draft.hoursToRisk <= 240 &&
    draft.speedKn >= 6 &&
    draft.speedKn <= 24 &&
    draft.closureHours >= 1 &&
    draft.closureHours <= 240 &&
    draft.waveM >= 0 &&
    draft.waveM <= 12 &&
    draft.charterUsdDay > 0 &&
    draft.charterUsdDay <= 1000000 &&
    draft.bunkerUsdTonne > 0 &&
    draft.bunkerUsdTonne <= 10000 &&
    draft.fuelTonnesDay > 0 &&
    draft.fuelTonnesDay <= 1000;
  const field = (
    label: string,
    key: keyof ScenarioInputs,
    min: number,
    max: number,
    step = 1,
  ) => (
    <label>
      {label}
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={Number.isNaN(draft[key]) ? "" : draft[key]}
        onChange={(e) =>
          setDraft((d) => ({ ...d, [key]: e.target.valueAsNumber }))
        }
      />
    </label>
  );
  return (
    <div
      className={`public-workspace ${embedded ? "workspace-embedded" : ""}`}
      data-mobile-pane={mobilePane}
      data-signals-open={signalsOpen}
    >
      <a className="workspace-skip" href="#workspace-inspector">
        Skip to investigation
      </a>
      <header className="workspace-header">
        <Link to="/explore" className="workspace-brand">
          ↗{" "}
          <strong>
            PortWatch <span>X</span>
          </strong>
          <small>Global shipping intelligence</small>
        </Link>
        <nav aria-label="Public navigation">
          <span className="workspace-visitor">Public visitor</span>
          <Link to="/research">Research & evidence ↗</Link>
          <Link to="/login">Operator access</Link>
        </nav>
      </header>
      <div
        className="workspace-mobile-tabs"
        role="group"
        aria-label="Workspace panels"
      >
        {["scene", "signals", "inspector"].map((p) => (
          <button
            key={p}
            aria-pressed={mobilePane === p}
            onClick={() => setMobilePane(p)}
          >
            {p === "scene"
              ? "Globe"
              : p === "signals"
                ? "Signals & layers"
                : "Investigation"}
          </button>
        ))}
      </div>
      <div className="workspace-body">
        <button
          className="workspace-signals-toggle"
          aria-expanded={signalsOpen}
          onClick={() => setSignalsOpen((o) => !o)}
        >
          Signals & layers {signalsOpen ? "−" : "+"}
        </button>
        <aside className="workspace-rail" aria-label="Signals and layers">
          <div className="workspace-rail-title">
            <small>01 / Observe</small>
            <h1>Investigate the world.</h1>
            <p>
              Select a report. Follow the exposed route. Compare a shipping
              choice.
            </p>
          </div>
          <label className="workspace-search">
            Find a signal or port
            <input
              type="search"
              placeholder="Red Sea, Chennai, energy…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <section className="workspace-layers">
            <h2>Scene layers</h2>
            {data?.layers.map((l) => (
              <div key={l.id}>
                <label>
                  <input
                    type="checkbox"
                    aria-label={l.label}
                    checked={layers[l.id]}
                    onChange={(e) =>
                      setLayers((s) => ({ ...s, [l.id]: e.target.checked }))
                    }
                  />
                  <span>{l.label}</span>
                  <small>{l.status.replaceAll("_", " ")}</small>
                </label>
                <details>
                  <summary>Coverage</summary>
                  <p>{l.coverage}</p>
                </details>
              </div>
            ))}
          </section>
          <section className="workspace-alerts">
            <h2>
              Reported signals <span>{data?.events.length ?? "—"}</span>
            </h2>
            {data?.events
              .filter((e) =>
                (e.title + e.region + e.categoryLabel)
                  .toLowerCase()
                  .includes(search.toLowerCase()),
              )
              .map((e) => (
                <button
                  key={e.eventId}
                  className={e.eventId === eventId ? "selected" : ""}
                  onClick={() => selectEvent(e.eventId)}
                >
                  <small>
                    {e.categoryLabel} · {e.status.toLowerCase()}
                  </small>
                  <strong>{e.title}</strong>
                  <span>
                    {e.lanes.length} lanes · {e.ports.length} ports ·{" "}
                    {utc(e.lastSeen)}
                  </span>
                </button>
              ))}
            {data && !data.events.length ? (
              <p>
                No reports available at this time. Use the explicitly assumed
                shipping scenario below.
              </p>
            ) : null}
          </section>
          <section className="workspace-port-list">
            <h2>Port catalogue</h2>
            {data?.ports
              .filter((p) =>
                (p.name + p.code).toLowerCase().includes(search.toLowerCase()),
              )
              .map((p) => (
                <button
                  key={p.code}
                  onClick={() => selectPort(p.code)}
                  aria-pressed={p.code === portCode}
                >
                  {p.name}
                  <small>{p.code}</small>
                </button>
              ))}
          </section>
        </aside>
        <main
          className="workspace-scene"
          aria-label="Interactive global shipping scene"
        >
          <div className="workspace-scene-heading">
            <small>One scene · shared selection · visitor-local time</small>
            <h2>{event?.region ?? "Indian Ocean & global trade"}</h2>
            <p>
              {event
                ? event.title
                : "Public signals, route geography and isolated decisions"}
            </p>
          </div>
          {data || query.isError ? (
            <Suspense
              fallback={
                <div className="workspace-loading" role="status">
                  Preparing globe…
                </div>
              }
            >
              <Globe
                context={scene}
                portCode={portCode}
                eventId={eventId}
                earthquakes={false}
                headers={NO_HEADERS}
                onPort={selectPort}
                onEvent={selectEvent}
                routes={sceneRoutes}
                markers={markers}
                vessels={vessels}
                affectedPorts={affected}
                focus={focus}
                resetToken={resetToken}
                fitSelectionKey={`${selection?.kind ?? "world"}:${selection?.id ?? "initial"}:${selectedOption?.optionId ?? draft.laneCode}`}
                onVessel={() => {
                  setSelection({ kind: "vessel", id: "scenario" });
                  setTab("actions");
                  setMobilePane("inspector");
                }}
              />
            </Suspense>
          ) : (
            <div className="workspace-loading" role="status">
              Loading public signals…
            </div>
          )}
          {query.isError ? (
            <div className="workspace-source-error" role="alert">
              Public signals unavailable. Geography and assumed comparisons
              remain available.{" "}
              <button onClick={() => void query.refetch()}>
                Retry sources
              </button>
            </div>
          ) : null}
          <div className="workspace-scene-legend">
            <span>
              <i />
              Ports
            </span>
            <span>
              <i className="amber" />
              Reported events / selected route
            </span>
            <span>
              Simulated vessel {vessels.length ? "visible" : "not active"}
            </span>
          </div>
          <div className="workspace-scene-actions">
            <button
              onClick={() => {
                setSubmitted({ ...DEFAULT_SCENARIO });
                setDraft({ ...DEFAULT_SCENARIO });
                setPort("INNSA");
                setEventId(null);
                setTab("actions");
                setSelection({ kind: "vessel", id: "scenario" });
                setMobilePane("inspector");
              }}
            >
              Try a shipping scenario ↗
            </button>
            <p>Drag to rotate · scroll to zoom · click a marker</p>
          </div>
          <button
            className="workspace-reset"
            onClick={() => {
              setSelection(null);
              setResetToken((n) => n + 1);
            }}
          >
            Reset globe ↻
          </button>
          <section
            className="workspace-time"
            aria-label="Visitor time controls"
          >
            <label>
              Time view
              <select
                aria-label="Time view"
                value={mode}
                onChange={(e) => setMode(e.target.value as TimeMode)}
              >
                <option value="current">Current evidence</option>
                <option value="replay">Historical availability</option>
                <option value="projection">
                  Forecast / scenario projection
                </option>
              </select>
            </label>
            {mode === "replay" ? (
              <label>
                Replay cutoff (UTC)
                <input
                  type="datetime-local"
                  value={replayDate}
                  onChange={(e) =>
                    e.target.value && setReplayDate(e.target.value)
                  }
                />
              </label>
            ) : mode === "projection" ? (
              <label>
                Project ahead: {hours} h
                <input
                  type="range"
                  min="0"
                  max="72"
                  step="6"
                  value={hours}
                  onChange={(e) => setHours(+e.target.value)}
                />
              </label>
            ) : (
              <span>{utc(data?.collectedAt ?? anchor)}</span>
            )}
            <p>
              {mode === "replay"
                ? "Unavailable publication vintages are withheld. No current camera feeds."
                : mode === "projection"
                  ? "Known inputs projected forward; no future observations are inferred."
                  : "Dated evidence; stale snapshots stay labelled."}
            </p>
          </section>
        </main>
        <aside
          id="workspace-inspector"
          className="workspace-inspector"
          aria-label="Shipping investigation"
        >
          <div className="workspace-inspector-heading">
            <small>02 / Understand → decide</small>
            <h2>
              {selection?.kind === "event"
                ? "Reported disruption"
                : selection?.kind === "vessel"
                  ? "Scenario vessel"
                  : (port?.name ?? "Select an asset")}
            </h2>
            <p>
              {port?.code} ·{" "}
              {event
                ? "Linked to selected report"
                : "Public scenario and port context"}
            </p>
          </div>
          <div
            className="workspace-inspector-tabs"
            role="tablist"
            aria-label="Investigation view"
          >
            {(["signals", "actions", "learning"] as const).map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
              >
                {t === "signals"
                  ? "Evidence"
                  : t === "actions"
                    ? "Compare actions"
                    : "Learning"}
              </button>
            ))}
          </div>
          <div className="workspace-inspector-content">
            {tab === "signals" ? (
              <>
                {event ? (
                  <section className="workspace-section">
                    <h3>{event.title}</h3>
                    <p>
                      {event.categoryLabel} · {event.region}
                    </p>
                    <p>
                      Published / last reported {utc(event.lastSeen)}
                      <br />
                      Available in this cache {utc(event.availableAt)}
                    </p>
                    <small>{event.confidenceMeaning}</small>
                    <div className="workspace-source-links">
                      {event.sources
                        .filter((s) => s.url)
                        .map((s, i) => (
                          <a
                            key={i}
                            href={s.url!}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {s.outlet ?? "Source report"} ↗
                          </a>
                        ))}
                    </div>
                    <h4>Affected assets</h4>
                    {event.ports.map((p) => (
                      <button
                        className="workspace-asset"
                        key={p.portCode}
                        onClick={() => selectPort(p.portCode)}
                      >
                        {p.portName}
                        <span>{p.portCode} ↗</span>
                      </button>
                    ))}
                    <label>
                      Investigate route
                      <select
                        aria-label="Investigate route"
                        value={draft.laneCode}
                        onChange={(e) => {
                          const r = data?.routes.find(
                            (r) => r.id === e.target.value,
                          );
                          if (r) {
                            const p =
                              r.portCodes.find((c) =>
                                data?.ports.some((p) => p.code === c),
                              ) ?? "INNSA";
                            setDraft((d) => ({
                              ...d,
                              laneCode: r.id,
                              riskChokepoint:
                                event?.chokepoints.find((c) =>
                                  r.chokepoints.includes(c),
                                ) ?? r.chokepoints[0],
                              portCode: p,
                            }));
                            setPort(p);
                            setSubmitted(null);
                          }
                        }}
                      >
                        {data?.routes
                          .filter((r) =>
                            event.lanes.some((l) => l.laneCode === r.id),
                          )
                          .map((r) => (
                            <option key={r.id} value={r.id}>
                              {r.name}
                            </option>
                          ))}
                      </select>
                    </label>
                    <p>
                      Exposure follows catalogue relationships. A report alone
                      does not establish caused delay.
                    </p>
                  </section>
                ) : (
                  <section className="workspace-section">
                    <p>
                      Choose a source-backed report in the left rail, or start a
                      scenario to explore a possible restriction.
                    </p>
                  </section>
                )}
                <section className="workspace-section">
                  <h3>Port forecast · {port?.name}</h3>
                  <label>
                    Forecast horizon
                    <select
                      aria-label="Forecast horizon"
                      value={horizon}
                      onChange={(e) => setHorizon(+e.target.value)}
                    >
                      {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                        <option key={n} value={n}>
                          Day {n}
                        </option>
                      ))}
                    </select>
                  </label>
                  {forecast ? (
                    <>
                      <div className="workspace-big-number">
                        {fmt(forecast.q50)}
                        <small>/ 100 congestion proxy</small>
                      </div>
                      <p>
                        Nominal 80% interval {fmt(forecast.q10)}–
                        {fmt(forecast.q90)}
                      </p>
                      <p>
                        Origin {utc(forecast.originDate)}
                        <br />
                        Target {utc(forecast.targetDate)}
                      </p>
                      <p className="workspace-warning">
                        {forecast.status === "STALE"
                          ? "Stale forecast snapshot. "
                          : "Cached model forecast. "}
                        This is not a confirmed anchorage-wait estimate.
                      </p>
                      <Link to="/research">
                        Model performance & calibration ↗
                      </Link>
                    </>
                  ) : (
                    <p>
                      No forecast available for this port, horizon and evidence
                      time.
                    </p>
                  )}
                </section>
                <section className="workspace-section">
                  <h3>Weather at the port</h3>
                  {weather ? (
                    <>
                      <p>
                        Wind {fmt(weather.windKnots)} kn · gust{" "}
                        {fmt(weather.gustKnots)} kn
                        <br />
                        Waves {fmt(weather.waveHeightM)} m · rain{" "}
                        {fmt(weather.rainfallMm24h)} mm
                      </p>
                      <small>
                        {weather.status} · {utc(weather.observedAt)} ·{" "}
                        {weather.dataSource}
                      </small>
                      <p>Snapshot available {utc(weather.availableAt)}</p>
                      <p>{weather.timestampMeaning}</p>
                    </>
                  ) : (
                    <p>
                      No dated public weather snapshot is available at this
                      time.
                    </p>
                  )}
                </section>
                {layers.economics ? (
                  <section className="workspace-section">
                    <h3>Economic context</h3>
                    {data?.economics.map((e) => (
                      <p key={e.id}>
                        <a href={e.source} target="_blank" rel="noreferrer">
                          {e.label} ↗
                        </a>{" "}
                        {fmt(e.value)} {e.unit}
                        <br />
                        <small>
                          {e.status} · {utc(e.observedAt)}
                        </small>
                        <br />
                        {e.shippingConnection}
                      </p>
                    ))}
                    <p>
                      Scenario bunker/charter assumptions remain distinct from
                      these market series.
                    </p>
                  </section>
                ) : null}
                {layers.cameras ? (
                  <section className="workspace-section">
                    <h3>Public viewpoints</h3>
                    {data?.cameras
                      .filter((c) => c.portCode === portCode)
                      .map((c) => (
                        <p key={c.id}>
                          <a href={c.mediaUrl} target="_blank" rel="noreferrer">
                            {c.name} ↗
                          </a>
                          <br />
                          {c.coverage}
                          <br />
                          {c.health} · frame {utc(c.lastFrameAt)}
                          <br />
                          {c.healthNote}
                        </p>
                      ))}
                    {!data?.cameras.some((c) => c.portCode === portCode) ? (
                      <p>
                        No authorized public camera is connected at this port.
                        Historical views withhold current streams.
                      </p>
                    ) : null}
                  </section>
                ) : null}
                <section className="workspace-section">
                  <h3>Choose an action to investigate</h3>
                  <p>
                    Compare the existing plan with constrained alternatives
                    under explicit closure, weather and cost assumptions.
                  </p>
                  <button
                    className="workspace-primary"
                    onClick={() => setTab("actions")}
                  >
                    Configure shipping scenario →
                  </button>
                  <Link to="/research" hash="public-port-cases">
                    Reported outcomes & archived evidence ↗
                  </Link>
                </section>
              </>
            ) : tab === "actions" ? (
              <>
                <section className="workspace-section">
                  <h3>Isolated shipping scenario</h3>
                  <p className="workspace-simulation">
                    Simulation · vessel position, closure and seas are assumed.
                  </p>
                  {event ? (
                    <p>
                      Report context: {event.title}. The selected lane and
                      restriction location follow catalogue exposure; duration
                      and sea conditions remain visitor assumptions.
                    </p>
                  ) : null}
                  <label>
                    Shipping lane
                    <select
                      aria-label="Shipping lane"
                      value={draft.laneCode}
                      onChange={(e) => {
                        const r = data?.routes.find(
                          (r) => r.id === e.target.value,
                        );
                        if (r) {
                          const p =
                            r.portCodes.find((c) =>
                              data?.ports.some((p) => p.code === c),
                            ) ?? "INNSA";
                          setDraft((d) => ({
                            ...d,
                            laneCode: r.id,
                            riskChokepoint: r.chokepoints[0],
                            portCode: p,
                          }));
                          setPort(p);
                          setSubmitted(null);
                        }
                      }}
                    >
                      {data?.routes
                        .filter((r) => r.chokepoints.length)
                        .map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.name}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Destination port
                    <select
                      aria-label="Destination port"
                      value={draft.portCode}
                      onChange={(e) => {
                        setDraft((d) => ({ ...d, portCode: e.target.value }));
                        setPort(e.target.value);
                      }}
                    >
                      {data?.ports
                        .filter((p) => route?.portCodes.includes(p.code))
                        .map((p) => (
                          <option key={p.code} value={p.code}>
                            {p.name}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Restriction at
                    <select
                      aria-label="Restriction at"
                      value={draft.riskChokepoint}
                      onChange={(e) =>
                        setDraft((d) => ({
                          ...d,
                          riskChokepoint: e.target.value,
                        }))
                      }
                    >
                      {route?.chokepoints.map((c) => (
                        <option key={c} value={c}>
                          {data?.chokepoints.find((p) => p.id === c)?.name ?? c}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="workspace-fields">
                    {field("Hours before chokepoint", "hoursToRisk", -48, 240)}
                    {field("Service speed (kn)", "speedKn", 6, 24, 0.5)}
                    {field("Restriction duration (h)", "closureHours", 1, 240)}
                    {field("Assumed wave height (m)", "waveM", 0, 12, 0.5)}
                    {field(
                      "Charter (USD/day)",
                      "charterUsdDay",
                      1,
                      1000000,
                      1000,
                    )}
                    {field(
                      "Bunker (USD/tonne)",
                      "bunkerUsdTonne",
                      1,
                      10000,
                      25,
                    )}
                    {field(
                      "Fuel at service speed (t/day)",
                      "fuelTonnesDay",
                      1,
                      1000,
                      5,
                    )}
                  </div>
                  <button
                    className="workspace-primary"
                    disabled={!valid || scenario.isFetching}
                    onClick={compare}
                  >
                    {scenario.isFetching
                      ? "Evaluating branches…"
                      : "Compare shipping actions"}
                  </button>
                  {!valid ? (
                    <p role="alert">
                      Enter finite values within the displayed ranges.
                    </p>
                  ) : null}
                  <p>
                    Changing inputs creates a new comparison only when you run
                    it. Current results retain their submitted assumptions.
                  </p>
                </section>
                {scenario.isError ? (
                  <section className="workspace-section" role="alert">
                    Comparison unavailable: {scenario.error.message}
                  </section>
                ) : null}
                {scenario.data ? (
                  <>
                    <section className="workspace-section">
                      <h3>Compared options</h3>
                      <p>
                        Scenario vessel · no observed AIS identity.
                        <br />
                        Simulated position {fmt(
                          scenario.data.position.lat,
                        )}°, {fmt(scenario.data.position.lon)}° at{" "}
                        {utc(scenario.data.at)}.
                      </p>
                      <p>{scenario.data.doNothingStatement}</p>
                      <div className="workspace-option-list">
                        {options.map((o) => (
                          <button
                            key={o.optionId}
                            className={
                              o.optionId === selectedOption?.optionId
                                ? "selected"
                                : ""
                            }
                            onClick={() => {
                              setOptionId(o.optionId);
                              setSelection({ kind: "vessel", id: "scenario" });
                            }}
                          >
                            <strong>{o.label}</strong>
                            <small>
                              {o.isBaseline ? "Baseline · " : ""}
                              {o.status.toLowerCase().replaceAll("_", " ")}
                            </small>
                            <span>
                              {o.feasible
                                ? `${fmt(metric(o, "eta"))} h ETA shift · fuel ${fmt(metric(o, "fuel"))}×`
                                : o.rejectedBy.map((r) => r.label).join(", ")}
                            </span>
                          </button>
                        ))}
                      </div>
                    </section>
                    <section className="workspace-section">
                      <h3>{selectedOption?.label}</h3>
                      <dl className="workspace-metrics">
                        {[
                          "eta",
                          "distance",
                          "risk",
                          "fuel",
                          "weather",
                          "yard_pressure",
                          "cost",
                        ].map((k) => {
                          const m = selectedOption?.evaluation?.objectives[k];
                          return (
                            <div key={k}>
                              <dt>{k.replaceAll("_", " ")}</dt>
                              <dd>
                                {m?.available
                                  ? `${fmt(m.value)} ${m.unit}`
                                  : "Unavailable"}
                              </dd>
                              {!m?.available && m?.unknownBecause ? (
                                <small>{m.unknownBecause}</small>
                              ) : null}
                            </div>
                          );
                        })}
                      </dl>
                      <h4>Cost under submitted assumptions</h4>
                      {selectedOption?.evaluation?.financial.components.map(
                        (c) => (
                          <p key={c.key}>
                            <strong>{c.label}</strong>:{" "}
                            {c.money
                              ? `${fmt(c.money.amount)} ${c.money.currency}`
                              : c.state === "ZERO"
                                ? "0 USD"
                                : "Unavailable"}
                            <br />
                            <small>
                              {c.isAssumption
                                ? "Visitor price assumption · "
                                : ""}
                              {c.reason}
                            </small>
                          </p>
                        ),
                      )}
                      <p className="workspace-warning">
                        {selectedOption?.evaluation?.financial.complete
                          ? "Complete modelled cost."
                          : "Partial cost only. Unknown cargo and port charges prevent a total-cost or savings claim."}
                      </p>
                      <details>
                        <summary>Constraints, inputs & uncertainty</summary>
                        {selectedOption?.constraints.map((c, i) => (
                          <p key={i}>
                            {c.passed ? "Pass" : "Fail"}: {c.label} · {c.detail}
                          </p>
                        ))}
                        <p>{scenario.data.uncertainty}</p>
                        <p>{scenario.data.forecastConnection}</p>
                        <p>
                          Submitted: {submitted?.riskChokepoint} ·{" "}
                          {submitted?.speedKn} kn · {submitted?.closureHours} h
                          restriction · {submitted?.waveM} m sea ·{" "}
                          {submitted?.charterUsdDay} USD/day.
                        </p>
                      </details>
                    </section>
                    <section className="workspace-section">
                      <h3>Engine recommendation</h3>
                      <p>
                        {scenario.data.recommendation?.statement ??
                          "No feasible recommendation. Inspect the failed constraints."}
                      </p>
                      <p>{scenario.data.recommendation?.why}</p>
                      <small>
                        Robustness, frontier and Critic applied. Duration
                        confidence is uncalibrated.
                      </small>
                      <details>
                        <summary>
                          Unavailable actions and ranking limits
                        </summary>
                        {scenario.data.availableActions
                          .filter((a) => a.availability.status !== "AVAILABLE")
                          .map((a, i) => (
                            <p key={i}>
                              {a.label ?? a.kind}: {a.availability.reason}
                            </p>
                          ))}
                        {Object.entries(
                          scenario.data.recommendation?.rankingBasis
                            .objectivesDropped ?? {},
                        ).map(([k, v]) => (
                          <p key={k}>
                            {k}: {v}
                          </p>
                        ))}
                      </details>
                      <p>
                        Observed outcome: unavailable for this simulated vessel.
                        No approval or operational action is issued.
                      </p>
                    </section>
                  </>
                ) : null}
              </>
            ) : (
              <>
                <section className="workspace-section">
                  <h3>Weather learns from observations</h3>
                  <label>
                    Weather variable
                    <select
                      aria-label="Weather variable"
                      value={variable}
                      onChange={(e) => setVariable(e.target.value)}
                    >
                      {[
                        ["wind_speed", "Wind speed"],
                        ["wind_gust", "Wind gust"],
                        ["rainfall", "Rainfall"],
                        ["wave_height", "Wave height"],
                        ["visibility", "Visibility"],
                      ].map(([v, l]) => (
                        <option key={v} value={v}>
                          {l}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p>
                    Original forecast → later observation → residual →
                    supervised correction.
                  </p>
                  {feedback.isPending ? (
                    <p role="status">Loading retained forecasts…</p>
                  ) : feedback.isError ? (
                    <p role="alert">Public forecast feedback unavailable.</p>
                  ) : feedback.data?.forecasts.length ? (
                    <>
                      {feedback.data.forecasts.map((f) => (
                        <article key={f.id} className="workspace-feedback">
                          <h4>
                            {f.targetDate} · day {f.horizonDays}
                          </h4>
                          <dl>
                            <dt>Original</dt>
                            <dd>
                              {fmt(f.original)} {f.unit}
                            </dd>
                            <dt>Observation</dt>
                            <dd>
                              {fmt(f.observed)} {f.unit}
                            </dd>
                            <dt>Residual (observed − original)</dt>
                            <dd>
                              {f.observed === null
                                ? "Pending"
                                : fmt(f.observed - f.original)}
                            </dd>
                            <dt>Retained correction</dt>
                            <dd>
                              {fmt(f.corrected)} {f.unit} ·{" "}
                              {f.correction.status ?? "not fitted"}
                            </dd>
                          </dl>
                          <small>
                            Issued {utc(f.issuedAt)} ·{" "}
                            {f.observationSource ??
                              "Awaiting an available observation"}
                          </small>
                        </article>
                      ))}
                      <p>{feedback.data.note}</p>
                    </>
                  ) : (
                    <p>
                      No retained public forecast pairs are available for this
                      port and variable. A newer forecast cannot serve as an
                      observation.
                    </p>
                  )}
                </section>
                <section className="workspace-section">
                  <h3>Research programme</h3>
                  <p>
                    Learned fusion, constrained RL and revised interval
                    calibration are separate experiments to build and evaluate.
                    They are not active policies in this workspace iteration.
                  </p>
                  <Link to="/research">
                    Benchmarks, assumptions and reproducible results ↗
                  </Link>
                </section>
              </>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
