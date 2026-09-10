/**
 * Fleet Command.
 *
 * The screen answers one question, and the layout is built around it:
 *
 *     Which ships in my fleet require intervention over the next 72 hours?
 *
 * So ACTION REQUIRED is the first thing on the right rail, above the fleet
 * roster and above everything else. It is ranked by exposure, and every row
 * carries the deadline by which the option closes — because an exposure with no
 * deadline is a statistic and an exposure with one is a decision.
 *
 * Vessels that have already entered a risk area appear in a separate, quieter
 * list. They are not "less important"; they are *unactionable*, and mixing them
 * into the action queue would send an operator looking for a lever that is not
 * there.
 *
 * Map-first, like every primary surface. Company vessels are drawn at full
 * weight, other traffic is dimmed rather than hidden, and the weather composite
 * is on by default.
 */

import { createFileRoute } from "@tanstack/react-router";
import { AlertTriangle, ArrowUpRight, Ship } from "lucide-react";
import { useMemo, useState } from "react";

import { Link } from "@tanstack/react-router";

import { useWorkspace } from "@/auth/AuthProvider";
import { AgentConsole } from "@/components/agent/AgentConsole";
import { useFixes } from "@/components/app/traffic-context";
import { MaritimeSearch, type SearchHit } from "@/components/command/MaritimeSearch";
import { TimeTransport } from "@/components/command/TimeTransport";
import { EnvironmentLegend, TrafficFilters } from "@/components/command/TrafficFilters";
import { VesselHoverCard } from "@/components/command/VesselInspector";
import { EmptyNote, FloatPanel, PanelSection, PanelTabs } from "@/components/command/panels";
import { useWorkspaceMap } from "@/components/command/useWorkspaceMap";
import { exposureTone } from "@/components/globaleye/EventPanels";
import { Pill, formatUtc } from "@/components/kit/primitives";
import { ScreenFallback } from "@/components/kit/states";
import { MaritimeMap } from "@/components/map/MaritimeMap";
import { CHOKEPOINT_BY_CODE } from "@/lib/maritime/chokepoints";
import { seaRoute } from "@/lib/maritime/searoutes";
import { cn } from "@/lib/utils";
import { useCompanyFleet, useCompanyRisk } from "@/services/os-hooks";
import type { CompanyRiskRow, FleetVessel } from "@/types/portwatch-os";

export const Route = createFileRoute("/company/overview")({ component: FleetCommand });

/** Lane geometry for the vessels this fleet actually runs. */
function fleetRoutes(
  vessels: FleetVessel[],
  exposureByVessel: Map<string, number>,
  selectedId: string | null,
): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (const vessel of vessels) {
    if (!vessel.origin_port || !vessel.destination_port) continue;
    const route = seaRoute(vessel.origin_port, vessel.destination_port);
    if (!route) continue;
    const exposure = exposureByVessel.get(vessel.vessel_id) ?? 0;
    const focused = selectedId === null || selectedId === vessel.vessel_id;
    features.push({
      type: "Feature",
      properties: {
        part: "fleet",
        id: vessel.vessel_id,
        color:
          exposure >= 0.55 ? "#d05a4c" : exposure >= 0.3 ? "#d3a02f" : "#4c9fcb",
        width: focused ? 1.4 + exposure * 2 : 0.8,
        opacity: focused ? 0.35 + exposure * 0.45 : 0.12,
        label: `${vessel.name} · ${vessel.origin_port} → ${vessel.destination_port}`,
      },
      geometry: { type: "LineString", coordinates: route.path.coords },
    });
  }
  return { type: "FeatureCollection", features };
}

