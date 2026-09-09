/**
 * National command.
 *
 * The map is the screen. Everything else floats over it and folds away: search
 * and filters top-left, the environment legend bottom-left, the time transport
 * across the bottom, and a right inspector that only appears once a vessel or a
 * port has been selected. Until then the right column carries the one summary a
 * duty officer needs -- what is moving, where the pressure is, and what the
 * decision layer wants done.
 */

import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { useMemo, useState } from "react";

import { useAuth } from "@/auth/AuthProvider";
import { AgentConsole } from "@/components/agent/AgentConsole";
import { useFixes, useTrafficTick } from "@/components/app/traffic-context";
import { PortSummary } from "@/components/command/PortCockpit";
import { MaritimeSearch, type SearchHit } from "@/components/command/MaritimeSearch";
import { TimeTransport } from "@/components/command/TimeTransport";
import {
  EnvironmentLegend,
  TrafficFilters,
  VesselClassLegend,
} from "@/components/command/TrafficFilters";
import {
  VesselHoverCard,
  VesselInspector,
  useRouteExposure,
} from "@/components/command/VesselInspector";
import { EmptyNote, FloatPanel, PanelSection } from "@/components/command/panels";
import { selectionGeometry } from "@/components/command/selection-geometry";
import { useWorkspaceMap } from "@/components/command/useWorkspaceMap";
import { Num, Pill, riskLabel, riskTone } from "@/components/kit/primitives";
import { ScreenFallback } from "@/components/kit/states";
import { MaritimeMap } from "@/components/map/MaritimeMap";
import { countByStatus, portTraffic } from "@/lib/maritime/traffic-views";
import { useNews } from "@/services/hooks";

export const Route = createFileRoute("/admin/radar")({ component: NationalRadar });

