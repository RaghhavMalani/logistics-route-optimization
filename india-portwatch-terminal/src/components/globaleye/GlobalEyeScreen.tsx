/**
 * The Global Eye workspace, shared by all three roles that get one.
 *
 * The layout is the same everywhere because the question is the same -- what is
 * happening, and what does it do to me. What changes is the `scope`:
 *
 *   national   every event, ranked by severity × corroboration.
 *   company    filtered to events that reach this fleet, with vessel exposure.
 *   port       filtered to events that reach this port.
 *
 * Map-first, like every other primary surface. Events sit on the chart at their
 * chokepoint or their reported position, with the corridor from the chokepoint
 * to each exposed port drawn as water. The register and the impact chain are
 * floating panels, so the geography stays the thing being read.
 */

import { useMemo, useState } from "react";

import { useWorkspace } from "@/auth/AuthProvider";
import { EmptyNote, FloatPanel, PanelSection, PanelTabs } from "@/components/command/panels";
import { TimeTransport } from "@/components/command/TimeTransport";
import { EnvironmentLegend } from "@/components/command/TrafficFilters";
import { useWorkspaceMap } from "@/components/command/useWorkspaceMap";
import { Pill, formatUtc } from "@/components/kit/primitives";
import { ScreenFallback } from "@/components/kit/states";
import { MaritimeMap } from "@/components/map/MaritimeMap";
import { CHOKEPOINT_BY_CODE } from "@/lib/maritime/chokepoints";
import { seaRoute } from "@/lib/maritime/searoutes";
import { cn } from "@/lib/utils";
import { useEventImpact, useGlobalEvents, useGlobalExposure } from "@/services/os-hooks";
import type { EventImpact, GlobalEvent } from "@/types/portwatch-os";
import {
  ActionList,
  EventRow,
  ImpactChain,
  PortExposureRow,
  ProbabilityBadge,
  SourceList,
  VesselExposureRow,
  exposureTone,
  groupTone,
  severityTone,
} from "./EventPanels";

export type GlobalEyeScope = "national" | "company" | "port";

/**
 * Event and corridor geometry for the chart.
 *
 * Corridors are catalogue legs from the chokepoint to each exposed port, so a
 * line's length on the chart is the length of the passage it represents. An
 * event with no mapped chokepoint contributes a marker and no corridor, and the
 * panel says how many those are.
 */
function eventGeometry(impacts: EventImpact[], selectedId: string | null) {
  const events: GeoJSON.Feature[] = [];
  const routes: GeoJSON.Feature[] = [];
  let unroutable = 0;

  for (const impact of impacts) {
    const focused = selectedId === null || impact.eventId === selectedId;
    if (impact.coordinates) {
      events.push({
        type: "Feature",
        properties: {
          id: impact.eventId,
          title: impact.title,
          severity: impact.severity,
          color:
            impact.severity >= 0.7 ? "#d05a4c"
              : impact.severity >= 0.45 ? "#d3a02f" : "#4c9fcb",
          opacity: focused ? 0.95 : 0.35,
        },
        geometry: {
          type: "Point",
          coordinates: [impact.coordinates.lon, impact.coordinates.lat],
        },
      });
    }

    if (!focused) continue;
    for (const chokepoint of impact.chokepoints) {
      const choke = CHOKEPOINT_BY_CODE.get(chokepoint);
      if (!choke?.waypointId) continue;
      for (const port of impact.ports.slice(0, 5)) {
        const route = seaRoute(choke.waypointId, port.portCode);
        if (!route) {
          unroutable += 1;
          continue;
        }
        routes.push({
          type: "Feature",
          properties: {
            part: "exposure",
            id: `${impact.eventId}-${port.portCode}`,
            color:
              port.exposure >= 0.55 ? "#d05a4c"
                : port.exposure >= 0.3 ? "#d3a02f" : "#4c9fcb",
            width: 0.9 + port.exposure * 2.4,
            opacity: 0.3 + port.exposure * 0.5,
            label: `${choke.name} → ${port.portCode} · exposure ${port.exposure.toFixed(2)}`,
          },
          geometry: { type: "LineString", coordinates: route.path.coords },
        });
      }
    }
  }

  return {
    events: { type: "FeatureCollection" as const, features: events },
    routes: { type: "FeatureCollection" as const, features: routes },
    unroutable,
  };
}

