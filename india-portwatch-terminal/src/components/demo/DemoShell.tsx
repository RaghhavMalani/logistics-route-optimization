import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { ROLE_PROFILE, type Role } from "@/auth/types";
import { getJson, postJson } from "@/services/api";
import type { DemoWorkspaceData, DemoAdvisory } from "@/services/demo";
import type { ScenarioOption } from "@/services/public-workspace";
import type { TwinSelection } from "@/components/twin/PortTwinScene";
import "./demo.css";
import "@/components/intelligence/intelligence.css";
const Globe = lazy(() => import("@/components/intelligence/IntelligenceGlobe"));
const Twin = lazy(() => import("@/components/twin/PortTwinScene"));
const NO_HEADERS = {};
const ROLE_NAMES: Record<Role, string> = {
  SHIPPING_COMPANY: "Company",
  VESSEL_OPERATOR: "Vessel",
  PORT_AUTHORITY: "Port",
  NATIONAL_ADMIN: "Admin",
};
const titles: Record<Role, string> = {
  SHIPPING_COMPANY: "Fleet intervention desk",
  VESSEL_OPERATOR: "Bridge & voyage",
  PORT_AUTHORITY: "JNPA planning desk",
  NATIONAL_ADMIN: "Network & model oversight",
};
const number = (v: number | null | undefined, digits = 1) =>
  v == null ? "Unavailable" : v.toFixed(digits);
const clock = (v: string) =>
  new Date(v)
    .toISOString()
    .replace("T", " ")
    .replace(/\.\d+Z$/, " UTC");

