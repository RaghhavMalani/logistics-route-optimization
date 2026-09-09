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

import { useFixes, useTrafficTick } from "@/components/app/traffic-context";
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
import { Num, Pill } from "@/components/kit/primitives";
import { ScreenFallback } from "@/components/kit/states";
import { MaritimeMap } from "@/components/map/MaritimeMap";
import { formatBearing } from "@/lib/maritime/geo";
import { waypoint } from "@/lib/maritime/searoutes";
import { NAV_STATUS_LABEL, VESSEL_CLASSES } from "@/lib/maritime/traffic-types";
import { nearbyTraffic, STATUS_TONE } from "@/lib/maritime/traffic-views";
import { useFleet } from "@/services/hooks";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/vessel/overview")({ component: VesselBridge });

function VesselBridge() {
  const workspace = useWorkspaceMap();
  const fleet = useFleet();
  const fixes = useFixes(1);
  const at = useTrafficTick(1);
  const [following, setFollowing] = useState(true);

  const owned = useMemo(() => fixes.filter((fix) => fix.owned), [fixes]);

  // The operator lands on their own bridge, not on an empty selection.
  const { selectedVesselId, setSelectedVesselId } = workspace;
  useEffect(() => {
    if (!selectedVesselId && owned.length) setSelectedVesselId(owned[0].id);
  }, [owned, selectedVesselId, setSelectedVesselId]);

  const selectedFix = useMemo(
    () => fixes.find((fix) => fix.id === workspace.selectedVesselId) ?? owned[0] ?? null,
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
    () => new Set([...owned.map((fix) => fix.id), ...contacts.map((contact) => contact.fix.id)]),
    [contacts, owned],
  );

  if (fleet.isLoading || fleet.isError) {
    return (
      <ScreenFallback
        title="Bridge"
        context={<span>Own vessel, surrounding traffic and passage weather</span>}
        isLoading={fleet.isLoading}
        error={fleet.error}
        retry={() => void fleet.refetch()}
        label="Acquiring fleet picture"
      />
    );
  }

  const onPick = (hit: SearchHit) => {
    if (hit.kind === "vessel") {
      workspace.setSelectedVesselId(hit.id);
      setFollowing(false);
    }
    workspace.flyTo([hit.lon, hit.lat], 8.5);
  };

  return (
    <div className="absolute inset-0">
      <h1 className="sr-only">Fleet Bridge</h1>

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
        onSelectVessel={(id) => {
          workspace.setSelectedVesselId(id);
          setFollowing(false);
        }}
        onHoverVessel={workspace.setHoveredVesselId}
        onSelectPort={workspace.setSelectedPortCode}
        focus={
          following && selectedFix
            ? {
                center: [selectedFix.lon, selectedFix.lat],
                zoom: 7,
                token: Math.floor(at / 5000),
              }
            : workspace.focus
        }
        renderHoverCard={(fix) => <VesselHoverCard fix={fix} />}
        overlay={
          <>
            <div className="pointer-events-none absolute left-2.5 top-2.5 z-20 flex max-h-[calc(100%-110px)] w-[216px] flex-col gap-2">
              <MaritimeSearch
                ports={workspace.ports}
                onPick={onPick}
                placeholder="Search traffic or port"
              />
              <TrafficFilters workspace={workspace} />
            </div>

            <div className="pointer-events-none absolute bottom-2.5 left-2.5 z-20 flex w-[248px] flex-col gap-1.5">
              <VesselClassLegend />
              <EnvironmentLegend workspace={workspace} frame={workspace.frame} />
            </div>

            <div className="pointer-events-none absolute bottom-2.5 left-[272px] right-[336px] z-20">
              <TimeTransport timeline={workspace.timeline} weatherAt={workspace.weatherAt} />
            </div>

            <div className="pointer-events-none absolute bottom-2.5 right-2.5 top-2.5 z-20 flex w-[322px] flex-col gap-2">
              {owned.length > 1 ? (
                <FloatPanel title="Own fleet" note={`${owned.length} vessels`} className="shrink-0">
                  <ul className="p-1">
                    {owned.map((fix) => (
                      <li key={fix.id}>
                        <button
                          type="button"
                          onClick={() => {
                            workspace.setSelectedVesselId(fix.id);
                            setFollowing(true);
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

              {selectedFix ? (
                <VesselInspector
                  fix={selectedFix}
                  ports={workspace.ports}
                  timeline={workspace.timeline}
                  ownRow={ownRow}
                  onClose={() => workspace.setSelectedVesselId(owned[0]?.id ?? null)}
                  onFollow={() => setFollowing((v) => !v)}
                  following={following}
                  onIsolate={() =>
                    workspace.setIsolate(workspace.filters.isolate ? null : selectedFix.id)
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
                    The routing artefact carried no vessel for this operator in this run.
                  </EmptyNote>
                </FloatPanel>
              )}
            </div>

            {/* --------------------------------------------- traffic around -- */}
            {selectedFix ? (
              <div className="pointer-events-none absolute left-2.5 top-2.5 z-20 ml-[224px] w-[252px]">
                <FloatPanel
                  title="Traffic around own ship"
                  note={`${contacts.length} within 60 nm`}
                  collapsible
                  className="max-h-[300px]"
                >
                  {contacts.length === 0 ? (
                    <EmptyNote>No contact inside 60 nautical miles.</EmptyNote>
                  ) : (
                    <PanelSection title="Contacts">
                      <ul className="space-y-[2px]">
                        {contacts.map((contact) => (
                          <li key={contact.fix.id}>
                            <button
                              type="button"
                              onClick={() => {
                                workspace.setSelectedVesselId(contact.fix.id);
                                setFollowing(false);
                              }}
                              className="grid w-full grid-cols-[1fr_40px_38px] items-baseline gap-1.5 rounded-[2px] px-1 py-[2px] text-left hover:bg-[var(--panel-3)]"
                            >
                              <span className="min-w-0 truncate text-[10.5px] text-[var(--text-2)]">
                                <span
                                  aria-hidden
                                  className="mr-1 inline-block h-[6px] w-[6px] rounded-[1px] align-middle"
                                  style={{
                                    background: VESSEL_CLASSES[contact.fix.vesselClass].color,
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
                            <div className="px-1 pb-[2px] text-[9px] text-[var(--text-3)]">
                              {waypoint(contact.fix.destinationId)?.name.split(" (")[0] ?? "—"} ·{" "}
                              <Num value={contact.fix.sogKn} digits={1} unit="kn" />
                              {contact.computable ? (
                                <span
                                  className={cn(
                                    "ml-1",
                                    contact.cpa.cpaNm < 1 && contact.cpa.tcpaMinutes > 0
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
                  )}
                </FloatPanel>
              </div>
            ) : null}
          </>
        }
      />
    </div>
  );
}
