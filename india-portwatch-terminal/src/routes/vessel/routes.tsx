import { Link, createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { statusTone, useFleetIntel, type VesselIntel } from "@/components/app/fleet-context";
import { Page, PageBody, PageHeader, Panel, StatStrip } from "@/components/kit/layout";
import {
  Delta,
  KeyValue,
  MiniBar,
  Num,
  Pill,
  formatUtc,
  riskLabel,
  riskTone,
} from "@/components/kit/primitives";
import { EmptyState, FailureState, LoadingPanel } from "@/components/kit/states";
import { MapControlPanel, MapLegend } from "@/components/map/MapControls";
import { OperationsMap } from "@/components/map/OperationsMap";
import type { LayerKey } from "@/components/map/basemap";
import type { Lane } from "@/components/map/layers";
import { useOperationalMap } from "@/components/map/useOperationalMap";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/vessel/routes")({ component: RouteIntelligence });

const LAYERS: Record<LayerKey, boolean> = {
  ports: true,
  vessels: false,
  weather: true,
  stations: false,
  storms: true,
  routes: true,
  chokepoints: true,
  events: false,
  zones: false,
  graticule: true,
};

/**
 * Route intelligence compares the call a vessel declared with the best
 * alternative in its own candidate set. Both sides come from the optimizer's
 * scored options — no third route is invented to make the comparison look
 * richer.
 */
function RouteIntelligence() {
  const { intel, isLoading, error, refetch, ports, weather, events } = useFleetIntel();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(LAYERS);

  const active: VesselIntel | null =
    intel.find((row) => row.vessel.id === selectedId) ?? intel[0] ?? null;

  const lanes = useMemo<Lane[]>(() => {
    if (!active?.destination?.location || !active.alternative?.location) return [];
    return [
      {
        id: `route-${active.vessel.id}`,
        from: active.destination.location,
        to: active.alternative.location,
        color: active.vessel.reroute ? "#d3a02f" : "#4c9fcb",
        width: 2,
        opacity: 0.9,
        dashed: true,
        label: "Declared call → alternative",
      },
    ];
  }, [active]);

  const emphasise = useMemo(
    () =>
      new Set(
        [active?.vessel.intendedPortCode, active?.vessel.recommendedPortCode].filter(
          (code): code is string => Boolean(code),
        ),
      ),
    [active],
  );

  const map = useOperationalMap({
    ports,
    weather,
    vessels: [],
    events,
    selected: active?.vessel.intendedPortCode ?? null,
    emphasise,
    extraLanes: lanes,
  });

  const centre = useMemo<[number, number]>(() => {
    const a = active?.destination?.location;
    const b = active?.alternative?.location;
    if (a && b && (a.lon !== b.lon || a.lat !== b.lat)) {
      return [(a.lon + b.lon) / 2, (a.lat + b.lat) / 2];
    }
    if (a) return [a.lon, a.lat];
    return [79.5, 15.5];
  }, [active]);

  if (isLoading) return <LoadingPanel label="Loading route options" rows={9} />;
  if (error) return <FailureState error={error} retry={refetch} />;

  if (!active) {
    return (
      <Page>
        <PageHeader title="Route Intelligence" />
        <PageBody>
          <EmptyState title="No routes scored" detail="The routing artefact is empty for this run." />
        </PageBody>
      </Page>
    );
  }

  const { vessel, destination, alternative } = active;
  const sameCall = vessel.intendedPortCode === vessel.recommendedPortCode;

  const comparison: Array<{
    metric: string;
    declared: number | null;
    alternative: number | null;
    digits?: number;
    unit?: string;
    /** True when a lower number is the better one. */
    lowerIsBetter: boolean;
    hint?: string;
  }> = [
    {
      metric: "Arrival day",
      declared: vessel.intendedArrivalDay ?? null,
      alternative: vessel.bestArrivalDay ?? null,
      digits: 0,
      lowerIsBetter: true,
      hint: "Horizon day the optimizer scored as cheapest inside the declared window",
    },
    {
      metric: "Predicted berth wait",
      declared: vessel.intendedWaitHours ?? null,
      alternative: vessel.alternativeWaitHours ?? null,
      unit: "h",
      lowerIsBetter: true,
    },
    {
      metric: "Extra steaming",
      declared: 0,
      alternative: vessel.extraSteamingHours ?? null,
      unit: "h",
      lowerIsBetter: true,
      hint: "Great-circle diversion converted at the optimizer's 19 kn service speed",
    },
    {
      metric: "Diversion",
      declared: 0,
      alternative: vessel.diversionKm ?? null,
      digits: 0,
      unit: " km",
      lowerIsBetter: true,
      hint: "Fuel proxy: the optimizer charges distance, not modelled bunker burn",
    },
    {
      metric: "Port entry risk",
      declared: vessel.intendedCongestionProbability ?? null,
      alternative: vessel.alternativeCongestionProbability ?? null,
      digits: 2,
      lowerIsBetter: true,
    },
    {
      metric: "Destination congestion",
      declared: destination?.congestionIndex ?? null,
      alternative: alternative?.congestionIndex ?? null,
      lowerIsBetter: true,
    },
    {
      metric: "Weather impact",
      declared: weather.find((s) => s.portCode === vessel.intendedPortCode)?.impactScore ?? null,
      alternative:
        weather.find((s) => s.portCode === vessel.recommendedPortCode)?.impactScore ?? null,
      digits: 3,
      lowerIsBetter: true,
    },
    {
      metric: "Optimizer cost",
      declared: vessel.intendedCost ?? null,
      alternative: vessel.alternativeCost ?? null,
      digits: 2,
      lowerIsBetter: true,
      hint: "Predicted delay + 40 × P(congestion) + 0.02 × diversion km",
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Route Intelligence"
        context={
          <>
            <span>{vessel.name}</span>
            <Pill tone={statusTone(active.status)}>{active.status}</Pill>
          </>
        }
        meta={<span className="num">origin {formatUtc(vessel.originDate)}</span>}
      />

      <StatStrip
        size="sm"
        items={[
          {
            label: "Declared call",
            value: vessel.intendedPortName ?? vessel.intendedPortCode ?? "n/a",
            note: destination ? `${destination.regime} · ${riskLabel(destination.risk)}` : "no snapshot",
          },
          {
            label: "Best alternative",
            value: vessel.recommendedPortName ?? vessel.recommendedPortCode ?? "n/a",
            tone: vessel.reroute ? "warn" : "neutral",
            note: sameCall ? "the declared call is already cheapest" : "from the vessel's candidate set",
          },
          {
            label: "Net ETA change",
            value: vessel.etaDeltaHours?.toFixed(1) ?? "n/a",
            unit: "h",
            tone: (vessel.etaDeltaHours ?? 0) > 0 ? "warn" : "ok",
            note: "extra steaming minus waiting time saved",
          },
          {
            label: "Berth wait change",
            value: vessel.portWaitDeltaHours?.toFixed(1) ?? "n/a",
            unit: "h",
            tone: (vessel.portWaitDeltaHours ?? 0) < 0 ? "ok" : "neutral",
            note: "negative means alongside sooner",
          },
          {
            label: "Cost advantage",
            value:
              vessel.intendedCost != null && vessel.alternativeCost != null
                ? (vessel.intendedCost - vessel.alternativeCost).toFixed(2)
                : "n/a",
            tone: vessel.reroute ? "warn" : "ok",
            note: "reroute only when this clears 15% of the declared cost",
          },
        ]}
      />

      <PageBody padded={false} className="flex min-h-0 overflow-hidden">
        <div className="flex w-[210px] shrink-0 flex-col border-r border-[var(--line)]">
          <div className="panel-head rounded-none">Fleet</div>
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {intel.map((row) => (
              <li key={row.vessel.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(row.vessel.id)}
                  className={cn(
                    "w-full border-b border-[var(--line)]/50 px-3 py-2 text-left transition-colors",
                    active.vessel.id === row.vessel.id
                      ? "bg-[var(--panel-3)]"
                      : "hover:bg-[var(--panel-2)]",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-[12px] text-[var(--text)]">
                      {row.vessel.name}
                    </span>
                    <Pill tone={statusTone(row.status)}>
                      {row.vessel.reroute ? "alt" : "keep"}
                    </Pill>
                  </div>
                  <div className="num mt-0.5 truncate text-[10.5px] text-[var(--text-3)]">
                    {row.vessel.intendedPortCode} → {row.vessel.recommendedPortCode}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative min-w-0 flex-1 border-r border-[var(--line)]">
          <OperationsMap
            data={map.data}
            visible={layers}
            labels={map.labels}
            selected={vessel.intendedPortCode}
            center={centre}
            zoom={sameCall ? 6.4 : 5.2}
            overlay={
              <>
                <MapControlPanel
                  toggles={[
                    { key: "ports", label: "Ports", count: map.counts.ports },
                    { key: "routes", label: "Corridors", count: map.counts.routes },
                    { key: "chokepoints", label: "Chokepoints", count: map.counts.chokepoints },
                    {
                      key: "weather",
                      label: "Weather field",
                      count: map.counts.weather,
                      disabled: (map.counts.weather ?? 0) === 0,
                      disabledReason: "No weather artefact in this run",
                    },
                    { key: "graticule", label: "Graticule" },
                  ]}
                  visible={layers}
                  onToggle={(key) => setLayers((prev) => ({ ...prev, [key]: !prev[key] }))}
                  weatherField={map.weatherField}
                  onWeatherField={map.setWeatherField}
                  weatherAvailability={map.availability}
                />
                <MapLegend
                  weatherField={map.weatherField}
                  weatherActive={layers.weather}
                  extra={[
                    {
                      label: sameCall ? "No diversion scored" : "Declared → alternative",
                      color: vessel.reroute ? "#d3a02f" : "#4c9fcb",
                      shape: "line",
                    },
                  ]}
                  note={
                    sameCall
                      ? "The optimizer's best option is the declared call itself, so there is no second path to draw."
                      : "The corridor is a great circle between the two calls — a comparison of endpoints, not a routed passage plan."
                  }
                />
              </>
            }
          />
        </div>

        <aside className="flex w-[430px] shrink-0 flex-col overflow-y-auto 2xl:w-[490px]">
          <Panel
            title="Declared versus recommended"
            className="shrink-0 rounded-none border-x-0 border-t-0"
          >
            <table className="data-grid">
              <thead>
                <tr>
                  {["Metric", "Declared", "Alternative", "Δ"].map((header, index) => (
                    <th
                      key={header}
                      className={cn(
                        "border-b border-[var(--line)] bg-[var(--panel-2)] px-2.5 py-[6px]",
                        "text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-3)]",
                        index === 0 ? "text-left" : "text-right",
                      )}
                    >
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {comparison.map((row) => {
                  const delta =
                    row.declared != null && row.alternative != null
                      ? row.alternative - row.declared
                      : null;
                  return (
                    <tr
                      key={row.metric}
                      title={row.hint}
                      className="border-b border-[var(--line)]/45 last:border-0"
                    >
                      <td className="px-2.5 py-[6px] text-[11.5px] text-[var(--text-3)]">
                        {row.metric}
                      </td>
                      <td className="px-2.5 py-[6px] text-right">
                        <Num value={row.declared} digits={row.digits ?? 1} unit={row.unit} />
                      </td>
                      <td className="px-2.5 py-[6px] text-right">
                        <Num value={row.alternative} digits={row.digits ?? 1} unit={row.unit} />
                      </td>
                      <td className="px-2.5 py-[6px] text-right">
                        {delta == null ? (
                          <span className="num text-[var(--text-3)]">—</span>
                        ) : (
                          <Delta
                            value={delta}
                            digits={row.digits ?? 1}
                            invert={!row.lowerIsBetter}
                          />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="border-t border-[var(--line)] px-3 py-2 text-[11.5px] leading-snug text-[var(--text-3)]">
              Green is the better side. The optimizer only advises a reroute when the cost
              advantage clears 15% of the declared call's cost, which is why a small
              improvement still reads as “keep”.
            </p>
          </Panel>

          <Panel title="Candidate set" className="shrink-0 rounded-none border-x-0 border-t-0">
            <div className="px-3 py-2">
              <KeyValue label="Declared call" dense>
                <span className="num text-[11.5px]">{vessel.intendedPortCode ?? "n/a"}</span>
              </KeyValue>
              <KeyValue label="Alternatives considered" dense>
                <span className="num text-[11.5px]">
                  {vessel.candidatePortCodes?.length
                    ? vessel.candidatePortCodes.join(" · ")
                    : "none declared"}
                </span>
              </KeyValue>
              <KeyValue label="Declared window" dense>
                <span className="num text-[11.5px]">
                  {active.arrivalWindow
                    ? `+${active.arrivalWindow.earliest} … +${active.arrivalWindow.latest}`
                    : "n/a"}
                </span>
              </KeyValue>
              <KeyValue label="Advised buffer" dense>
                <Num value={vessel.bufferHours} digits={0} unit="h" />
              </KeyValue>
              <p className="mt-2 border-t border-[var(--line)] pt-2 text-[11px] leading-snug text-[var(--text-3)]">
                The optimizer scores only the ports the operator declared as acceptable for
                this vessel. It does not search the whole network.
              </p>
            </div>
          </Panel>

          <Panel
            title="Overall risk"
            className="min-h-0 flex-1 rounded-none border-x-0 border-b-0"
          >
            <div className="p-3">
              {(
                [
                  ["Port entry risk", vessel.intendedCongestionProbability, "crit"],
                  [
                    "Destination weather",
                    weather.find((s) => s.portCode === vessel.intendedPortCode)?.impactScore,
                    "warn",
                  ],
                  [
                    "Model disagreement",
                    destination?.modelDisagreement,
                    "unc",
                  ],
                  [
                    "Transition risk 24h",
                    destination?.transitionRisk24h,
                    "info",
                  ],
                ] as const
              ).map(([label, value, tone]) => (
                <div key={label} className="mb-2.5">
                  <div className="mb-1 flex items-baseline justify-between">
                    <span className="text-[11.5px] text-[var(--text-3)]">{label}</span>
                    <Num value={value ?? null} digits={3} />
                  </div>
                  <MiniBar value={value ?? null} tone={tone} />
                </div>
              ))}
              <Link
                to="/vessel/$vesselId"
                params={{ vesselId: vessel.id }}
                className="mt-1 inline-block border-t border-[var(--line)] pt-2 text-[11.5px] text-[var(--info)] hover:underline"
              >
                Open the full vessel view →
              </Link>
            </div>
          </Panel>
        </aside>
      </PageBody>
    </Page>
  );
}
