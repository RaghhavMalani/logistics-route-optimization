/**
 * The port controller's cockpit.
 *
 * The chart is centred on the facility and carries every vessel that matters to
 * it: inbound, outbound, at anchor, waiting for a berth, alongside, and the
 * traffic simply passing through the approach. The approach sector, the
 * anchorage and the fairway centreline are drawn under them so the picture reads
 * as harbour control rather than as dots over water.
 *
 * The board along the bottom is the same fleet as a sortable table, and the
 * right column is the state, the arrival sequence, the weather and the decision
 * queue. Nothing here is a second page: every panel folds.
 */

import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { useFixes, useTrafficTick } from "@/components/app/traffic-context";
import { usePortContext, PortSwitcher } from "@/components/app/port-context";
import { MaritimeSearch, type SearchHit } from "@/components/command/MaritimeSearch";
import {
  ArrivalSequence,
  PortSummary,
  PortWeatherPanel,
  TrafficBoard,
} from "@/components/command/PortCockpit";
import { TimeTransport } from "@/components/command/TimeTransport";
import { EnvironmentLegend, TrafficFilters } from "@/components/command/TrafficFilters";
import {
  VesselHoverCard,
  VesselInspector,
  useRouteExposure,
} from "@/components/command/VesselInspector";
import { FloatPanel, PanelTabs } from "@/components/command/panels";
import { selectionGeometry } from "@/components/command/selection-geometry";
import { useWorkspaceMap } from "@/components/command/useWorkspaceMap";
import { ScreenFallback } from "@/components/kit/states";
import { MaritimeMap } from "@/components/map/MaritimeMap";
import { destination } from "@/lib/maritime/geo";
import { seawardBearing } from "@/lib/maritime/port-geometry";
import { arrivalSequence, portTraffic } from "@/lib/maritime/traffic-views";
import { useDecision, useForecast } from "@/services/hooks";

export const Route = createFileRoute("/port/overview")({ component: PortCockpitScreen });

type Tab = "state" | "arrivals" | "weather";