function NationalRadar() {
  const workspace = useWorkspaceMap();
  const news = useNews();
  const { setPortCode } = useAuth();
  const at = useTrafficTick(1);
  const fixes = useFixes(1);
  const [following, setFollowing] = useState(false);

  const selectedFix = useMemo(
    () => fixes.find((fix) => fix.id === workspace.selectedVesselId) ?? null,
    [fixes, workspace.selectedVesselId],
  );
  const exposure = useRouteExposure(selectedFix, workspace.timeline);
  const geometry = useMemo(() => selectionGeometry(selectedFix, exposure), [exposure, selectedFix]);

  const selectedPort = workspace.selectedPortCode
    ? (workspace.portByCode.get(workspace.selectedPortCode) ?? null)
    : null;

  const statusCounts = useMemo(() => countByStatus(fixes), [fixes]);
  const visibleCount = useMemo(
    () => fixes.filter(workspace.vesselFilter).length,
    [fixes, workspace.vesselFilter],
  );

  const selectedPortTraffic = useMemo(() => {
    if (!selectedPort?.location) return null;
    return portTraffic(fixes, {
      code: selectedPort.code,
      lat: selectedPort.location.lat,
      lon: selectedPort.location.lon,
    });
  }, [fixes, selectedPort]);

  const ranked = useMemo(
    () =>
      [...workspace.ports].sort((a, b) => (b.priorityScore ?? 0) - (a.priorityScore ?? 0)),
    [workspace.ports],
  );

  const alerts = news.data?.alerts ?? [];

  if (workspace.portsQuery.isLoading || workspace.portsQuery.isError) {
    return (
      <ScreenFallback
        title="National Command"
        context={<span>Live maritime picture for Indian waters</span>}
        isLoading={workspace.portsQuery.isLoading}
        error={workspace.portsQuery.error}
        retry={() => void workspace.portsQuery.refetch()}
        label="Acquiring national picture"
      />
    );
  }

  const onPick = (hit: SearchHit) => {
    if (hit.kind === "vessel") {
      workspace.setSelectedVesselId(hit.id);
      workspace.setSelectedPortCode(null);
    } else if (hit.kind === "port") {
      workspace.setSelectedPortCode(hit.id);
      workspace.setSelectedVesselId(null);
    }
    workspace.flyTo([hit.lon, hit.lat], hit.kind === "vessel" ? 8 : 7);
  };

  return (
    <div className="absolute inset-0">
      <h1 className="sr-only">National Command</h1>

      <MaritimeMap
        layers={workspace.layers}
        data={{ ...workspace.data, ...geometry }}
        weatherRaster={workspace.raster}
        windFrame={workspace.frame}
        showWind={workspace.showWind && workspace.layers.weather}
        vesselFilter={workspace.vesselFilter}
        labels={workspace.labels}
        selectedVesselId={workspace.selectedVesselId}
        onSelectVessel={(id) => {
          workspace.setSelectedVesselId(id);
          if (id) workspace.setSelectedPortCode(null);
          setFollowing(false);
        }}
        onHoverVessel={workspace.setHoveredVesselId}
        selectedPortCode={workspace.selectedPortCode}
        onSelectPort={(code) => {
          workspace.setSelectedPortCode(code);
          workspace.setSelectedVesselId(null);
        }}
        focus={
          following && selectedFix
            ? { center: [selectedFix.lon, selectedFix.lat], zoom: 8, token: Math.floor(at / 4000) }
            : workspace.focus
        }
        renderHoverCard={(fix) => <VesselHoverCard fix={fix} />}
        overlay={
          <>
            {/* -------------------------------------------------- top left -- */}
            <div className="pointer-events-none absolute left-2.5 top-2.5 z-20 flex max-h-[calc(100%-96px)] w-[216px] flex-col gap-2">
              <MaritimeSearch ports={workspace.ports} onPick={onPick} />
              <TrafficFilters workspace={workspace} />
            </div>

            {/* The command surface. Collapsed to a strip so the chart stays the
                product; it expands over the map and closes again. */}
            <div className="pointer-events-none absolute right-[352px] top-2.5 z-30">
              <AgentConsole />
            </div>

            {/* ------------------------------------------------- bottom left -- */}
            <div className="pointer-events-none absolute bottom-2.5 left-2.5 z-20 flex w-[248px] flex-col gap-1.5">
              <VesselClassLegend />
              <EnvironmentLegend workspace={workspace} frame={workspace.frame} />
            </div>

            {/* ------------------------------------------------------ bottom -- */}
            <div className="pointer-events-none absolute bottom-2.5 left-[272px] right-[352px] z-20">
              <TimeTransport timeline={workspace.timeline} weatherAt={workspace.weatherAt} />
            </div>

            {/* ------------------------------------------------------- right -- */}
            <div className="pointer-events-none absolute bottom-2.5 right-2.5 top-2.5 z-20 flex w-[338px] flex-col gap-2">
              {selectedFix ? (
                <VesselInspector
                  fix={selectedFix}
                  ports={workspace.ports}
                  timeline={workspace.timeline}
                  onClose={() => {
                    workspace.setSelectedVesselId(null);
                    workspace.setIsolate(null);
                    setFollowing(false);
                  }}
                  onIsolate={() =>
                    workspace.setIsolate(workspace.filters.isolate ? null : selectedFix.id)
                  }
                  isolated={workspace.filters.isolate === selectedFix.id}
                  onFollow={() => setFollowing((v) => !v)}
                  following={following}
                  onSelectVessel={(id) => workspace.setSelectedVesselId(id)}
                  className="min-h-0 flex-1"
                />
              ) : selectedPort && selectedPortTraffic ? (
                <FloatPanel
                  title={selectedPort.name}
                  note={<span className="num">{selectedPort.code}</span>}
                  onClose={() => workspace.setSelectedPortCode(null)}
                  className="min-h-0 flex-1"
                >
                  <PortSummary port={selectedPort} traffic={selectedPortTraffic} />
                  <PanelSection title="Open the twin">
                    <div className="flex flex-wrap gap-1.5">
                      <Link
                        to="/port/overview"
                        onClick={() => setPortCode(selectedPort.code)}
                        className="inline-flex items-center gap-1 rounded-[2px] border border-[var(--line-strong)] px-1.5 py-[3px] text-[10.5px] text-[var(--text-2)] hover:text-[var(--text)]"
                      >
                        Port cockpit <ArrowUpRight size={10} />
                      </Link>
                      <Link
                        to="/admin/scenarios"
                        className="inline-flex items-center gap-1 rounded-[2px] border border-[var(--line-strong)] px-1.5 py-[3px] text-[10.5px] text-[var(--text-2)] hover:text-[var(--text)]"
                      >
                        Stress-test <ArrowUpRight size={10} />
                      </Link>
                    </div>
                  </PanelSection>
                </FloatPanel>
              ) : (
                <FloatPanel
                  title="National picture"
                  note={<span className="num">{visibleCount} shown</span>}
                  className="min-h-0 flex-1"
                >
                  <PanelSection title="Traffic" right={`${fixes.length} tracked`}>
                    <div className="grid grid-cols-3 gap-x-2 gap-y-1.5">
                      {(
                        [
                          ["Under way", statusCounts.underway],
                          ["Inbound", statusCounts.inbound],
                          ["Outbound", statusCounts.outbound],
                          ["Anchored", statusCounts.anchored],
                          ["Waiting", statusCounts.waiting],
                          ["Alongside", statusCounts.moored],
                        ] as Array<[string, number]>
                      ).map(([label, count]) => (
                        <div key={label}>
                          <div className="text-[9.5px] uppercase tracking-[0.06em] text-[var(--text-3)]">
                            {label}
                          </div>
                          <div className="num mt-[1px] text-[16px] leading-none text-[var(--text)]">
                            {count}
                          </div>
                        </div>
                      ))}
                    </div>
                  </PanelSection>

                  <PanelSection title="Ports by priority" right={`${ranked.length} ranked`}>
                    <ul>
                      {ranked.map((port, index) => (
                        <li key={port.code}>
                          <button
                            type="button"
                            onClick={() => {
                              workspace.setSelectedPortCode(port.code);
                              if (port.location) workspace.flyTo([port.location.lon, port.location.lat], 7.4);
                            }}
                            className="grid w-full grid-cols-[16px_1fr_38px_54px_44px] items-center gap-1.5 rounded-[2px] px-1 py-[3px] text-left hover:bg-[var(--panel-2)]"
                          >
                            <span className="num text-[9.5px] text-[var(--text-3)]">
                              {String(index + 1).padStart(2, "0")}
                            </span>
                            <span className="truncate text-[11px] text-[var(--text)]">
                              {port.name}
                            </span>
                            <Num
                              value={port.congestionIndex}
                              digits={0}
                              className="text-right text-[11px]"
                            />
                            <span className="flex justify-end">
                              <Pill tone={riskTone(port.risk)}>{riskLabel(port.risk)}</Pill>
                            </span>
                            <span className="num text-right text-[10px] text-[var(--text-3)]">
                              {(port.delayHours ?? 0).toFixed(1)}h
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </PanelSection>

                  <PanelSection title="Action queue" right={`${alerts.length} open`}>
                    {alerts.length === 0 ? (
                      <EmptyNote>
                        The decision layer issued no action for the current forecast.
                      </EmptyNote>
                    ) : (
                      <ul className="space-y-1.5">
                        {alerts.slice(0, 6).map((alert) => (
                          <li key={alert.id}>
                            <div className="flex items-baseline gap-1.5">
                              <Pill tone={alert.severity === "high" ? "warn" : "info"}>
                                {alert.severity}
                              </Pill>
                              <span className="num ml-auto text-[9.5px] text-[var(--text-3)]">
                                conf {alert.confidence?.toFixed(2) ?? "n/a"}
                              </span>
                            </div>
                            <p className="mt-[2px] text-[10.5px] leading-snug text-[var(--text-2)]">
                              {alert.text}
                            </p>
                          </li>
                        ))}
                      </ul>
                    )}
                  </PanelSection>
                </FloatPanel>
              )}
            </div>
          </>
        }
      />
    </div>
  );
}