function ActionRow({
  row,
  index,
  onSelect,
  selected,
}: {
  row: CompanyRiskRow;
  index: number;
  onSelect: () => void;
  selected: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      data-testid="action-required-row"
      className={cn(
        "block w-full border-b border-[var(--line)]/60 px-2 py-1.5 text-left transition-colors last:border-0",
        selected ? "bg-[var(--panel-3)]" : "hover:bg-[var(--panel-2)]",
      )}
    >
      <div className="flex items-baseline gap-2">
        <span className="num shrink-0 text-[10px] text-[var(--text-3)]">
          {String(index + 1).padStart(2, "0")}
        </span>
        <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-[var(--text)]">
          {row.vesselName}
        </span>
        <span
          className={cn("num shrink-0 text-[11px]", `text-[var(--${exposureTone(row.exposure)})]`)}
        >
          {row.exposure.toFixed(2)}
        </span>
      </div>

      <div className="mt-[3px] text-[10.5px] leading-snug text-[var(--text-2)]">
        {row.eventCategoryLabel} · {row.chokepoint.replace(/_/g, "-")}
      </div>

      <div className="mt-[3px] flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9.5px] text-[var(--text-3)]">
        {row.hoursToRiskArea != null ? (
          <span className="num">{row.hoursToRiskArea.toFixed(0)}h to the risk area</span>
        ) : null}
        {row.delayHoursIfDiverted != null ? (
          <span className="num">diversion costs {row.delayHoursIfDiverted.toFixed(0)}h</span>
        ) : null}
        {row.destinationPort ? <span className="num">→ {row.destinationPort}</span> : null}
      </div>

      <div className="mt-1 flex items-center gap-1.5">
        <Pill tone={row.recommendedAction === "evaluate_diversion" ? "warn" : "info"}>
          {row.recommendedAction.replace(/_/g, " ")}
        </Pill>
        {row.diversionDeadline ? (
          <span className="num text-[9.5px] text-[var(--warn)]">
            by {formatUtc(row.diversionDeadline)}
          </span>
        ) : null}
      </div>
    </button>
  );
}

