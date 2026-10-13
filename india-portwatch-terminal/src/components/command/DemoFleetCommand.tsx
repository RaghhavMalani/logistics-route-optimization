import { lazy, Suspense, useMemo, useState } from "react";
import { Link } from "@tanstack/react-router";
import { FloatPanel, PanelSection, PanelTabs } from "./panels";
import {
  useDemoAction,
  useDemoWorkspace,
  type DemoVessel,
} from "@/services/demo";
import { formatUtc, Pill } from "@/components/kit/primitives";
import type { ScenarioOption } from "@/services/public-workspace";
import { ActionRow } from "./LegacyDemoActionRow";
import type { CompanyRiskRow } from "@/types/portwatch-os";
import "./demo-command.css";
const Globe = lazy(() => import("@/components/intelligence/IntelligenceGlobe"));
const HEADERS = {};

/** Maps only visitor-owned fleet and decision contracts onto Fleet Command. */
export function DemoFleetCommand() {
  const query = useDemoWorkspace(),
    action = useDemoAction(),
    data = query.data,
    world = data?.world;
  const [tab, setTab] = useState("action"),
    [search, setSearch] = useState(""),
    [pane, setPane] = useState("scene"),
    [optionId, setOption] = useState<string | null>(null);
  const [parameters, setParameters] = useState(false),
    [speed, setSpeed] = useState(16),
    [closure, setClosure] = useState(72),
    [wave, setWave] = useState(2),
    [timing, setTiming] = useState<number | null>(null);
  const [port, setPort] = useState("INNSA"),
    [eventId, setEvent] = useState<string | null>(null);
  const [contextSelection, setContextSelection] = useState<
    "port" | "event" | null
  >(null);
  const ship = world?.fleet.find((v) => v.id === world.selectedVessel),
    comparison = world?.comparisons
      .filter((c) => c.vesselId === ship?.id)
      .at(-1);
  const option =
    comparison?.result.options.find((o) => o.optionId === optionId) ??
    comparison?.result.options.find(
      (o) => o.optionId === comparison.result.recommendation?.optionId,
    ) ??
    comparison?.result.options[0];
  const routes = useMemo(
    () =>
      comparison
        ? comparison.result.options
            .filter((o) => o.optionId === option?.optionId || o.isBaseline)
            .map((o) => ({
              id: o.optionId,
              name: o.label,
              positions: o.geometry,
              selected: o.optionId === option?.optionId,
              rejected: !o.feasible,
            }))
        : (data?.scene.routes
            .filter((r) => r.id === ship?.laneCode)
            .map((r) => ({ ...r, selected: true })) ?? []),
    [comparison, option, data?.scene.routes, ship?.laneCode],
  );
  const context = useMemo(
    () => ({
      ports: data?.scene.ports ?? [],
      news: { events: data?.scene.events ?? [] },
      cameras: data?.scene.cameras ?? [],
    }),
    [data?.scene],
  );
  const vessels = useMemo(
    () =>
      world?.fleet.map((v) => ({
        id: v.id,
        name: v.name,
        lat:
          v.id === comparison?.vesselId
            ? comparison.result.position.lat
            : v.lat,
        lon:
          v.id === comparison?.vesselId
            ? comparison.result.position.lon
            : v.lon,
      })) ?? [],
    [world?.fleet, comparison],
  );
  async function pick(id: string) {
    await action.mutateAsync({
      path: "/demo/selection",
      body: { vesselId: id },
    });
    setOption(null);
    setTiming(null);
    setEvent(null);
    setContextSelection(null);
  }
  const row = (v: DemoVessel): CompanyRiskRow => ({
    vesselId: v.id,
    vesselName: v.name,
    laneCode: v.laneCode,
    chokepoint: v.laneCode === "GULF_IND" ? "HORMUZ" : "SUEZ",
    exposure: 1,
    hoursToRiskArea: v.hoursToRisk,
    alreadyEntered: v.hoursToRisk <= 0,
    diversionDeadline:
      v.hoursToRisk > 0
        ? new Date(
            Date.parse(world!.epoch) + v.hoursToRisk * 3600000,
          ).toISOString()
        : null,
    delayHoursIfDiverted: null,
    destinationPort: v.portCode,
    currentEta: new Date(
      Date.parse(world!.epoch) + v.etaHours * 3600000,
    ).toISOString(),
    recommendedAction: v.hoursToRisk <= 0 ? "monitor" : "evaluate_diversion",
    actionBasis:
      "Visitor-assumed restriction; not a verified closure or calibrated event probability.",
    eventId: world!.event.id,
    eventTitle: world!.event.title,
    eventCategory: "scenario",
    eventCategoryLabel: "Assumed restriction",
    eventSeverity: 1,
    eventConfidence: 1,
    eventProbability: null,
    eventSourceCount: 0,
  });
  const metric = (o: ScenarioOption, key: string) =>
    o.evaluation?.objectives[key]?.value;
  if (!data || !world || !ship)
    return (
      <div className="p-5" role={query.isError ? "alert" : "status"}>
        {query.isError ? query.error.message : "Loading your fleet…"}
        <button onClick={() => void query.refetch()}>Retry</button>
      </div>
    );
  return (
    <div className="fleet-command-preview" data-pane={pane}>
      <h1 className="sr-only">Fleet Command</h1>
      <div className="command-mobile-tabs">
        {["scene", "inspector"].map((p) => (
          <button key={p} aria-pressed={p === pane} onClick={() => setPane(p)}>
            {p === "scene" ? "Scene" : "Fleet & decisions"}
          </button>
        ))}
      </div>
      <div className="command-scene">
        <Suspense fallback={<p>Preparing globe…</p>}>
          <Globe
            context={context}
            portCode={port}
            eventId={eventId}
            earthquakes={false}
            headers={HEADERS}
            onPort={(code) => {
              setPort(code);
              setContextSelection("port");
              setPane("inspector");
            }}
            onEvent={(id) => {
              setEvent(id);
              setContextSelection("event");
              setPane("inspector");
            }}
            onVessel={(id) => void pick(id)}
            routes={routes}
            vessels={vessels}
            selectedVesselId={ship.id}
            fitSelectionKey={`${ship.id}:${option?.optionId ?? "voyage"}`}
          />
        </Suspense>
      </div>
      <div className="command-search">
        <label>
          <span className="sr-only">Find a fleet vessel</span>
          <input
            placeholder="Search vessel or port…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <details>
          <summary>Layers & scene key</summary>
          <p>▲ Fictional vessel · ● Port · ◆ Reported event</p>
          <p>Amber: selected route · blue: baseline · red dashed: infeasible</p>
          <p>
            General geographic context; no live AIS or connected wave field.
          </p>
        </details>
      </div>
      <aside
        className="command-inspector"
        aria-label="Fleet intervention inspector"
      >
        {contextSelection ? (
          <FloatPanel
            title={
              contextSelection === "port"
                ? data.scene.ports.find((p) => p.code === port)?.name
                : "Reported signal"
            }
            onClose={() => setContextSelection(null)}
          >
            <PanelSection title="Selected context">
              {contextSelection === "port" ? (
                <>
                  <p>{port} · dated forecast context</p>
                  <p>
                    Congestion proxy{" "}
                    {data.scene.ports
                      .find((p) => p.code === port)
                      ?.forecasts[0]?.q50?.toFixed(1) ?? "Unavailable"}{" "}
                    /100. Not confirmed berth waiting.
                  </p>
                </>
              ) : (
                <>
                  <p>
                    {
                      data.scene.events.find((e) => e.eventId === eventId)
                        ?.title
                    }
                  </p>
                  <p>
                    Public report; it does not verify the assumed demo
                    restriction.
                  </p>
                </>
              )}
              <Link to="/company/global-eye">
                Inspect forecasts and evidence →
              </Link>
            </PanelSection>
          </FloatPanel>
        ) : null}
        <FloatPanel
          title="Fleet Command"
          note="3 demo vessels"
          testId="fleet-command-panel"
        >
          <PanelTabs
            value={tab}
            onChange={setTab}
            tabs={[
              { value: "action", label: "Interventions" },
              { value: "fleet", label: "Fleet" },
            ]}
          />
          {world.fleet
            .filter(
              (v) =>
                (v.name + v.id).toLowerCase().includes(search.toLowerCase()) &&
                (tab === "fleet" || v.hoursToRisk > 0),
            )
            .map((v, i) => (
              <ActionRow
                key={v.id}
                row={row(v)}
                index={i}
                selected={v.id === ship.id}
                onSelect={() => void pick(v.id)}
              />
            ))}
          {tab === "action" ? (
            <PanelSection title="Committed passage">
              {world.fleet
                .filter((v) => v.hoursToRisk <= 0)
                .map((v) => (
                  <button
                    className="command-row"
                    key={v.id}
                    onClick={() => void pick(v.id)}
                  >
                    {v.name}
                    <span>Monitor · {v.hoursToRisk}h</span>
                  </button>
                ))}
            </PanelSection>
          ) : null}
        </FloatPanel>
        <FloatPanel title={ship.name} note={<Pill tone="unc">Simulated</Pill>}>
          <PanelSection title="Passage & deadline">
            <div className="command-row">
              <span>
                {ship.laneCode} → {ship.portCode}
              </span>
              <strong>
                {ship.hoursToRisk > 0
                  ? `${timing ?? ship.hoursToRisk}h to gate`
                  : "Gate passed"}
              </strong>
            </div>
            <div className="command-row">
              <span>Planned arrival</span>
              <span>
                {formatUtc(
                  new Date(
                    Date.parse(world.epoch) + ship.etaHours * 3600000,
                  ).toISOString(),
                )}
              </span>
            </div>
            <p>{ship.cargo}</p>
            <button
              className="command-primary"
              disabled={action.isPending}
              onClick={() => {
                setParameters(true);
                setPane("inspector");
              }}
            >
              Compare voyage actions
            </button>
          </PanelSection>
          {parameters ? (
            <PanelSection title="Assumed restriction">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void action
                    .mutateAsync({
                      path: "/demo/scenario",
                      body: {
                        vesselId: ship.id,
                        speedKn: speed,
                        closureHours: closure,
                        waveM: wave,
                        hoursToRisk: timing ?? ship.hoursToRisk,
                      },
                    })
                    .then(() => {
                      setOption(null);
                      setParameters(false);
                    });
                }}
              >
                <div className="command-fields">
                  {[
                    ["Speed (kn)", speed, setSpeed, 6, 24],
                    ["Closure (h)", closure, setClosure, 1, 240],
                    ["Waves (m)", wave, setWave, 0, 12],
                    [
                      "Hours to gate",
                      timing ?? ship.hoursToRisk,
                      setTiming,
                      -48,
                      240,
                    ],
                  ].map(([label, value, setter, min, max]) => (
                    <label key={String(label)}>
                      {String(label)}
                      <input
                        aria-label={String(label)}
                        type="number"
                        required
                        min={Number(min)}
                        max={Number(max)}
                        step="any"
                        value={Number.isNaN(value) ? "" : Number(value)}
                        onChange={(e) =>
                          (setter as (v: number) => void)(
                            e.target.valueAsNumber,
                          )
                        }
                      />
                    </label>
                  ))}
                </div>
                <button className="command-primary" disabled={action.isPending}>
                  Run comparison
                </button>
              </form>
              <p>
                USD 30,000/day charter · USD 650/t bunker · 45 t/day. Editable
                assumptions in Global Intelligence.
              </p>
            </PanelSection>
          ) : null}
          {comparison ? (
            <PanelSection
              title="Voyage alternatives"
              right={`${comparison.result.options.length} options`}
            >
              {comparison.result.options.map((o) => (
                <button
                  key={o.optionId}
                  className="command-option"
                  aria-pressed={option?.optionId === o.optionId}
                  onClick={() => setOption(o.optionId)}
                >
                  <strong>{o.label}</strong>
                  <span>
                    {o.feasible
                      ? `${metric(o, "eta")?.toFixed(1) ?? "—"} h ETA shift`
                      : `Rejected · ${o.rejectedBy[0]?.label ?? "constraint"}`}
                  </span>
                </button>
              ))}
              {option ? (
                <>
                  <p>{comparison.result.recommendation?.statement}</p>
                  <details>
                    <summary>Constraints, uncertainty & cost</summary>
                    <p>{comparison.result.uncertainty}</p>
                    {option.constraints.map((c) => (
                      <p key={c.label}>
                        {c.passed ? "✓" : "×"} {c.label}: {c.detail}
                      </p>
                    ))}
                    <p>
                      {option.evaluation?.financial.partialTotal?.amount.toLocaleString() ??
                        "Unavailable"}{" "}
                      USD partial assumed cost. Cargo and terminal charges are
                      unavailable.
                    </p>
                  </details>
                  <button
                    className="command-primary"
                    disabled={!option.feasible || action.isPending}
                    onClick={() =>
                      void action.mutateAsync({
                        path: "/demo/proposal",
                        body: {
                          comparisonId: comparison.id,
                          optionId: option.optionId,
                        },
                      })
                    }
                  >
                    Submit to port review
                  </button>
                </>
              ) : null}
            </PanelSection>
          ) : null}
          <PanelSection title="Advisory chain">
            <p>
              {world.proposal
                ? `Proposal ${world.proposal.vesselId} · ${world.proposal.state}. Port review available through role switch.`
                : "No proposal yet. Compare a voyage to start port review."}
            </p>
            {world.advisories.map((a) => (
              <div key={a.id}>
                <strong>
                  {a.proposal.vesselId} · {a.state}
                </strong>
                <p>
                  {a.outcome
                    ? `${a.outcome.reportedWaitingHours}h demonstration outcome`
                    : a.portPlan.policy}
                </p>
                {a.state === "ISSUED" ? (
                  <button
                    onClick={() =>
                      void action.mutateAsync({
                        path: `/demo/advisories/${a.id}/ack`,
                      })
                    }
                  >
                    Acknowledge advisory
                  </button>
                ) : null}
              </div>
            ))}
          </PanelSection>
          <PanelSection title="Evidence & context">
            <details>
              <summary>Sources and clocks</summary>
              <p>
                Visitor epoch {formatUtc(world.epoch)}. Actions use actual
                receipt times.
              </p>
              <p>
                Fictional ship identities; MMSI unavailable. Restriction and
                voyage inputs are assumptions.
              </p>
              <p>
                {data.scene.ports.find((p) => p.code === port)?.name} · forecast
                origin{" "}
                {formatUtc(
                  data.scene.ports.find((p) => p.code === port)?.forecasts[0]
                    ?.originDate,
                )}
                . Dated congestion proxy, not confirmed berth waiting.
              </p>
            </details>
            <Link to="/company/global-eye">Investigate global signals →</Link>
          </PanelSection>
        </FloatPanel>
        {action.isError ? <p role="alert">{action.error.message}</p> : null}
      </aside>
      <div className="command-voyage-strip">
        <span>▲ {ship.name} · FICTIONAL</span>
        <span>
          {ship.laneCode} → {ship.portCode}
        </span>
        <span>{option?.label ?? "Published lane geometry"}</span>
        <span>Demo epoch {formatUtc(world.epoch)}</span>
      </div>
    </div>
  );
}