export function GlobalEyeScreen({
  scope,
  title,
  portCode,
}: {
  scope: GlobalEyeScope;
  title: string;
  portCode?: string | null;
}) {
  const { companyId } = useWorkspace();
  const workspace = useWorkspaceMap({
    layerOverrides: { events: true, routes: true },
  });
  const scopedCompany = scope === "company" ? companyId : null;

  const exposure = useGlobalExposure({
    companyId: scopedCompany,
    portCode: scope === "port" ? portCode : null,
    limit: 24,
  });
  const events = useGlobalEvents({ limit: 60 });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<"chain" | "vessels" | "sources">("chain");

  const impacts = exposure.data?.impacts ?? [];
  const selected = useMemo(
    () => impacts.find((i) => i.eventId === selectedId) ?? impacts[0] ?? null,
    [impacts, selectedId],
  );

  const geometry = useMemo(
    () => eventGeometry(impacts, selected?.eventId ?? null),
    [impacts, selected?.eventId],
  );

  const portRisk = exposure.data?.portRisk ?? {};
  const rankedPorts = useMemo(
    () => Object.values(portRisk).sort((a, b) => b.risk - a.risk),
    [portRisk],
  );

  if (exposure.isLoading || exposure.isError) {
    return (
      <ScreenFallback
        title={title}
        context={<span>World events and their maritime exposure</span>}
        isLoading={exposure.isLoading}
        error={exposure.error}
        retry={() => void exposure.refetch()}
        label="Building the exposure graph"
      />
    );
  }

  const ingest = exposure.data?.ingest;
  const calibrated = exposure.data?.calibrationAvailable ?? false;
  const unclassified = ingest?.unclassified ?? 0;

  return (
    <div className="absolute inset-0">
      <h1 className="sr-only">{title}</h1>

      <MaritimeMap
        layers={{ ...workspace.layers, events: true, routes: true }}
        data={{
          ...workspace.data,
          events: geometry.events,
          routes: geometry.routes,
        }}
        weatherRaster={workspace.raster}
        windFrame={workspace.frame}
        showWind={workspace.showWind && workspace.layers.weather}
        vesselFilter={workspace.vesselFilter}
        labels={workspace.labels}
        selectedPortCode={workspace.selectedPortCode}
        onSelectPort={workspace.setSelectedPortCode}
        focus={workspace.focus}
        overlay={
          <>
            {/* ------------------------------------------------- register -- */}
            <div className="pointer-events-none absolute bottom-2.5 left-2.5 top-2.5 z-20 flex w-[300px] flex-col gap-2">
              <FloatPanel
                title="Event register"
                note={
                  <span className="num">
                    {impacts.length} of {ingest?.events ?? 0}
                  </span>
                }
                className="min-h-0 flex-1"
                testId="event-register"
                footer={
                  <>
                    {ingest?.rawItems ?? 0} feed items merged into {ingest?.events ?? 0} events
                    {unclassified
                      ? `; ${unclassified} carried no maritime-relevant classification`
                      : ""}
                    .{" "}
                    {calibrated
                      ? "Probabilities are calibrated against resolved outcomes."
                      : "No calibrated probability yet: severity and corroboration are shown instead."}
                  </>
                }
              >
                {impacts.length === 0 ? (
                  <EmptyNote>
                    No event in the current feed reaches this scope. That is a measured
                    absence, not a missing feed — {ingest?.events ?? 0} events were
                    ingested.
                  </EmptyNote>
                ) : (
                  impacts.map((impact) => (
                    <EventRow
                      key={impact.eventId}
                      event={impact}
                      exposure={impact.worstExposure || null}
                      selected={selected?.eventId === impact.eventId}
                      onSelect={() => {
                        setSelectedId(impact.eventId);
                        if (impact.coordinates) {
                          workspace.flyTo(
                            [impact.coordinates.lon, impact.coordinates.lat],
                            4.6,
                          );
                        }
                      }}
                    />
                  ))
                )}
              </FloatPanel>
            </div>

            {/* -------------------------------------------------- legend -- */}
            <div className="pointer-events-none absolute bottom-2.5 left-[314px] z-20 w-[248px]">
              <EnvironmentLegend workspace={workspace} frame={workspace.frame} />
            </div>

            {/* ----------------------------------------------- transport -- */}
            <div className="pointer-events-none absolute bottom-2.5 left-[574px] right-[364px] z-20">
              <TimeTransport timeline={workspace.timeline} weatherAt={workspace.weatherAt} />
            </div>

            {/* ------------------------------------------------ inspector -- */}
            <div className="pointer-events-none absolute bottom-2.5 right-2.5 top-2.5 z-20 flex w-[350px] flex-col gap-2">
              {selected ? (
                <FloatPanel
                  title={selected.categoryLabel}
                  note={<Pill tone={severityTone(selected.severity)}>
                    sev {selected.severity.toFixed(2)}
                  </Pill>}
                  className="min-h-0 flex-1"
                  scroll
                  testId="event-inspector"
                  footer={
                    selected.geolocationBasis === "chokepoint_centroid"
                      ? "Position is the chokepoint centroid, not a reported coordinate."
                      : selected.geolocationBasis === "unlocated"
                        ? "This event carries no position and is not drawn on the chart."
                        : undefined
                  }
                >
                  <div className="border-b border-[var(--line)] px-2 py-2">
                    <p className="text-[12px] leading-snug text-[var(--text)]">
                      {selected.title}
                    </p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[9.5px] text-[var(--text-3)]">
                      {selected.region ? <Pill tone="neutral">{selected.region}</Pill> : null}
                      <span className="num">first seen {formatUtc(selected.firstSeen)}</span>
                      <span className="num">last {formatUtc(selected.lastSeen)}</span>
                      <span className="num" title="Recency weight applied to this event's exposure">
                        decay {selected.decay.toFixed(2)}
                      </span>
                    </div>
                    <div className="mt-2">
                      <ProbabilityBadge event={selected} />
                    </div>
                  </div>

                  <PanelTabs
                    value={tab}
                    onChange={setTab}
                    tabs={[
                      { value: "chain", label: "Chain" },
                      { value: "vessels", label: "Vessels", count: selected.vessels.length },
                      { value: "sources", label: "Sources", count: selected.sourceCount },
                    ]}
                  />

                  {tab === "chain" ? (
                    <>
                      <ImpactChain impact={selected} />
                      <PanelSection title="Ports exposed" right={`${selected.ports.length}`}>
                        {selected.ports.length ? (
                          selected.ports.map((port) => (
                            <PortExposureRow key={port.portCode} row={port} />
                          ))
                        ) : (
                          <EmptyNote>No Indian port is reached by an exposed lane.</EmptyNote>
                        )}
                      </PanelSection>
                      <PanelSection title="Actions" right={`${selected.actions.length}`}>
                        <ActionList actions={selected.actions} />
                      </PanelSection>
                      {selected.notes.length ? (
                        <PanelSection title="What this does not say">
                          <ul className="space-y-1">
                            {selected.notes.map((note) => (
                              <li
                                key={note}
                                className="text-[10px] leading-snug text-[var(--text-3)]"
                              >
                                {note}
                              </li>
                            ))}
                          </ul>
                        </PanelSection>
                      ) : null}
                    </>
                  ) : null}

                  {tab === "vessels" ? (
                    selected.vessels.length ? (
                      <div>
                        {selected.vessels.map((vessel) => (
                          <VesselExposureRow key={vessel.vesselId} row={vessel} />
                        ))}
                      </div>
                    ) : (
                      <EmptyNote>
                        No fleet is in scope for this view, so vessel-level exposure is not
                        computed. Sign in as a shipping company to see fleet exposure.
                      </EmptyNote>
                    )
                  ) : null}

                  {tab === "sources" ? (
                    <PanelSection title="Reports" right={`${selected.reportCount}`}>
                      <SourceList event={selected} />
                    </PanelSection>
                  ) : null}
                </FloatPanel>
              ) : (
                <FloatPanel title="Exposure" className="min-h-0 flex-1">
                  <EmptyNote>Select an event to trace its impact chain.</EmptyNote>
                </FloatPanel>
              )}

              <FloatPanel
                title="Ports by event risk"
                note={<span className="num">{rankedPorts.length}</span>}
                collapsible
                defaultOpen={rankedPorts.length > 0}
                className="max-h-[240px] shrink-0"
                footer="Combined across live events with a noisy-OR, so two independent 0.50 exposures give 0.75 rather than certainty."
              >
                {rankedPorts.length ? (
                  <div className="px-2 py-1">
                    {rankedPorts.slice(0, 12).map((port) => (
                      <div
                        key={port.portCode}
                        className="flex items-baseline gap-2 border-b border-[var(--line)]/50 py-[3px] last:border-0"
                      >
                        <span className="num w-[46px] shrink-0 text-[10.5px] text-[var(--text-2)]">
                          {port.portCode}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-[10.5px] text-[var(--text)]">
                          {port.portName}
                        </span>
                        <span className="num shrink-0 text-[9.5px] text-[var(--text-3)]">
                          {port.events.length} ev
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
                    ))}
                  </div>
                ) : (
                  <EmptyNote>No port carries measurable event risk right now.</EmptyNote>
                )}
              </FloatPanel>
            </div>
          </>
        }
      />
    </div>
  );
}