function FleetCommand() {
  const { companyId } = useWorkspace();
  const workspace = useWorkspaceMap({ layerOverrides: { routes: true } });
  const fleet = useCompanyFleet(companyId);
  const [horizon, setHorizon] = useState(72);
  const risk = useCompanyRisk(companyId, horizon);
  const [selectedVessel, setSelectedVessel] = useState<string | null>(null);
  const [tab, setTab] = useState<"action" | "fleet" | "ports">("action");
  const fixes = useFixes(1);

  const vessels = fleet.data?.vessels ?? [];
  const actionRequired = risk.data?.actionRequired ?? [];
  const monitorOnly = risk.data?.monitorOnly ?? [];

  const exposureByVessel = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of risk.data?.rows ?? []) {
      map.set(row.vesselId, Math.max(map.get(row.vesselId) ?? 0, row.exposure));
    }
    return map;
  }, [risk.data?.rows]);

  const routes = useMemo(
    () => fleetRoutes(vessels, exposureByVessel, selectedVessel),
    [exposureByVessel, selectedVessel, vessels],
  );

  const portRisk = useMemo(
    () => Object.values(risk.data?.portRisk ?? {}).sort((a, b) => b.risk - a.risk),
    [risk.data?.portRisk],
  );

  const selected = useMemo(
    () => vessels.find((v) => v.vessel_id === selectedVessel) ?? null,
    [selectedVessel, vessels],
  );
  const selectedRows = useMemo(
    () => (risk.data?.rows ?? []).filter((row) => row.vesselId === selectedVessel),
    [risk.data?.rows, selectedVessel],
  );

  // Hoisted above the loading early-return. Called from inside the JSX it sat
  // after that return, so the loading render and the loaded render disagreed on
  // how many hooks had run.
  const ownedIds = useMemo(
    () => new Set(fixes.filter((fix) => fix.owned).map((fix) => fix.id)),
    [fixes],
  );

  if (fleet.isLoading || fleet.isError) {
    return (
      <ScreenFallback
        title="Fleet Command"
        context={<span>Which ships require intervention</span>}
        isLoading={fleet.isLoading}
        error={fleet.error}
        retry={() => void fleet.refetch()}
        label="Loading the fleet"
      />
    );
  }

  const onPick = (hit: SearchHit) => {
    if (hit.kind === "port") workspace.setSelectedPortCode(hit.id);
    workspace.flyTo([hit.lon, hit.lat], hit.kind === "vessel" ? 8 : 7);
  };

  return (
    <div className="absolute inset-0">
      <h1 className="sr-only">Fleet Command</h1>

      <MaritimeMap
        layers={{ ...workspace.layers, routes: true }}
        data={{ ...workspace.data, routes }}
        weatherRaster={workspace.raster}
        windFrame={workspace.frame}
        showWind={workspace.showWind && workspace.layers.weather}
        vesselFilter={workspace.vesselFilter}
        // Company hulls at full weight, everything else dimmed but present: a
        // fleet desk needs to see its own ships in traffic, not in isolation.
        focusIds={ownedIds}
        labels={workspace.labels}
        selectedPortCode={workspace.selectedPortCode}
        onSelectPort={workspace.setSelectedPortCode}
        renderHoverCard={(fix) => <VesselHoverCard fix={fix} />}
        focus={workspace.focus}
        overlay={
          <>
            <div className="pointer-events-none absolute left-2.5 top-2.5 z-20 flex max-h-[calc(100%-96px)] w-[216px] flex-col gap-2">
              <MaritimeSearch ports={workspace.ports} onPick={onPick} />
              <TrafficFilters workspace={workspace} />
            </div>

            <div className="pointer-events-none absolute bottom-2.5 left-2.5 z-20 w-[248px]">
              <EnvironmentLegend workspace={workspace} frame={workspace.frame} />
            </div>

            <div className="pointer-events-none absolute right-[372px] top-2.5 z-30">
              <AgentConsole />
            </div>

            <div className="pointer-events-none absolute bottom-2.5 left-[272px] right-[372px] z-20">
              <TimeTransport timeline={workspace.timeline} weatherAt={workspace.weatherAt} />
            </div>

            {/* --------------------------------------------------- right -- */}
            <div className="pointer-events-none absolute bottom-2.5 right-2.5 top-2.5 z-20 flex w-[358px] flex-col gap-2">
              <FloatPanel
                title={fleet.data?.companyName ?? "Fleet"}
                note={
                  <span className="num">
                    {risk.data?.vesselsExposed ?? 0}/{vessels.length} exposed
                  </span>
                }
                className="min-h-0 flex-1"
                scroll
                testId="fleet-command-panel"
                footer={fleet.data?.disclaimer}
              >
                <div className="flex items-center gap-1 border-b border-[var(--line)] px-2 py-1">
                  <span className="eyebrow text-[8.5px]">Horizon</span>
                  {[24, 48, 72, 168].map((hours) => (
                    <button
                      key={hours}
                      type="button"
                      aria-pressed={horizon === hours}
                      onClick={() => setHorizon(hours)}
                      className={cn(
                        "num rounded-[2px] px-1.5 py-[1px] text-[10px] transition-colors",
                        horizon === hours
                          ? "bg-[var(--panel-4)] text-[var(--text)]"
                          : "text-[var(--text-3)] hover:text-[var(--text-2)]",
                      )}
                    >
                      {hours}h
                    </button>
                  ))}
                  <Link
                    to="/company/global-eye"
                    className="ml-auto inline-flex items-center gap-1 text-[10px] text-[var(--text-3)] hover:text-[var(--text)]"
                  >
                    Global Eye <ArrowUpRight size={9} />
                  </Link>
                </div>

                <PanelTabs
                  value={tab}
                  onChange={setTab}
                  tabs={[
                    { value: "action", label: "Action required", count: actionRequired.length },
                    { value: "fleet", label: "Fleet", count: vessels.length },
                    { value: "ports", label: "Ports", count: portRisk.length },
                  ]}
                />

                {tab === "action" ? (
                  <>
                    {risk.isLoading ? (
                      <EmptyNote>Computing fleet exposure…</EmptyNote>
                    ) : actionRequired.length === 0 ? (
                      <EmptyNote>
                        No vessel in this fleet requires intervention over the next{" "}
                        {horizon} hours. {monitorOnly.length
                          ? `${monitorOnly.length} vessel(s) are already inside an exposed area and appear below.`
                          : "No live event reaches a lane this fleet runs."}
                      </EmptyNote>
                    ) : (
                      <div data-testid="action-required">
                        <div className="flex items-center gap-1.5 border-b border-[var(--line)] bg-[var(--crit-dim)]/25 px-2 py-1">
                          <AlertTriangle size={11} className="text-[var(--crit)]" />
                          <span className="eyebrow text-[9px] text-[var(--crit)]">
                            Action required
                          </span>
                          <span className="num ml-auto text-[10px] text-[var(--text-2)]">
                            {actionRequired.length} vessel
                            {actionRequired.length === 1 ? "" : "s"}
                          </span>
                        </div>
                        {actionRequired.map((row, index) => (
                          <ActionRow
                            key={`${row.vesselId}-${row.eventId}`}
                            row={row}
                            index={index}
                            selected={selectedVessel === row.vesselId}
                            onSelect={() => setSelectedVessel(row.vesselId)}
                          />
                        ))}
                      </div>
                    )}

                    {monitorOnly.length ? (
                      <PanelSection
                        title="Already committed"
                        right={`${monitorOnly.length} monitor only`}
                      >
                        <p className="mb-1.5 text-[10px] leading-snug text-[var(--text-3)]">
                          These vessels have passed the point at which a diversion was
                          available. They are listed so they are not mistaken for safe;
                          no routing action is offered because none exists.
                        </p>
                        {monitorOnly.map((row) => (
                          <div
                            key={`${row.vesselId}-${row.eventId}`}
                            className="flex items-baseline gap-2 border-b border-[var(--line)]/50 py-[3px] last:border-0"
                          >
                            <span className="min-w-0 flex-1 truncate text-[10.5px] text-[var(--text-2)]">
                              {row.vesselName}
                            </span>
                            <span className="num shrink-0 text-[9.5px] text-[var(--text-3)]">
                              {row.chokepoint.replace(/_/g, "-")}
                            </span>
                            <span className="num shrink-0 text-[10.5px] text-[var(--unc)]">
                              {row.exposure.toFixed(2)}
                            </span>
                          </div>
                        ))}
                      </PanelSection>
                    ) : null}
                  </>
                ) : null}

                {tab === "fleet" ? (
                  <div>
                    {vessels.map((vessel) => {
                      const exposure = exposureByVessel.get(vessel.vessel_id) ?? 0;
                      return (
                        <button
                          key={vessel.vessel_id}
                          type="button"
                          onClick={() => setSelectedVessel(vessel.vessel_id)}
                          className={cn(
                            "block w-full border-b border-[var(--line)]/60 px-2 py-1.5 text-left transition-colors last:border-0",
                            selectedVessel === vessel.vessel_id
                              ? "bg-[var(--panel-3)]"
                              : "hover:bg-[var(--panel-2)]",
                          )}
                        >
                          <div className="flex items-baseline gap-2">
                            <Ship size={10} className="shrink-0 text-[var(--text-3)]" />
                            <span className="min-w-0 flex-1 truncate text-[11.5px] text-[var(--text)]">
                              {vessel.name}
                            </span>
                            {exposure > 0 ? (
                              <span
                                className={cn(
                                  "num shrink-0 text-[10.5px]",
                                  `text-[var(--${exposureTone(exposure)})]`,
                                )}
                              >
                                {exposure.toFixed(2)}
                              </span>
                            ) : (
                              <span className="num shrink-0 text-[10px] text-[var(--ok)]">
                                clear
                              </span>
                            )}
                          </div>
                          <div className="mt-[2px] flex flex-wrap items-center gap-x-2 text-[9.5px] text-[var(--text-3)]">
                            <span className="num">{vessel.vessel_id}</span>
                            <span className="truncate">{vessel.laneName ?? "no lane"}</span>
                            <span className="num">
                              {vessel.origin_port} → {vessel.destination_port}
                            </span>
                            {vessel.eta ? (
                              <span className="num">ETA {formatUtc(vessel.eta)}</span>
                            ) : null}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : null}

                {tab === "ports" ? (
                  portRisk.length ? (
                    <div className="px-2 py-1">
                      {portRisk.map((port) => (
                        <div
                          key={port.portCode}
                          className="border-b border-[var(--line)]/50 py-1 last:border-0"
                        >
                          <div className="flex items-baseline gap-2">
                            <span className="num w-[46px] shrink-0 text-[10.5px] text-[var(--text-2)]">
                              {port.portCode}
                            </span>
                            <span className="min-w-0 flex-1 truncate text-[10.5px] text-[var(--text)]">
                              {port.portName}
                            </span>
                            <span className="num shrink-0 text-[9.5px] text-[var(--text-3)]">
                              {port.affectedVessels} vsl
                            </span>
                            <span
                              className={cn(
                                "num shrink-0 text-[11px]",
                                `text-[var(--${exposureTone(port.risk)})]`,
                              )}
                            >
                              {port.risk.toFixed(2)}
                            </span>
                          </div>
                          {port.arrivalShiftHours ? (
                            <div className="num mt-[2px] text-[9.5px] text-[var(--text-3)]">
                              arrivals shift +{port.arrivalShiftHours.toFixed(1)} h
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyNote>
                      No destination port carries measurable event risk for this fleet.
                    </EmptyNote>
                  )
                ) : null}
              </FloatPanel>

              {selected ? (
                <FloatPanel
                  title={selected.name}
                  note={<span className="num">{selected.vessel_id}</span>}
                  onClose={() => setSelectedVessel(null)}
                  className="max-h-[300px] shrink-0"
                >
                  <PanelSection title="Particulars">
                    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10.5px]">
                      {(
                        [
                          ["Class", selected.vessel_class],
                          ["LOA", `${selected.loa_m.toFixed(0)} m`],
                          ["Draught", `${selected.draught_m.toFixed(1)} m`],
                          ["Capacity", `${selected.capacity_teu.toLocaleString()} TEU`],
                          ["Free slots", `${selected.available_teu.toFixed(0)} TEU`],
                          ["Speed", `${selected.service_speed_kn.toFixed(1)} kn`],
                          ["Flag", selected.flag],
                          ["IMO", selected.imo ?? "none issued"],
                        ] as Array<[string, string]>
                      ).map(([label, value]) => (
                        <div key={label} className="flex items-baseline justify-between gap-2">
                          <span className="text-[var(--text-3)]">{label}</span>
                          <span className="num text-[var(--text)]">{value}</span>
                        </div>
                      ))}
                    </div>
                  </PanelSection>
                  {selectedRows.length ? (
                    <PanelSection title="Exposure" right={`${selectedRows.length}`}>
                      {selectedRows.map((row) => (
                        <div
                          key={row.eventId}
                          className="border-b border-[var(--line)]/50 py-1 last:border-0"
                        >
                          <div className="truncate text-[10.5px] text-[var(--text-2)]">
                            {row.eventTitle}
                          </div>
                          <p className="mt-[2px] text-[9.5px] leading-snug text-[var(--text-3)]">
                            {row.actionBasis}
                          </p>
                        </div>
                      ))}
                    </PanelSection>
                  ) : (
                    <EmptyNote>No live event reaches this vessel.</EmptyNote>
                  )}
                </FloatPanel>
              ) : null}
            </div>
          </>
        }
      />
    </div>
  );
}
