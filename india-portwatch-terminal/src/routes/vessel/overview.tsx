import { useWorkspaceTarget } from "@/components/app/use-workspace-target";
import { DataNowSources, WeatherDataNow, DatedSource } from "@/components/app/SourceHealth";
/**
 * The vessel operator's bridge view.
 *
 * The operator's own ship is the emphasised mark, but it is never the only one:
 * a passage plan made without the traffic around it is not a passage plan. The
 * surrounding fleet stays on the chart at lower weight, the own route is drawn
 * with its forecast weather exposure, and where the routing artefact recommends
 * a different call that alternative is drawn beside it so the two can be
 * compared as geometry rather than as two numbers in a table.
 */

import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";

import { AgentConsole } from "@/components/agent/AgentConsole";
import {
  useFixes,
  useTraffic,
  useTrafficTick,
} from "@/components/app/traffic-context";
import {
  MaritimeSearch,
  type SearchHit,
} from "@/components/command/MaritimeSearch";
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
import { ObservedSelection } from "@/components/command/ObservedVesselInspector";
import {
  EmptyNote,
  FloatPanel,
  PanelSection,
  PanelTabs,
} from "@/components/command/panels";
import { selectionGeometry } from "@/components/command/selection-geometry";
import { useWorkspaceMap } from "@/components/command/useWorkspaceMap";
import { Num, Pill } from "@/components/kit/primitives";
import { ScreenFallback } from "@/components/kit/states";
import { MaritimeMap } from "@/components/map/MaritimeMap";
import { formatBearing } from "@/lib/maritime/geo";
import { BridgePassage } from "@/components/command/BridgePassage";
import { useAuth } from "@/auth/AuthProvider";
import { useAdvisories } from "@/services/os-hooks";
import { WorkspaceHandoffCard } from "@/components/advisory/WorkspaceHandoffCard";
import { waypoint } from "@/lib/maritime/searoutes";
import { NAV_STATUS_LABEL, VESSEL_CLASSES } from "@/lib/maritime/traffic-types";
import { nearbyTraffic, STATUS_TONE } from "@/lib/maritime/traffic-views";
import { useFleet } from "@/services/hooks";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/vessel/overview")({
  head: () => ({ meta: [{ title: "PortWatch X — Vessel Bridge" }] }),
  component: VesselBridge,
});