function PortCockpitScreen() {
  const { port, query } = usePortContext();
  const workspace = useWorkspaceMap({
    zonesFor: port?.code ?? null,
    initialSelectedPort: port?.code ?? null,
  });
  const at = useTrafficTick(1);
  const fixes = useFixes(1);
  const forecast = useForecast(port?.code ?? null);
  const decision = useDecision(port?.code ?? null);

  const [tab, setTab] = useState<Tab>("state");
  // The board is the densest thing on the screen and the first thing that
  // starts eating the chart. It opens where there is room for both.
  const [boardOpen, setBoardOpen] = useState(
    () => typeof window !== "undefined" && window.innerWidth >= 1600,
  );
  // A narrower frame holds less sea at the same scale, so it pulls back rather
  // than showing a harbour with three ships in it.
  const wide = typeof window === "undefined" || window.innerWidth >= 1600;
  const boardHeight = boardOpen ? 210 : 26;
  const bottomStack = boardHeight + 62;

  const traffic = useMemo(() => {
    if (!port?.location) return null;
    // Seventy nautical miles: wide enough to hold the whole approach the
    // opening camera shows, tight enough that "in the approach" still means
    // something to a duty controller.
    return portTraffic(
      fixes,
      { code: port.code, lat: port.location.lat, lon: port.location.lon },
      70,
    );
  }, [fixes, port]);

  const plan = useMemo(() => {
    if (!port || !traffic) return null;
    return arrivalSequence(traffic, port, { at, forecast: forecast.data ?? undefined });
  }, [at, forecast.data, port, traffic]);

  const selectedFix = useMemo(
    () => fixes.find((fix) => fix.id === workspace.selectedVesselId) ?? null,
    [fixes, workspace.selectedVesselId],
  );
  const exposure = useRouteExposure(selectedFix, workspace.timeline);
  const geometry = useMemo(() => selectionGeometry(selectedFix, exposure), [exposure, selectedFix]);

  const localIds = useMemo(
    () => new Set((traffic?.all ?? []).map((fix) => fix.id)),
    [traffic],
  );

  if (query.isLoading || query.isError || !port) {
    return (
      <ScreenFallback
        title="Port Control"
        context={<span>Approach traffic, arrivals and berth pressure</span>}
        isLoading={query.isLoading}
        error={query.error}
        retry={() => void query.refetch()}
        label="Acquiring port picture"
      />
    );
  }

  /*
   * The camera sits offshore of the quay, not on it.
   *
   * Half a port's compass is land, and centring on the berth spends half the
   * chart on a coastline nobody is watching. Pushing the view seaward puts the
   * facility near the edge and fills the frame with the approach, which is
   * where the traffic actually is.
   */
  const centre: [number, number] = port.location
    ? destination(
        [port.location.lon, port.location.lat],
        seawardBearing(port.code, port.location.lon, port.location.lat),
        46,
      )
    : [80.3, 13.1];

  const onPick = (hit: SearchHit) => {
    if (hit.kind === "vessel") workspace.setSelectedVesselId(hit.id);
    workspace.flyTo([hit.lon, hit.lat], hit.kind === "vessel" ? 9 : 8);
  };

  return (
    <div className="absolute inset-0">
      <h1 className="sr-only">{port.name} Port Control</h1>

      <MaritimeMap
        layers={workspace.layers}
        data={{ ...workspace.data, ...geometry }}
        weatherRaster={workspace.raster}
        windFrame={workspace.frame}
        showWind={workspace.showWind && workspace.layers.weather}
        vesselFilter={workspace.vesselFilter}
        pinnedIds={localIds}
        labels={workspace.labels}
        view={{ center: centre, zoom: wide ? 7.3 : 6.9 }}
        focus={workspace.focus}
        selectedVesselId={workspace.selectedVesselId}
        onSelectVessel={workspace.setSelectedVesselId}
        onHoverVessel={workspace.setHoveredVesselId}
        selectedPortCode={port.code}
        onSelectPort={() => undefined}
        forceVesselLabels
        maxVesselLabels={30}
        renderHoverCard={(fix) => <VesselHoverCard fix={fix} />}
        overlay={
          <>
            <div className="pointer-events-none absolute left-2.5 top-2.5 z-20 flex max-h-[calc(100%-96px)] w-[216px] flex-col gap-2">
              <MaritimeSearch ports={workspace.ports} onPick={onPick} placeholder="Search traffic" />
              <TrafficFilters workspace={workspace} />
            </div>

            <div className="pointer-events-none absolute left-2.5 top-2.5 z-20 ml-[224px] flex items-center gap-2">
              <div className="pointer-events-auto flex items-center gap-2 rounded-[3px] border border-[var(--line-strong)] bg-[var(--panel)]/95 px-2 py-[4px] backdrop-blur-[3px]">
                <PortSwitcher className="w-[168px]" />
              </div>
            </div>

            <div
              className="pointer-events-none absolute left-2.5 z-20 w-[248px]"
              style={{ bottom: bottomStack + 8 }}
            >
              <EnvironmentLegend workspace={workspace} frame={workspace.frame} />
            </div>

            {/* -------------------------------------------------- right rail -- */}
            <div
              className="pointer-events-none absolute right-2.5 top-2.5 z-20 flex w-[320px] flex-col gap-2"
              style={{ bottom: bottomStack + 8 }}
            >
              {selectedFix ? (
                <VesselInspector
                  fix={selectedFix}
                  ports={workspace.ports}
                  timeline={workspace.timeline}
                  onClose={() => {
                    workspace.setSelectedVesselId(null);
                    workspace.setIsolate(null);
                  }}
                  onIsolate={() =>
                    workspace.setIsolate(workspace.filters.isolate ? null : selectedFix.id)
                  }
                  isolated={workspace.filters.isolate === selectedFix.id}
                  onSelectVessel={workspace.setSelectedVesselId}
                  className="min-h-0 flex-1"
                />
              ) : (
                <FloatPanel
                  title={port.name}
                  note={<span className="num">{port.code}</span>}
                  className="min-h-0 flex-1"
                  scroll={false}
                >
                  <div className="flex h-full min-h-0 flex-col">
                    <PanelTabs
                      value={tab}
                      onChange={setTab}
                      tabs={[
                        { value: "state", label: "State" },
                        { value: "arrivals", label: "Arrivals", count: plan?.slots.length },
                        { value: "weather", label: "Weather" },
                      ]}
                    />
                    <div className="min-h-0 flex-1 overflow-y-auto">
                      {tab === "state" && traffic ? (
                        <PortSummary
                          port={port}
                          traffic={traffic}
                          plan={plan}
                          decision={decision.data ?? null}
                          decisionMissing={decision.isError}
                          onSelect={workspace.setSelectedVesselId}
                        />
                      ) : null}
                      {tab === "arrivals" && plan ? (
                        <ArrivalSequence
                          plan={plan}
                          selectedId={workspace.selectedVesselId}
                          onSelect={workspace.setSelectedVesselId}
                        />
                      ) : null}
                      {tab === "weather" ? (
                        <PortWeatherPanel
                          port={port}
                          timeline={workspace.timeline}
                          baseAt={workspace.weatherAt}
                        />
                      ) : null}
                    </div>
                  </div>
                </FloatPanel>
              )}
            </div>

            {/* ------------------------------------------------ traffic board -- */}
            <div
              className="pointer-events-none absolute z-20"
              style={{ left: 272, right: 330, bottom: boardHeight + 18 }}
            >
              <TimeTransport timeline={workspace.timeline} weatherAt={workspace.weatherAt} />
            </div>

            <div className="pointer-events-none absolute inset-x-2.5 bottom-2.5 z-20">
              {traffic && plan ? (
                <FloatPanel
                  title="Traffic board"
                  note={
                    <span className="num">
                      {traffic.all.length} vessels · {traffic.inbound.length} inbound ·{" "}
                      {traffic.waiting.length} waiting
                    </span>
                  }
                  actions={
                    <button
                      type="button"
                      onClick={() => setBoardOpen((v) => !v)}
                      className="text-[9.5px] uppercase tracking-[0.08em] text-[var(--text-3)] hover:text-[var(--text)]"
                    >
                      {boardOpen ? "collapse" : "expand"}
                    </button>
                  }
                  scroll={false}
                  testId="traffic-board"
                  className={boardOpen ? "h-[210px]" : "h-[26px]"}
                >
                  <TrafficBoard
                    traffic={traffic}
                    plan={plan}
                    port={port}
                    selectedId={workspace.selectedVesselId}
                    onSelect={workspace.setSelectedVesselId}
                    onHover={workspace.setHoveredVesselId}
                    className="h-full"
                  />
                </FloatPanel>
              ) : null}
            </div>
          </>
        }
      />
    </div>
  );
}