export default function DemoShell() {
  const auth = useAuth(),
    navigate = useNavigate(),
    queries = useQueryClient();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const desk: Role = pathname.startsWith("/port")
    ? "PORT_AUTHORITY"
    : pathname.startsWith("/vessel")
      ? "VESSEL_OPERATOR"
      : pathname.startsWith("/company")
        ? "SHIPPING_COMPANY"
        : "NATIONAL_ADMIN";
  const query = useQuery({
    queryKey: ["demo-world", auth.session?.accessToken],
    queryFn: ({ signal }) =>
      getJson<DemoWorkspaceData>("/demo/workspace", {}, { signal }),
    retry: false,
    staleTime: 10000,
  });
  const data = query.data,
    world = data?.world;
  const [pane, setPane] = useState("scene"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  const [speed, setSpeed] = useState(16),
    [closure, setClosure] = useState(72),
    [wave, setWave] = useState(2),
    [hours, setHours] = useState<number | null>(null);
  const [optionId, setOption] = useState<string | null>(null),
    [eventId, setEvent] = useState<string | null>(null),
    [portCode, setPort] = useState("INNSA"),
    [mapFocus, setMapFocus] = useState("fleet");
  const [weatherImpact, setWeatherImpact] = useState(0.18),
    [waitHours, setWaitHours] = useState(3),
    [twinSelection, setTwinSelection] = useState<TwinSelection | null>(null);
  const [portOption, setPortOption] = useState(0);
  const vessel =
    world?.fleet.find((v) => v.id === world.selectedVessel) ?? world?.fleet[0];
  const comparison = world?.comparisons
    .filter((c) => c.vesselId === vessel?.id)
    .at(-1);
  const option =
    comparison?.result.options.find((o) => o.optionId === optionId) ??
    comparison?.result.options.find(
      (o) => o.optionId === world?.proposal?.optionId,
    ) ??
    comparison?.result.options[0];
  const port = data?.scene.ports.find((p) => p.code === portCode),
    forecast = port?.forecasts[0];
  const context = useMemo(
    () => ({
      ports: data?.scene.ports ?? [],
      news: { events: data?.scene.events ?? [] },
      cameras: data?.scene.cameras ?? [],
    }),
    [data?.scene],
  );
  const routes = useMemo(
    () =>
      option
        ? [
            {
              id: option.optionId,
              name: option.label,
              positions: option.geometry,
              selected: true,
            },
          ]
        : (data?.scene.routes
            .filter((r) => r.id === vessel?.laneCode)
            .map((r) => ({
              id: r.id,
              name: r.name,
              positions: r.positions,
              selected: true,
            })) ?? []),
    [option, data?.scene.routes, vessel?.laneCode],
  );
  const vessels = useMemo(
    () =>
      world?.fleet.map((v) => ({
        id: v.id,
        name: v.name + " · demo",
        lat:
          comparison?.vesselId === v.id
            ? comparison.result.position.lat
            : v.lat,
        lon:
          comparison?.vesselId === v.id
            ? comparison.result.position.lon
            : v.lon,
      })) ?? [],
    [world?.fleet, comparison],
  );
  const event = data?.scene.events.find((e) => e.eventId === eventId);
  const focus = useMemo(
    () => (mapFocus === "fleet" ? { lon: 55, lat: 25 } : undefined),
    [mapFocus],
  );
  const activeTwin =
    world?.portComparison?.options[portOption]?.finalState ?? data?.twin;
  const scenarioValid =
    [speed, closure, wave, hours ?? vessel?.hoursToRisk ?? 24].every(
      Number.isFinite,
    ) &&
    speed >= 6 &&
    speed <= 24 &&
    closure >= 1 &&
    closure <= 240 &&
    wave >= 0 &&
    wave <= 12 &&
    (hours ?? 24) >= -48 &&
    (hours ?? 24) <= 240;
  async function action(path: string, body: unknown = {}) {
    setBusy(true);
    setError(null);
    try {
      const result = await postJson(path, body);
      await queries.invalidateQueries({ queryKey: ["demo-world"] });
      return result;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Demo action failed");
      return null;
    } finally {
      setBusy(false);
    }
  }
  async function switchRole(role: Role) {
    setBusy(true);
    setError(null);
    try {
      await auth.switchDemo(role);
      setOption(null);
      setPane("scene");
      await navigate({ to: ROLE_PROFILE[role].home });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Role switch failed");
    } finally {
      setBusy(false);
    }
  }
  async function selectVessel(id: string) {
    const result = await action("/demo/selection", { vesselId: id });
    if (result) {
      setOption(null);
      setHours(null);
      setMapFocus("fleet");
      setPane("inspector");
    }
  }
  const nav =
    desk === "SHIPPING_COMPANY"
      ? [
          ["Fleet", "/company/overview"],
          ["Voyage options", "/company/routes"],
          ["Cargo", "/company/cargo"],
          ["Advisories", "/company/advisories"],
        ]
      : desk === "VESSEL_OPERATOR"
        ? [
            ["Bridge", "/vessel/overview"],
            ["Routes", "/vessel/routes"],
            ["Advisories", "/vessel/advisories"],
          ]
        : desk === "PORT_AUTHORITY"
          ? [
              ["Operations", "/port/overview"],
              ["Digital twin", "/port/twin"],
              ["Forecasts", "/port/forecast"],
              ["Weather", "/port/weather"],
              ["Advisories", "/port/advisories"],
            ]
          : [
              ["Network", "/admin/radar"],
              ["Ports", "/admin/ports"],
              ["Sources", "/admin/data"],
              ["Models & learning", "/admin/learning"],
              ["Scenarios", "/admin/scenarios"],
            ];
  const portDesk = desk === "PORT_AUTHORITY";
  const twinView = portDesk && !pathname.endsWith("/global-eye");
  const scenarioDesk =
    !portDesk && (desk !== "NATIONAL_ADMIN" || pathname.endsWith("/scenarios"));
  const globalPath =
    desk === "VESSEL_OPERATOR"
      ? "/vessel/routes"
      : ROLE_PROFILE[desk].home.split("/").slice(0, 2).join("/") +
        "/global-eye";
  useEffect(() => {
    const section = pathname.endsWith("/cargo")
      ? "cargo"
      : pathname.endsWith("/weather")
        ? "weather"
        : pathname.endsWith("/forecast")
          ? "forecast"
          : pathname.endsWith("/advisories")
            ? "advisories"
            : pathname.endsWith("/data")
              ? "sources"
              : pathname.endsWith("/learning")
                ? "models"
                : pathname.endsWith("/routes") ||
                    pathname.endsWith("/scenarios")
                  ? "voyage"
                  : null;
    if (section && query.isSuccess) {
      setPane(section === "cargo" ? "signals" : "inspector");
      document
        .getElementById("demo-" + section)
        ?.scrollIntoView({ block: "start" });
    }
  }, [pathname, query.isSuccess]);
  return (
    <div className="demo-app">
      <header className="demo-top">
        <Link to="/" className="demo-brand">
          ↗ PortWatch X
        </Link>
        <span>
          {ROLE_NAMES[desk]} · {portDesk ? "INNSA" : vessel?.name}
        </span>
        <span className="demo-badge">Visitor sandbox</span>
        <label>
          Switch demo role
          <select
            aria-label="Switch demo role"
            value={auth.role ?? desk}
            disabled={busy}
            onChange={(e) => void switchRole(e.target.value as Role)}
          >
            {Object.entries(ROLE_NAMES).map(([role, label]) => (
              <option key={role} value={role}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button
          disabled={busy}
          onClick={() =>
            void auth
              .resetDemo()
              .then(() => {
                setOption(null);
                setHours(null);
              })
              .catch((e) => setError(e.message))
          }
        >
          Reset demo
        </button>
        <button
          onClick={() =>
            void auth
              .signOut()
              .then(() => navigate({ to: "/login" }))
              .catch((e) => setError(e.message))
          }
        >
          Exit demo
        </button>
      </header>
      <nav className="demo-nav" aria-label="Demo workspace">
        {nav.map(([label, to]) => (
          <Link key={to} to={to} className={pathname === to ? "active" : ""}>
            {label}
          </Link>
        ))}
        <Link
          to={globalPath}
          onClick={() => {
            setPane("scene");
            setMapFocus("fleet");
          }}
        >
          Global Intelligence ↗
        </Link>
        <Link to="/research">Research & evidence ↗</Link>
      </nav>
      <nav className="demo-mobile-panels" aria-label="Demo panels">
        {[
          ["scene", "Scene"],
          ["signals", "Assets & signals"],
          ["inspector", "Planning & decisions"],
        ].map(([id, label]) => (
          <button
            key={id}
            aria-pressed={pane === id}
            onClick={() => setPane(id)}
          >
            {label}
          </button>
        ))}
      </nav>
      {error ? (
        <p role="alert" className="demo-error">
          {error}
        </p>
      ) : null}
      {query.isPending ? (
        <p role="status" className="demo-loading">
          Restoring your demonstration world…
        </p>
      ) : query.isError ? (
        <div className="demo-loading">
          <p role="alert">
            Demo world could not load. Your operational data was not
            substituted.
          </p>
          <button onClick={() => void query.refetch()}>Retry demo</button>
        </div>
      ) : (
        <div className={"demo-layout pane-" + pane}>
          <aside className="demo-assets">
            <small>
              01 /{" "}
              {desk === "SHIPPING_COMPANY"
                ? "Ranked fleet exposure"
                : desk === "VESSEL_OPERATOR"
                  ? "Assigned voyage"
                  : portDesk
                    ? "Arrivals & resources"
                    : "Network priorities"}
            </small>
            <h1>{titles[desk]}</h1>
            <p>{world?.meaning}</p>
            {world?.fleet.map((v) => (
              <button
                className={
                  v.id === vessel?.id ? "demo-asset selected" : "demo-asset"
                }
                key={v.id}
                disabled={
                  busy ||
                  (auth.role === "VESSEL_OPERATOR" && v.id !== "PWD-001")
                }
                onClick={() => void selectVessel(v.id)}
              >
                <strong>{v.name}</strong>
                <span>
                  {v.id} · {v.portCode} · {v.status}
                </span>
                <span>
                  {v.hoursToRisk} h relative to chokepoint · {v.cargo}
                </span>
              </button>
            ))}
            {desk === "SHIPPING_COMPANY" ? (
              <>
                <Link to="/vessel/overview">
                  Inspect selected voyage on the bridge →
                </Link>
                <section id="demo-cargo">
                  <h2>Cargo connections</h2>
                  <p>
                    {vessel?.cargo}. Illustrative planned port arrival{" "}
                    {number(vessel?.etaHours)} h after the demo epoch.
                  </p>
                  <p>
                    Compare ETA shifts against this plan. Connection cutoffs,
                    reefer charges and missed-service costs are unavailable;
                    cargo savings are not scored.
                  </p>
                </section>
              </>
            ) : null}
            {desk === "VESSEL_OPERATOR" && auth.role === "SHIPPING_COMPANY" ? (
              <Link to="/company/overview">← Return to fleet</Link>
            ) : null}
            {portDesk ? (
              <section>
                <h2>Illustrative arrival plan</h2>
                <p>
                  {world?.proposal
                    ? `${world.proposal.vesselId}: ${number(world.proposal.etaShiftHours)} h proposed ETA shift. The voyage is outside the initial 72 h berth window.`
                    : "Compare a company voyage and submit a proposal to see its arrival change here."}
                </p>
                <p>
                  4 schematic berths · {data?.twin.cranes.length} cranes ·{" "}
                  {data?.twin.calls.length} illustrative calls.
                </p>
                <p>
                  Camera coverage:{" "}
                  {data?.scene.cameras.length
                    ? "Public viewpoints available in Global Intelligence"
                    : "No authorized viewpoint connected"}
                  .
                </p>
              </section>
            ) : null}
            {desk === "NATIONAL_ADMIN" ? (
              <section>
                <h2>Public network forecasts</h2>
                {data?.scene.ports
                  .slice()
                  .sort(
                    (a, b) =>
                      (b.congestionIndex ?? -1) - (a.congestionIndex ?? -1),
                  )
                  .map((p) => (
                    <button
                      className="demo-risk-row"
                      key={p.code}
                      onClick={() => {
                        setPort(p.code);
                        setMapFocus("port");
                        setPane("inspector");
                      }}
                    >
                      {p.code} <span>{number(p.congestionIndex)} proxy</span>
                    </button>
                  ))}
              </section>
            ) : null}
            <section>
              <h2>Source-linked reports</h2>
              <p>
                Public context; the demo restriction is a separate assumption.
              </p>
              {data?.scene.events.slice(0, 8).map((e) => (
                <button
                  className="demo-asset"
                  key={e.eventId}
                  onClick={() => {
                    setEvent(e.eventId);
                    setMapFocus("event");
                    setPane("inspector");
                  }}
                >
                  <strong>{e.title}</strong>
                  <span>
                    {e.ports.length} ports · {clock(e.availableAt)}
                  </span>
                </button>
              ))}
            </section>
          </aside>
          <main className="demo-scene">
            <div className="demo-scene-heading">
              <h2>
                {twinView
                  ? "Port digital twin"
                  : "Voyages in their global context"}
              </h2>
              <p>
                {twinView
                  ? "Schematic facility · fictional occupancy"
                  : "Simulated hulls · no observed MMSI or live AIS"}
              </p>
            </div>
            <Suspense
              fallback={
                <p className="demo-loading" role="status">
                  Preparing the scene. Planning controls remain available.
                </p>
              }
            >
              {twinView && activeTwin ? (
                <Twin
                  state={activeTwin}
                  overlay="utilisation"
                  onSelect={setTwinSelection}
                  selectedId={twinSelection?.id}
                  className="demo-renderer"
                />
              ) : (
                <Globe
                  context={context}
                  portCode={portCode}
                  eventId={eventId}
                  earthquakes={false}
                  headers={NO_HEADERS}
                  focus={focus}
                  onPort={(code) => {
                    setPort(code);
                    setEvent(null);
                    setMapFocus("port");
                    setPane("inspector");
                  }}
                  onEvent={(id) => {
                    setEvent(id);
                    setMapFocus("event");
                    setPane("inspector");
                  }}
                  routes={routes}
                  vessels={vessels}
                  affectedPorts={event?.ports.map((p) => p.portCode)}
                  onVessel={(id) => void selectVessel(id)}
                />
              )}
            </Suspense>
            <div className="demo-scene-note">
              {twinView
                ? "Berths and dimensions follow the existing constrained twin. This layout is not a surveyed terminal."
                : "Route topology comes from the existing shipping engine. Visitor assumptions drive the scenario."}
            </div>
          </main>
          <aside className="demo-inspector">
            <h2>
              {portDesk
                ? "Resource planning & review"
                : desk === "NATIONAL_ADMIN"
                  ? "System reliability & experiments"
                  : vessel?.name}
            </h2>
            {event ? (
              <section>
                <h3>Selected public report</h3>
                <p>{event.title}</p>
                <p>
                  Catalogue exposure:{" "}
                  {event.ports.map((p) => p.portCode).join(", ")}. This report
                  was not substituted for the demo closure.
                </p>
                {event.sources
                  .filter((s) => s.url)
                  .slice(0, 3)
                  .map((s, i) => (
                    <a key={i} href={s.url!} target="_blank" rel="noreferrer">
                      {s.outlet ?? "Source report"} ↗
                    </a>
                  ))}
              </section>
            ) : null}
            <section id="demo-forecast">
              <h3>Destination forecast · {portCode}</h3>
              {forecast ? (
                <>
                  <strong className="demo-number">
                    {number(forecast.q50)} <small>/100 congestion proxy</small>
                  </strong>
                  <p>
                    Nominal 80% interval {number(forecast.q10)}–
                    {number(forecast.q90)}
                  </p>
                  <p>
                    Origin {clock(forecast.originDate)}
                    <br />
                    Target {clock(forecast.targetDate)}
                  </p>
                  <p>
                    {forecast.status} · public forecast context, not confirmed
                    waiting.
                  </p>
                </>
              ) : (
                <p>Forecast unavailable at this port.</p>
              )}
            </section>
            {portDesk ? (
              <section id="demo-weather">
                <h3>Weather context · {portCode}</h3>
                {data?.scene.weather
                  .filter((w) => w.portCode === portCode)
                  .map((w) => (
                    <div key={w.portCode + w.observedAt}>
                      <p>
                        {w.status} · {w.dataSource}
                      </p>
                      <p>
                        Wind {number(w.windKnots)} kn · wave{" "}
                        {number(w.waveHeightM)} m · visibility{" "}
                        {number(w.visibilityKm)} km
                      </p>
                      <p>
                        Weather time {clock(w.observedAt)}
                        <br />
                        Available {clock(w.availableAt)}
                      </p>
                      <p>
                        {w.timestampMeaning}. This context does not replace the
                        editable simulation weather assumption.
                      </p>
                    </div>
                  ))}
                {!data?.scene.weather.some((w) => w.portCode === portCode) ? (
                  <p>No public weather observation at this port.</p>
                ) : null}
              </section>
            ) : null}
            {desk === "NATIONAL_ADMIN" ? (
              <section id="demo-models">
                <h3>Model status</h3>
                <p>
                  Published historical GBM benchmark: evaluated proxy target.
                  Active cache: existing adaptive ensemble. A recent receipt
                  does not refresh its forecast origin.
                </p>
                <p>
                  Neural fusion, new RL policy and reserved-period calibration:
                  not yet trained in this milestone.
                </p>
                <Link to="/research">
                  Inspect benchmark versions & calibration ↗
                </Link>
                <h3 id="demo-sources">Source health</h3>
                {data?.scene.sources.map((s) => (
                  <p key={s.name}>
                    {s.name} · {s.status}
                    <br />
                    Available {s.collectedAt ? clock(s.collectedAt) : "Unknown"}
                  </p>
                ))}
              </section>
            ) : null}
            {scenarioDesk ? (
              <section id="demo-voyage">
                <h3>Voyage comparison</h3>
                <p>
                  {world?.event.title}. Changing timing, closure or seas creates
                  a new immutable comparison.
                </p>
                <div className="demo-form-grid">
                  {[
                    ["Service speed (kn)", speed, setSpeed],
                    ["Restriction duration (h)", closure, setClosure],
                    ["Assumed wave height (m)", wave, setWave],
                    [
                      "Hours before chokepoint",
                      hours ?? vessel?.hoursToRisk ?? 24,
                      setHours,
                    ],
                  ].map(([label, value, setter]) => (
                    <label key={String(label)}>
                      {String(label)}
                      <input
                        aria-label={String(label)}
                        type="number"
                        value={
                          Number.isFinite(value as number)
                            ? (value as number)
                            : ""
                        }
                        onChange={(e) =>
                          (setter as (v: number) => void)(
                            e.target.value === ""
                              ? NaN
                              : Number(e.target.value),
                          )
                        }
                      />
                    </label>
                  ))}
                </div>
                <button
                  className="demo-primary"
                  disabled={busy || !scenarioValid}
                  onClick={() =>
                    void action("/demo/scenario", {
                      vesselId: vessel?.id,
                      speedKn: speed,
                      closureHours: closure,
                      waveM: wave,
                      hoursToRisk: hours ?? vessel?.hoursToRisk ?? 24,
                    }).then((r) => {
                      if (r) setOption(null);
                    })
                  }
                >
                  Compare voyage actions
                </button>
                {!scenarioValid ? (
                  <p role="alert">
                    Enter finite values within speed 6–24 kn, duration 1–240 h,
                    waves 0–12 m and timing −48–240 h.
                  </p>
                ) : null}
                {comparison ? (
                  <>
                    <p>Frozen {clock(comparison.recordedAt)}</p>
                    <p>{comparison.result.doNothingStatement}</p>
                    <div className="demo-options">
                      {comparison.result.options.map((o) => (
                        <button
                          key={o.optionId}
                          className={
                            o.optionId === option?.optionId ? "selected" : ""
                          }
                          onClick={() => setOption(o.optionId)}
                        >
                          <strong>{o.label}</strong>
                          <span>
                            {o.feasible
                              ? "Feasible in the stated scenario"
                              : "Rejected"}{" "}
                            · {number(o.evaluation?.objectives.eta?.value)} h
                            ETA shift
                          </span>
                          {o.rejectedBy.map((c, i) => (
                            <span key={i}>
                              {c.label}: {c.detail}
                            </span>
                          ))}
                        </button>
                      ))}
                    </div>
                    <OptionDetails option={option} />
                    <p>{comparison.result.uncertainty}</p>
                    <p>{comparison.result.forecastConnection}</p>
                    {desk === "SHIPPING_COMPANY" ||
                    desk === "NATIONAL_ADMIN" ? (
                      <button
                        disabled={busy || !option?.feasible}
                        onClick={() =>
                          void action("/demo/proposal", {
                            comparisonId: comparison.id,
                            optionId: option?.optionId,
                          })
                        }
                      >
                        Submit selected plan to demo port
                      </button>
                    ) : null}
                  </>
                ) : (
                  <p>
                    Compare PWD-001 ahead of Suez, then inspect PWD-002 after
                    the commitment gate.
                  </p>
                )}
              </section>
            ) : null}
            {portDesk ? (
              <section>
                <h3>Compare berth resource policies</h3>
                <p>
                  Same fictional arrivals, dimensions, cranes and seed for both
                  policies. Unsafe allocations remain rejected.
                </p>
                <label>
                  Assumed weather impact (0–1)
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step=".05"
                    value={Number.isFinite(weatherImpact) ? weatherImpact : ""}
                    onChange={(e) =>
                      setWeatherImpact(
                        e.target.value === "" ? NaN : Number(e.target.value),
                      )
                    }
                  />
                </label>
                <button
                  className="demo-primary"
                  disabled={
                    busy ||
                    !Number.isFinite(weatherImpact) ||
                    weatherImpact < 0 ||
                    weatherImpact > 1
                  }
                  onClick={() =>
                    void action("/demo/port-scenario", {
                      weatherImpact,
                      horizonHours: 72,
                    }).then(() => setPortOption(0))
                  }
                >
                  Compare port plans
                </button>
                {world?.portComparison?.options.map((o, i) => (
                  <button
                    className={
                      "demo-asset " + (portOption === i ? "selected" : "")
                    }
                    key={o.policy}
                    onClick={() => setPortOption(i)}
                  >
                    <strong>{o.policy}</strong>
                    <span>
                      {number(o.metrics.meanWaitHours)} h mean simulated wait ·{" "}
                      {o.metrics.completedCalls} completed calls
                    </span>
                    <span>
                      {o.violations.length} violations ·{" "}
                      {o.rejectedActions.length} rejected actions
                    </span>
                  </button>
                ))}
                {twinSelection ? (
                  <div>
                    <h4>{twinSelection.label}</h4>
                    {twinSelection.fields.map(([k, v]) => (
                      <p key={k}>
                        {k}: {v}
                      </p>
                    ))}
                  </div>
                ) : null}
                <p>
                  Company proposal:{" "}
                  {world?.proposal
                    ? `${world.proposal.vesselId} · ${number(world.proposal.etaShiftHours)} h ETA shift · proposed, not executed`
                    : "No proposal yet. Switch to Company, compare and submit a plan."}
                </p>
                <button
                  disabled={busy || !world?.proposal || !world.portComparison}
                  onClick={() =>
                    void action("/demo/advisories", {
                      policy:
                        world?.portComparison?.options[portOption]?.policy,
                    })
                  }
                >
                  Approve and issue demo advisory
                </button>
              </section>
            ) : null}
            <section id="demo-advisories">
              <h3>Advisory → response → outcome</h3>
              <p>
                Only this visitor receives these records. Acknowledgment does
                not move a real vessel.
              </p>
              {world?.advisories.length ? (
                world.advisories.map((a) => (
                  <Advisory
                    key={a.id}
                    item={a}
                    desk={desk}
                    busy={busy}
                    waitHours={waitHours}
                    setWaitHours={setWaitHours}
                    action={action}
                  />
                ))
              ) : (
                <p>
                  No advisory yet. Company proposes → Port reviews its resource
                  comparison → Vessel acknowledges → Port records a demo
                  outcome.
                </p>
              )}
            </section>
            <section>
              <h3>Evidence & time</h3>
              <p>
                Demo epoch {world ? clock(world.epoch) : "—"}. Public
                observations keep their original availability; demo actions use
                actual receipt times.
              </p>
              <Link to="/explore">
                Current, replay & projection in Global Intelligence ↗
              </Link>
              <Link to="/research" hash="public-port-cases">
                Real port-call evidence ↗
              </Link>
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}
function OptionDetails({ option }: { option: ScenarioOption | undefined }) {
  return option?.evaluation ? (
    <div className="demo-option-details">
      <h4>Selected option inputs & consequences</h4>
      {Object.entries(option.evaluation.objectives).map(([key, m]) => (
        <p key={key}>
          {key}: {number(m.value)} {m.unit}
        </p>
      ))}
      {option.evaluation.financial.components.map((c) => (
        <p key={c.key}>
          {c.label}:{" "}
          {c.money ? `${number(c.money.amount)} ${c.money.currency}` : c.reason}
        </p>
      ))}
      <p>
        Partial costs under assumed USD 30,000/day charter, USD 650/tonne fuel
        and 45 tonnes/day burn. Unknown charges and cargo effects prevent a
        total savings claim.
      </p>
    </div>
  ) : null;
}
function Advisory({
  item,
  desk,
  busy,
  waitHours,
  setWaitHours,
  action,
}: {
  item: DemoAdvisory;
  desk: Role;
  busy: boolean;
  waitHours: number;
  setWaitHours: (v: number) => void;
  action: (path: string, body?: unknown) => Promise<unknown>;
}) {
  const recipient = desk === "SHIPPING_COMPANY" || desk === "VESSEL_OPERATOR",
    issuer = desk === "PORT_AUTHORITY" || desk === "NATIONAL_ADMIN";
  return (
    <article className="demo-advisory">
      <strong>
        {item.proposal.vesselId} · {item.state}
      </strong>
      <p>
        Issued {clock(item.issuedAt)}. Proposed ETA shift{" "}
        {number(item.proposal.etaShiftHours)} h.
      </p>
      <p>
        Reviewed port plan: {item.portPlan.policy} · seed {item.portPlan.seed} ·{" "}
        {number(item.portPlan.inputs.weatherImpact)} assumed weather impact.
      </p>
      {recipient && item.state === "ISSUED" ? (
        <button
          disabled={busy}
          onClick={() => void action(`/demo/advisories/${item.id}/ack`)}
        >
          Acknowledge demo advisory
        </button>
      ) : null}
      {issuer && item.state === "ACKNOWLEDGED" ? (
        <>
          <label>
            Demo reported waiting (h)
            <input
              type="number"
              min="0"
              max="240"
              value={Number.isFinite(waitHours) ? waitHours : ""}
              onChange={(e) =>
                setWaitHours(
                  e.target.value === "" ? NaN : Number(e.target.value),
                )
              }
            />
          </label>
          <button
            disabled={
              busy ||
              !Number.isFinite(waitHours) ||
              waitHours < 0 ||
              waitHours > 240
            }
            onClick={() =>
              void action(`/demo/advisories/${item.id}/outcome`, {
                reportedWaitingHours: waitHours,
              })
            }
          >
            Record demonstration outcome
          </button>
        </>
      ) : null}
      {item.outcome ? (
        <p>
          {item.outcome.reportedWaitingHours} h · {item.outcome.meaning}
        </p>
      ) : null}
    </article>
  );
}