function VesselBridge() {
  const workspace = useWorkspaceMap();
  const { source: trafficSource } = useTraffic();
  const fleet = useFleet();
  const { identityHeaders } = useAuth();
  const accepted = useAdvisories(identityHeaders, { state: "accepted" });
  const fixes = useFixes(1);
  const at = useTrafficTick(1);
  const [railTab, setRailTab] = useState<"now" | "traffic" | "scenarios">("now");
  const [following, setFollowing] = useState(true);
  const targetPort = useWorkspaceTarget("port");
  const targetHull = useWorkspaceTarget("hull");
  useEffect(() => {
    if (targetPort || targetHull) setFollowing(false);
  }, [targetPort, targetHull]);
  // The follow camera pulls back on a narrower frame for the same reason the
  // port view does: the point is the traffic around the ship, not the ship.
  const followZoom =
    typeof window === "undefined" || window.innerWidth >= 1600 ? 7 : 6.4;

  const owned = useMemo(() => fixes.filter((fix) => fix.owned), [fixes]);

  // The operator lands on their own bridge, not on an empty selection.
  const { selectedPortCode, selectedVesselId, setSelectedVesselId } = workspace;
  useEffect(() => {
    if (!targetPort && !selectedPortCode && !selectedVesselId && owned.length) {
      setSelectedVesselId(owned[0].id);
    }
  }, [owned, selectedPortCode, selectedVesselId, setSelectedVesselId, targetPort]);

  const selectedFix = useMemo(
    () =>
      fixes.find((fix) => fix.id === workspace.selectedVesselId) ??
      owned[0] ??
      null,
    [fixes, owned, workspace.selectedVesselId],
  );

  const ownRow = useMemo(() => {
    if (!selectedFix?.owned) return null;
    const id = selectedFix.id.replace(/^own:/, "");
    return (fleet.data ?? []).find((row) => row.id === id) ?? null;
  }, [fleet.data, selectedFix]);

  const exposure = useRouteExposure(selectedFix, workspace.timeline);
  const geometry = useMemo(
    () =>
      selectionGeometry(selectedFix, exposure, {
        alternativeTo: ownRow?.reroute ? ownRow.recommendedPortCode : null,
      }),
    [exposure, ownRow, selectedFix],
  );

  const contacts = useMemo(
    () => (selectedFix ? nearbyTraffic(selectedFix, fixes, 60, 10) : []),
    [fixes, selectedFix],
  );

  // Own ships and every named contact stay out of the merge and keep their
  // labels: they are the reason this screen exists.
  const pinnedIds = useMemo(
    () =>
      new Set([
        ...owned.map((fix) => fix.id),
        ...contacts.map((contact) => contact.fix.id),
      ]),
    [contacts, owned],
  );

  if (fleet.isLoading || fleet.isError) {
    return (
      <ScreenFallback
        title="Bridge"
        context={
          <span>Own vessel, surrounding traffic and passage weather</span>
        }
        isLoading={fleet.isLoading}
        error={fleet.error}
        retry={() => void fleet.refetch()}
        label="Acquiring fleet picture"
      />
    );
  }

  const recommendation = accepted.data?.advisories
    .filter((row) => row.state === "accepted" && row.recipientVesselId === ownRow?.id)
    .sort((a, b) => (b.respondedAt ?? "").localeCompare(a.respondedAt ?? ""))
    .find((row) => typeof row.recommendation.recommendedSpeedKn === "number");
  const recommendedSpeed = recommendation?.recommendation.recommendedSpeedKn;
  const onPick = (hit: SearchHit) => {
    if (hit.kind === "vessel") {
      workspace.setSelectedVesselId(hit.id);
      setFollowing(false);
    }
    if (hit.kind === "port") {
      workspace.setSelectedPortCode(hit.id);
      setFollowing(false);
    }
    workspace.flyTo([hit.lon, hit.lat], hit.kind === "port" ? 11.5 : 8.5);
  };

  return (
    <div className="absolute inset-0">
      <h1 className="sr-only">Vessel Bridge</h1>

      <MaritimeMap
        layers={workspace.layers}
        data={{ ...workspace.data, ...geometry }}
        weatherRaster={workspace.raster}
        windFrame={workspace.frame}
        showWind={workspace.showWind && workspace.layers.weather}
        vesselFilter={workspace.vesselFilter}
        pinnedIds={pinnedIds}
        labels={workspace.labels}
        selectedVesselId={workspace.selectedVesselId}
        onSelectObserved={workspace.setSelectedObservedMmsi}
        onSelectVessel={(id) => {
          workspace.setSelectedVesselId(id);
          setFollowing(false);
        }}
        onHoverVessel={workspace.setHoveredVesselId}
        selectedPortCode={workspace.selectedPortCode}
        onSelectPort={(code) => {
          workspace.setSelectedPortCode(code);
          setFollowing(false);
        }}
        focus={
          following && selectedFix
            ? {
                center: [selectedFix.lon, selectedFix.lat],
                zoom: followZoom,
                token: Math.floor(at / 5000),
              }
            : workspace.focus
        }
        renderHoverCard={(fix) => <VesselHoverCard fix={fix} />}
        overlay={
          <>
            <div data-map-label-occluder="children" className="pointer-events-none absolute left-2.5 top-2.5 z-20 flex max-h-[calc(100%-110px)] w-[216px] flex-col gap-2">
              <MaritimeSearch
                ports={workspace.ports}
                onPick={onPick}
                placeholder="Search traffic or port"
              />
              <TrafficFilters workspace={workspace} />
            </div>

            <div data-map-label-occluder="children" className="pointer-events-none absolute right-[346px] top-2.5 z-30 max-[900px]:hidden">
              <AgentConsole />
            </div>

            <div data-map-label-occluder="children" className="pointer-events-none absolute bottom-2.5 left-2.5 z-20 flex w-[248px] flex-col gap-1.5">
              <VesselClassLegend />
              <EnvironmentLegend
                workspace={workspace}
                frame={workspace.frame}
              />
            </div>

            <div
              data-map-camera-inset="bottom"
              className="pointer-events-none absolute bottom-2.5 left-[272px] right-[336px] z-20"
            >
              <TimeTransport
                timeline={workspace.timeline}
                weatherAt={workspace.weatherAt}
                className="flex-wrap [&>div:last-child]:basis-full"
              />
            </div>

            <aside
              aria-label="Vessel Bridge tools"
              data-testid="workspace-right-panel"
              data-map-camera-inset="right"
              className="pw-workspace-rail pointer-events-auto absolute bottom-2.5 right-2.5 top-2.5 z-20 flex w-[322px] flex-col overflow-hidden"
            >
              <PanelTabs value={railTab} onChange={setRailTab} tabs={[
                { value: "now", label: "Now" },
                { value: "traffic", label: "Traffic" },
                { value: "scenarios", label: "Scenarios" },
              ]} />
              {railTab === "now" ? <WorkspaceHandoffCard view="vessel" /> : null}
              {railTab === "now" && selectedFix?.owned ? (
                <BridgePassage
                  name={selectedFix.name}
                  origin={ownRow?.originPortCode}
                  destination={ownRow?.intendedPortCode}
                  eta={selectedFix.etaMs}
                  at={at}
                  recommendedSpeed={typeof recommendedSpeed === "number" && Number.isFinite(recommendedSpeed) && recommendedSpeed > 0 ? recommendedSpeed : undefined}
                  exposure={exposure}
                  timeline={workspace.timeline}
                />
              ) : null}
              {railTab === "traffic" && owned.length > 0 ? (
                <FloatPanel
                  title="Own fleet"
                  note={`${owned.length} vessels`}
                  className="shrink-0"
                >
                  <ul className="p-1">
                    {owned.map((fix) => (
                      <li key={fix.id}>
                        <button
                          type="button"
                          onClick={() => {
                            workspace.setSelectedVesselId(fix.id);
                            setFollowing(true);
                            setRailTab("now");
                          }}
                          className={cn(
                            "grid w-full grid-cols-[1fr_50px_44px] items-center gap-2 rounded-[2px] px-1.5 py-[3px] text-left",
                            workspace.selectedVesselId === fix.id
                              ? "bg-[var(--panel-3)]"
                              : "hover:bg-[var(--panel-2)]",
                          )}
                        >
                          <span className="truncate text-[11.5px] text-[var(--text)]">
                            {fix.name}
                          </span>
                          <span className="num text-right text-[10.5px] text-[var(--text-2)]">
                            {fix.sogKn.toFixed(1)}kn
                          </span>
                          <span className="flex justify-end">
                            <Pill tone={STATUS_TONE[fix.status]}>
                              {NAV_STATUS_LABEL[fix.status]}
                            </Pill>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </FloatPanel>
              ) : null}

              {railTab === "traffic" && selectedFix && contacts.length === 0 ? (
                <div className="pw-handoff-card pointer-events-auto px-3 py-2 text-xs text-[var(--text-3)]">
                  No contacts inside 60 nm.
                </div>
              ) : null}
              {railTab === "traffic" && selectedFix && contacts.length > 0 ? (
                <FloatPanel
                  title="Traffic around own ship"
                  note={`${contacts.length} within 60 nm`}
                  className="min-h-0 flex-1"
                >
                  <PanelSection title="Contacts">
                      <ul className="space-y-[2px]">
                        {contacts.slice(0, 6).map((contact) => (
                          <li key={contact.fix.id}>
                            <button
                              type="button"
                              onClick={() => {
                                workspace.setSelectedVesselId(contact.fix.id);
                                setFollowing(false);
                                setRailTab("now");
                              }}
                              className="grid w-full grid-cols-[1fr_40px_38px] items-baseline gap-1.5 rounded-[2px] px-1 py-[2px] text-left hover:bg-[var(--panel-3)]"
                            >
                              <span className="min-w-0 truncate text-[10.5px] text-[var(--text-2)]">
                                <span
                                  aria-hidden
                                  className="mr-1 inline-block h-[6px] w-[6px] rounded-[1px] align-middle"
                                  style={{
                                    background:
                                      VESSEL_CLASSES[contact.fix.vesselClass]
                                        .color,
                                  }}
                                />
                                {contact.fix.name}
                              </span>
                              <span className="num text-right text-[10px] text-[var(--text-3)]">
                                {contact.rangeNm.toFixed(1)}nm
                              </span>
                              <span className="num text-right text-[10px] text-[var(--text-3)]">
                                {formatBearing(contact.bearing)}
                              </span>
                            </button>
                            <div className="px-1 pb-[2px] text-[10px] text-[var(--text-3)]">
                              {waypoint(contact.fix.destinationId)?.name.split(
                                " (",
                              )[0] ?? "—"}{" "}
                              ·{" "}
                              <Num
                                value={contact.fix.sogKn}
                                digits={1}
                                unit="kn"
                              />
                              {contact.computable ? (
                                <span
                                  className={cn(
                                    "ml-1",
                                    contact.cpa.cpaNm < 1 &&
                                      contact.cpa.tcpaMinutes > 0
                                      ? "text-[var(--warn)]"
                                      : "",
                                  )}
                                >
                                  CPA {contact.cpa.cpaNm.toFixed(1)}nm
                                </span>
                              ) : null}
                            </div>
                          </li>
                        ))}
                      </ul>
                  </PanelSection>
                </FloatPanel>
              ) : null}

              {railTab === "now" ? (
                <>
              <ObservedSelection
                workspace={workspace}
                className="min-h-0 flex-1"
              />
              {selectedFix ? (
                <VesselInspector
                  fix={selectedFix}
                  ports={workspace.ports}
                  timeline={workspace.timeline}
                  ownRow={ownRow}
                  onClose={() =>
                    workspace.setSelectedVesselId(owned[0]?.id ?? null)
                  }
                  onFollow={() => setFollowing((v) => !v)}
                  following={following}
                  onIsolate={() =>
                    workspace.setIsolate(
                      workspace.filters.isolate ? null : selectedFix.id,
                    )
                  }
                  isolated={workspace.filters.isolate === selectedFix.id}
                  onSelectVessel={(id) => {
                    workspace.setSelectedVesselId(id);
                    setFollowing(false);
                  }}
                  className="min-h-0 flex-1"
                />
              ) : (
                <FloatPanel title="Own fleet" className="min-h-0 flex-1">
                  <EmptyNote>
                    The routing artefact carried no vessel for this operator in
                    this run.
                  </EmptyNote>
                </FloatPanel>
              )}
                </>
              ) : null}
              {railTab === "scenarios" ? (
                <div className="p-3 text-xs">
                  <p className="mb-2">Review recommendations and their modelled passage outcomes.</p>
                  <a href="/vessel/advisories" className="font-medium underline">Open the advisory register</a>
                </div>
              ) : null}
              {railTab === "now" ? (
                <div className="shrink-0 p-2 border-t border-[var(--line)] text-xs leading-snug">
                  <strong>Data now</strong> · Weather{" "}
                  <WeatherDataNow />{" "}
                  · Port activity <DatedSource id="imf-portwatch-data" /> · Traffic{" "}
                  {trafficSource.info.label}
                  <DataNowSources opensAbove />
                </div>
              ) : null}
            </aside>


          </>
        }
      />
    </div>
  );
}
