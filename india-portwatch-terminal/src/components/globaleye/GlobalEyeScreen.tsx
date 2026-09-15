/**
 * Global Eye: the world, and what is happening to it.
 *
 * This screen used to be a map with a 300px register down one side and a 350px
 * inspector down the other, both filled with 9px tables. That is a dashboard
 * that happens to contain a map, and it reads as static however live the data
 * underneath it is.
 *
 * The arrangement here is different in one specific way: **the geography is the
 * explanation**. Selecting an event does not fill a panel with rows -- it plays
 * the consequence across the water. The threatened chokepoint lights, the lanes
 * that genuinely transit it draw, the exposed hulls come up, and the ports the
 * delay lands on take a ring whose size is the pressure the engine computed.
 * The panels that remain are an action queue and an evidence drawer, and both
 * are narrow, capped, and dismissible.
 *
 * Two rules hold:
 *
 * *   **Nothing here computes consequence.** Every magnitude, every colour
 *     weight and every ring radius is read from a cascade the server produced.
 * *   **Time is one control.** Scrubbing the transport re-queries the same
 *     temporal graph, so a lapsed event visibly stops reaching anything rather
 *     than being filtered out by the client.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth, useWorkspace } from "@/auth/AuthProvider";
import { ObservedSelection } from "@/components/command/ObservedVesselInspector";
import { EmptyNote, FloatPanel } from "@/components/command/panels";
import { TimeTransport } from "@/components/command/TimeTransport";
import { EnvironmentLegend } from "@/components/command/TrafficFilters";
import { useWorkspaceMap } from "@/components/command/useWorkspaceMap";
import { Pill } from "@/components/kit/primitives";
import { ScreenFallback } from "@/components/kit/states";
import { MaritimeMap } from "@/components/map/MaritimeMap";
import { cascadeLayers } from "@/lib/maritime/cascade-layers";
import { cn } from "@/lib/utils";
import {
  useAttention,
  useAttentionItem,
  useWorldCascade,
  useWorldCascades,
} from "@/services/os-hooks";
import type { AttentionItem, WorldCascade } from "@/types/portwatch-os";

import { CommandBar } from "@/components/copilot/CommandBar";
import { DecisionPanel } from "@/components/decision/DecisionPanel";
import { SignalHealth } from "@/components/fabric/SignalHealth";
import {
  decisionLabels,
  decisionLayers,
  decisionBounds,
} from "@/lib/maritime/decision-layers";
import {
  type ScenarioAssumptions,
  useCreateDecision,
  useDecision,
} from "@/services/decisions";
import { LENS_DEFINITIONS, lensLayers } from "@/lib/maritime/lenses";
import { LENSES, useWorld, type Lens } from "@/world/WorldContext";

import { ActionRail } from "./ActionRail";
import { SecurityLensReport, TradeExposureReport } from "./LensReports";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { useCascadeReveal } from "./useCascadeReveal";

export type GlobalEyeScope = "national" | "company" | "port";

/** The horizons the projection offers, in hours from now. */
const PROJECTION_OFFSETS = [0, 3, 6, 12, 24, 48, 72] as const;

/** Room for the action rail on the left and the decision panel on the right. */
const DECISION_PADDING = { top: 56, bottom: 72, left: 372, right: 412 };

export function GlobalEyeScreen({
  scope,
  title,
  portCode,
}: {
  scope: GlobalEyeScope;
  title: string;
  portCode?: string | null;
}) {
  const workspace = useWorkspaceMap({
    layerOverrides: { events: true, routes: true, cascade: true },
  });
  const { identityHeaders } = useAuth();
  const { role } = useWorkspace();

  // Selection, lens and horizon live in the world context rather than here, so
  // the Copilot can drive them. A component that owned this privately could not
  // be moved from outside, which is what left the spatial loop open.
  const world = useWorld();
  const {
    eventId: selectedEventId,
    projectionHours,
    lens,
    evidenceFor: selectedAttentionId,
    attentionSubjects,
  } = world;
  const evidenceOpen = Boolean(selectedAttentionId);

  // The instant the whole world is queried at. One control, one clock: the
  // cascade, the attention queue and the map all read the same moment.
  const at = useMemo(() => {
    if (projectionHours === 0) return null;
    return new Date(Date.now() + projectionHours * 3_600_000).toISOString();
  }, [projectionHours]);

  const cascades = useWorldCascades(at);
  const attention = useAttention(identityHeaders, at, 5);

  const live = useMemo(
    () => (cascades.data?.cascades ?? []).filter((c) => c.live),
    [cascades.data],
  );

  // Default to the worst live cascade so the screen opens with the world
  // already saying something, rather than waiting to be asked.
  useEffect(() => {
    if (selectedEventId || live.length === 0) return;
    world.selectEvent(live[0].eventId);
  }, [live, selectedEventId, world]);

  const cascade = useWorldCascade(selectedEventId, identityHeaders, at);
  const reveal = useCascadeReveal(
    selectedEventId ? `${selectedEventId}@${projectionHours}` : null,
  );

  const affected = cascade.data?.affected;
  const layers = useMemo(
    () => cascadeLayers(affected, reveal.reveal),
    [affected, reveal.reveal],
  );

  // ------------------------------------------------------------ decision --
  // "What should we do?" builds a DecisionProblem from the same frozen world
  // this cascade came from. While one is open the map draws its options
  // instead of the cascade, and switching option switches the world branch.
  const createDecision = useCreateDecision(identityHeaders);
  const decision = useDecision(world.decisionId);
  const decisionOpen = Boolean(world.decisionId);
  const decisionLayerData = useMemo(
    () =>
      decisionLayers(
        decision.data,
        world.decisionOptionId,
        world.decisionCompare,
      ),
    [decision.data, world.decisionOptionId, world.decisionCompare],
  );
  const decisionLabelRows = useMemo(
    () =>
      decisionLabels(
        decision.data,
        world.decisionOptionId,
        world.decisionCompare,
      ),
    [decision.data, world.decisionOptionId, world.decisionCompare],
  );
  const mapLabels = useMemo(
    () =>
      decisionOpen
        ? [...workspace.labels, ...decisionLabelRows]
        : workspace.labels,
    [decisionOpen, workspace.labels, decisionLabelRows],
  );
  const decide = useCallback(
    (item: AttentionItem) => {
      const eventId = item.cascadeId.split(":").pop() ?? "";
      createDecision.mutate(
        {
          domain: "vessel",
          eventId,
          vesselId: item.subjectId,
          attentionId: item.attentionId,
          at,
          mode: "DEMO",
        },
        {
          onSuccess: (problem) => {
            world.selectVessel(item.subjectId);
            world.openDecision(
              problem.decisionId,
              problem.recommendation?.optionId ?? problem.baselineOptionId,
              true,
            );
          },
        },
      );
    },
    [at, createDecision, world],
  );
  // The same decision, priced again with the operator's scenario figures. A
  // new problem, not an edit: the computed one stays as it was in the ledger.
  const recompute = useCallback(
    (assumptions: ScenarioAssumptions) => {
      const current = decision.data;
      if (!current) return;
      // The evidence names the event by its world key, "event:<id>".
      const eventKey =
        (current.evidence?.event as { key?: string } | undefined)?.key ?? "";
      const eventId = eventKey.replace(/^event:/, "");
      if (!eventId) return;
      createDecision.mutate(
        {
          domain: "vessel",
          eventId,
          vesselId: current.subject.id,
          attentionId: current.attentionItemId ?? undefined,
          at,
          mode: "DEMO",
          assumptions: assumptions.rates,
          vesselAssumptions: assumptions.vessel,
        },
        {
          onSuccess: (problem) => {
            const keep = problem.options.some(
              (o) => o.optionId === world.decisionOptionId,
            );
            world.openDecision(
              problem.decisionId,
              keep
                ? world.decisionOptionId
                : (problem.recommendation?.optionId ??
                    problem.baselineOptionId),
              world.decisionCompare,
            );
          },
        },
      );
    },
    [at, createDecision, decision.data, world],
  );
  // When a decision opens (or its option changes) the camera shows every
  // visible passage: the Cape routing pulls the view out to the basin.
  const decisionViewKey = decision.data
    ? `${decision.data.decisionId}|${world.decisionCompare}`
    : null;
  useEffect(() => {
    if (!decisionViewKey || !decision.data) return;
    const box = decisionBounds(
      decision.data,
      world.decisionOptionId,
      world.decisionCompare,
    );
    if (box) workspace.fitBounds(box, DECISION_PADDING);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [decisionViewKey]);
  const canHandoff = role === "PORT_AUTHORITY" || role === "NATIONAL_ADMIN";

  const detail = useAttentionItem(
    evidenceOpen ? selectedAttentionId : null,
    identityHeaders,
    at,
  );

  // The sea state is the one layer a lens switches at the workspace rather
  // than over it: the toggle is also what starts the forecast query, and a
  // query for cells nobody is looking at would be a fetch for nothing.
  const setLayer = workspace.setLayer;
  useEffect(() => {
    setLayer("seastate", lens === "WEATHER");
  }, [lens, setLayer]);

  // The lens is applied over the workspace's own toggles rather than replacing
  // them, so a layer the operator turned off stays off when they change lens.
  const lensedLayers = useMemo(
    () =>
      lensLayers(lens, {
        ...workspace.layers,
        events: true,
        routes: true,
        cascade: true,
      }),
    [lens, workspace.layers],
  );

  // The queue narrows to whatever the Copilot or a click last pointed at.
  const visibleAttention = useMemo(() => {
    const items = attention.data?.items ?? [];
    if (attentionSubjects.length === 0) return items;
    const wanted = new Set(attentionSubjects);
    const matching = items.filter((item) => wanted.has(item.subjectId));
    // Never leave the rail empty because a filter matched nothing -- an empty
    // queue reads as "nothing to do", which is a different claim entirely.
    return matching.length ? matching : items;
  }, [attention.data, attentionSubjects]);

  /** Selecting an item drives the world: subject, cascade and camera. */
  const selectItem = useCallback(
    (item: AttentionItem) => {
      const eventId = item.cascadeId.split(":").pop() ?? null;
      if (eventId && eventId !== selectedEventId) world.selectEvent(eventId);
      if (item.subjectType === "vessel") {
        world.selectVessel(item.subjectId);
        workspace.setSelectedVesselId(item.subjectId);
      }
      if (item.subjectType === "port") {
        world.selectPort(item.subjectId);
        workspace.setSelectedPortCode(item.subjectId);
      }
      const subject = [
        ...(affected?.ports ?? []),
        ...(affected?.chokepoints ?? []),
      ].find((s) => s.id === item.subjectId);
      if (subject?.lat != null && subject?.lon != null) {
        workspace.flyTo([subject.lon, subject.lat], 4.4);
      }
    },
    [affected, selectedEventId, workspace, world],
  );

  const inspect = useCallback(
    (item: AttentionItem) => {
      selectItem(item);
      world.openEvidence(item.attentionId);
    },
    [selectItem, world],
  );

  /**
   * The Copilot moves the camera by naming a subject, not a coordinate.
   *
   * A command carries an id; the geometry for it is in the cascade the screen
   * already holds. Resolving here keeps the agent from having to know where
   * anything is, which is knowledge it would otherwise have to be given and
   * could then get wrong.
   */
  useEffect(() => {
    const target = world.vesselId ?? world.portCode ?? world.chokepoint;
    if (!target || !affected) return;
    const subject = [
      ...affected.ports,
      ...affected.chokepoints,
      ...affected.vessels,
    ].find((s) => s.id === target);
    if (subject?.lat != null && subject?.lon != null) {
      workspace.flyTo([subject.lon, subject.lat], 4.4);
    }
  }, [world.vesselId, world.portCode, world.chokepoint, affected, workspace]);

  if (cascades.isLoading || cascades.isError) {
    return (
      <ScreenFallback
        title={title}
        context={<span>World events and their maritime consequence</span>}
        isLoading={cascades.isLoading}
        error={cascades.error}
        retry={() => void cascades.refetch()}
        label="Propagating world consequence"
      />
    );
  }

  const totals = cascade.data?.totals ?? {};
  const selectedCascade = cascade.data;
  const lensDefinition = LENS_DEFINITIONS[lens];

  return (
    <div className="absolute inset-0">
      <h1 className="sr-only">{title}</h1>

      <MaritimeMap
        layers={lensedLayers}
        data={{
          ...workspace.data,
          cascade: decisionOpen ? decisionLayerData.cascade : layers.cascade,
        }}
        weatherRaster={workspace.raster}
        windFrame={workspace.frame}
        showWind={workspace.showWind && workspace.layers.weather}
        vesselFilter={workspace.vesselFilter}
        focusIds={
          decisionOpen
            ? decisionLayerData.focusIds.size
              ? decisionLayerData.focusIds
              : null
            : layers.focusIds.size
              ? layers.focusIds
              : null
        }
        selectedVesselId={workspace.selectedVesselId}
        onSelectVessel={workspace.setSelectedVesselId}
        onSelectObserved={workspace.setSelectedObservedMmsi}
        labels={mapLabels}
        selectedPortCode={workspace.selectedPortCode}
        onSelectPort={workspace.setSelectedPortCode}
        focus={workspace.focus}
        overlay={
          <>
            {/* ---------------------------------------------- action rail -- */}
            {/*
              Bounded at the bottom rather than left to grow.
              At 1366x768 the rail is tall enough to run underneath the
              environment legend, which silently clips the live-consequence
              list -- a collision no overflow check catches, because nothing
              overflows the page.

              The rail itself is capped so the live-consequence list below it
              always keeps at least 168px: five actionable hulls, each with
              its effect lines and its "What should we do?" control, are taller
              than a 768px column, and a rail that takes its full content
              height pushes the register out of the column entirely. The rail
              scrolls inside its cap instead.
            */}
            <div className="pointer-events-none absolute bottom-[184px] left-2.5 top-2.5 z-20 flex w-[300px] flex-col gap-2 overflow-hidden">
              <FloatPanel
                title="Action required"
                note={
                  <span className="num">
                    {attention.data?.actionable ?? 0}/
                    {attention.data?.total ?? 0}
                  </span>
                }
                testId="action-rail"
                className="pointer-events-auto max-h-[calc(100%-176px)] min-h-0 shrink"
                footer={
                  "Ranked by the loss attention can still prevent: consequence × " +
                  "confidence × urgency, cut when no option remains."
                }
              >
                <ActionRail
                  items={visibleAttention}
                  total={attention.data?.total ?? 0}
                  selectedId={selectedAttentionId}
                  onSelect={selectItem}
                  onInspect={inspect}
                  onDecide={decide}
                  decidingId={
                    createDecision.isPending
                      ? (createDecision.variables?.attentionId ?? null)
                      : null
                  }
                  loading={attention.isLoading}
                />
                {createDecision.isError ? (
                  <p
                    className="px-2 py-1 text-[10.5px] text-[var(--crit)]"
                    data-testid="decide-error"
                  >
                    {(createDecision.error as Error).message}
                  </p>
                ) : null}
              </FloatPanel>

              {/* ------------------------------------------- world events -- */}
              <FloatPanel
                title="Live consequence"
                note={<span className="num">{live.length}</span>}
                testId="cascade-register"
                className="pointer-events-auto min-h-[168px] flex-1"
              >
                {live.length === 0 ? (
                  <EmptyNote>
                    No event in the register propagates consequence at this
                    instant. Scrub back toward now to see live events.
                  </EmptyNote>
                ) : (
                  live.slice(0, 6).map((row) => (
                    <CascadeRow
                      key={row.eventId}
                      row={row}
                      selected={row.eventId === selectedEventId}
                      onSelect={() => {
                        world.selectEvent(row.eventId);
                        world.openEvidence(null);
                        if (row.lat != null && row.lon != null) {
                          workspace.flyTo([row.lon, row.lat], 4.2);
                        }
                      }}
                    />
                  ))
                )}
              </FloatPanel>
            </div>

            {/* ------------------------------------------------- decision -- */}
            {decisionOpen ? (
              <div className="pointer-events-none absolute bottom-2.5 right-2.5 top-2.5 z-30 flex w-[372px] flex-col">
                <FloatPanel
                  title="Decision"
                  note={<span className="num">{world.decisionId}</span>}
                  className="pointer-events-auto min-h-0 flex-1"
                  scroll={false}
                  testId="decision-float"
                  onClose={() => world.openDecision(null)}
                  footer="Every figure is a measure the engine produced on that option's branch; unavailable means unavailable."
                >
                  {decision.data ? (
                    <DecisionPanel
                      problem={decision.data}
                      selectedOptionId={world.decisionOptionId}
                      compare={world.decisionCompare}
                      onSelectOption={world.selectDecisionOption}
                      onToggleCompare={world.setDecisionCompare}
                      canHandoff={canHandoff}
                      onRecompute={recompute}
                      recomputing={createDecision.isPending}
                    />
                  ) : decision.isError ? (
                    <p className="px-2 py-3 text-[10.5px] text-[var(--crit)]">
                      {(decision.error as Error).message}
                    </p>
                  ) : (
                    <p className="px-2 py-3 text-[10.5px] text-[var(--text-3)]">
                      Simulating every option on its own branch…
                    </p>
                  )}
                </FloatPanel>
              </div>
            ) : null}

            {/* ------------------------------------------------- evidence -- */}
            {evidenceOpen && selectedAttentionId && !decisionOpen ? (
              <div className="pointer-events-none absolute bottom-2.5 right-2.5 top-2.5 z-30 flex w-[330px] flex-col">
                <FloatPanel
                  title="Why this"
                  className="pointer-events-auto min-h-0 flex-1"
                  scroll={false}
                  testId="evidence-panel"
                  footer="Every line is a step the engine ran, including the ones it refused."
                >
                  {detail.isLoading ? (
                    <p className="px-2 py-3 text-[10.5px] text-[var(--text-3)]">
                      Reading the computation trail…
                    </p>
                  ) : (
                    <EvidenceDrawer
                      item={detail.data?.item ?? null}
                      steps={detail.data?.evidence ?? []}
                      narrative={detail.data?.narrative ?? []}
                      onClose={() => world.openEvidence(null)}
                    />
                  )}
                </FloatPanel>
              </div>
            ) : null}

            {/* --------------------------------------------- lens reports -- */}
            {/*
              Two lenses read the backend rather than a static note: the
              security lens asks the feed and is told UNAVAILABLE under the
              replay; the cargo lens traces the selected event's structural
              exposure. Both replace the fabricated-layer refusal with the
              API's own answer, which is the same refusal with evidence.
            */}
            {lens === "SECURITY" ? (
              <div className="pointer-events-none absolute bottom-[150px] left-1/2 z-20 w-[480px] -translate-x-1/2">
                <SecurityLensReport mode="DEMO" />
              </div>
            ) : lens === "CARGO" ? (
              <div className="pointer-events-none absolute bottom-[150px] left-1/2 z-20 w-[480px] -translate-x-1/2">
                <TradeExposureReport eventId={selectedEventId ?? null} />
              </div>
            ) : null}

            {/* --------------------------------------------- lens notice -- */}
            {lensDefinition.unavailable &&
            lens !== "SECURITY" &&
            lens !== "CARGO" ? (
              <div
                className="pointer-events-none absolute bottom-[150px] left-1/2 z-20 w-[420px] -translate-x-1/2"
                data-testid="lens-unavailable"
              >
                <div className="rounded border border-[var(--line)] bg-[var(--surface)]/94 px-2.5 py-2 backdrop-blur">
                  <div className="flex items-center gap-1.5">
                    <Pill tone="neutral">
                      {lensDefinition.label} · unavailable
                    </Pill>
                  </div>
                  <p className="mt-1 text-[10.5px] font-medium text-[var(--text)]">
                    {lensDefinition.unavailable.headline}
                  </p>
                  <p className="mt-1 text-[10.5px] leading-relaxed text-[var(--text-2)]">
                    {lensDefinition.unavailable.detail}
                  </p>
                  <ul className="mt-1.5 flex flex-col gap-0.5">
                    {lensDefinition.unavailable.needs.map((need) => (
                      <li
                        key={need}
                        className="text-[10px] text-[var(--text-3)]"
                      >
                        · {need}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : null}

            {/* ------------------------------------------------- headline -- */}
            {selectedCascade ? (
              <div
                className={cn(
                  "pointer-events-none absolute top-2.5 z-20",
                  // The headline is anchored just right of the rail and never
                  // wider than the water between the rail and the copilot
                  // column, so at 1366px with a decision open it shrinks
                  // rather than sliding under the lens bar.
                  decisionOpen
                    ? "left-[314px] w-[min(380px,calc(100vw-314px-392px-380px))]"
                    : evidenceOpen && selectedAttentionId
                      ? "left-[314px] w-[min(420px,calc(100vw-314px-350px-380px))]"
                      : "left-1/2 w-[420px] -translate-x-1/2",
                )}
                data-testid="cascade-headline"
              >
                <div className="rounded border border-[var(--line)] bg-[var(--surface)]/92 px-2.5 py-1.5 backdrop-blur">
                  <p className="truncate text-[11px] font-medium text-[var(--text)]">
                    {selectedCascade.title}
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[10.5px] text-[var(--text-2)]">
                    {totals.vessels ? (
                      <span className="num" data-testid="total-vessels">
                        {totals.vessels.value.toFixed(0)} vessels
                      </span>
                    ) : null}
                    {totals.hours ? (
                      <span className="num" data-testid="total-hours">
                        {totals.hours.value.toFixed(0)} h aggregate shift
                      </span>
                    ) : null}
                    {totals.ratio ? (
                      <span className="num" data-testid="total-pressure">
                        {(totals.ratio.value * 100).toFixed(0)}% yard pressure
                      </span>
                    ) : null}
                    <SeedBasis cascade={selectedCascade} />
                    <span className="num ml-auto text-[var(--text-3)]">
                      {affected?.lanes.length ?? 0} lanes ·{" "}
                      {affected?.ports.length ?? 0} ports
                    </span>
                  </div>
                </div>
              </div>
            ) : null}

            {/* ----------------------------------------------- copilot -- */}
            <div
              className={cn(
                "pointer-events-none absolute top-2.5 z-30 flex flex-col items-end gap-2",
                decisionOpen
                  ? "right-[392px]"
                  : evidenceOpen && selectedAttentionId
                    ? "right-[350px]"
                    : "right-2.5",
              )}
            >
              <CommandBar />
              <LensBar lens={lens} onChange={world.setLens} />
              <SignalHealth mode="DEMO" />
              {/* An observed hull's inspector flows beneath the trust surface
                  rather than beside it, so opening the health panel never
                  covers what a click on the chart just opened. */}
              {workspace.selectedObservedMmsi &&
              !(evidenceOpen && selectedAttentionId) &&
              !decisionOpen ? (
                <div className="pointer-events-none flex max-h-[60vh] w-[330px] flex-col">
                  <ObservedSelection
                    workspace={workspace}
                    className="min-h-0 flex-1"
                  />
                </div>
              ) : null}
            </div>

            {/* -------------------------------------------------- legend -- */}
            <div className="pointer-events-none absolute bottom-2.5 left-2.5 z-20 w-[248px]">
              <EnvironmentLegend
                workspace={workspace}
                frame={workspace.frame}
              />
            </div>

            {/* ----------------------------------------------- transport -- */}
            <div className="pointer-events-none absolute bottom-2.5 left-[266px] right-2.5 z-20 flex flex-col gap-1.5">
              <ProjectionBar
                hours={projectionHours}
                onChange={world.setProjectionHours}
                live={Boolean(selectedCascade?.live)}
                playing={reveal.playing}
                onPlay={reveal.play}
                onReset={reveal.reset}
              />
              <TimeTransport
                timeline={workspace.timeline}
                weatherAt={workspace.weatherAt}
              />
            </div>
          </>
        }
      />
    </div>
  );
}

/**
 * What the cascade was seeded from, and whether that number is calibrated.
 *
 * A probability is either calibrated against resolved outcomes or it is
 * withheld with a reason -- there is no third state, and a bare percentage out
 * of a word-list heuristic is the thing this product must never show. The
 * cascade is seeded with the calibrated probability where one exists and with
 * raw severity where none does, so a reader has to be able to tell which drove
 * everything downstream of it.
 */
function SeedBasis({ cascade }: { cascade: WorldCascade }) {
  const seed = cascade.seed?.quantity;
  if (!seed) return null;
  const calibrated = Boolean(seed.attrs?.calibrated);
  return (
    <span data-testid="seed-basis" className="num">
      {calibrated ? (
        <span title="Calibrated against resolved outcomes">
          seeded {(seed.value * 100).toFixed(0)}% calibrated
        </span>
      ) : (
        <span
          className="text-[var(--text-3)]"
          title="No calibrated probability yet; the cascade is seeded from severity and corroboration instead."
        >
          seeded from severity · no calibrated probability
        </span>
      )}
    </span>
  );
}

/**
 * The lens control.
 *
 * A lens is not a route. Switching one never navigates and never refetches:
 * the same world state is on screen throughout, and what changes is which parts
 * of it are drawn at full weight. That is the difference between an
 * interpretation and a page, and it is why these are six buttons on the world
 * rather than six entries in the navigation.
 */
function LensBar({
  lens,
  onChange,
}: {
  lens: Lens;
  onChange: (lens: Lens) => void;
}) {
  return (
    <div
      data-testid="lens-bar"
      className="pointer-events-auto flex items-center gap-0.5 rounded border border-[var(--line)] bg-[var(--surface)]/92 px-1 py-1 backdrop-blur"
      role="tablist"
      aria-label="World lens"
    >
      {LENSES.map((option) => {
        const definition = LENS_DEFINITIONS[option];
        const unavailable = Boolean(definition.unavailable);
        return (
          <button
            key={option}
            type="button"
            data-testid="lens-option"
            data-lens={option}
            data-active={lens === option}
            data-unavailable={unavailable}
            title={
              unavailable
                ? `${definition.purpose} — ${definition.unavailable!.headline}`
                : definition.purpose
            }
            onClick={() => onChange(option)}
            className={cn(
              "flex items-center gap-1 rounded px-2 py-1 text-[10px] transition-colors",
              lens === option
                ? "bg-[var(--accent)] text-[var(--surface)]"
                : "text-[var(--text-2)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]",
            )}
          >
            {/*
              A lens with nothing behind it is marked before it is opened.
              Finding out only after switching wastes the click and, worse,
              reads as a fault rather than a stated absence.
            */}
            {unavailable ? (
              <span
                className={cn(
                  "h-1 w-1 shrink-0 rounded-full",
                  lens === option
                    ? "bg-[var(--surface)]"
                    : "bg-[var(--text-3)]",
                )}
              />
            ) : null}
            {definition.label}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ rows -- */

function CascadeRow({
  row,
  selected,
  onSelect,
}: {
  row: WorldCascade;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      data-testid="cascade-row"
      data-event={row.eventId}
      className={cn(
        "w-full border-b border-[var(--line)] px-2 py-1.5 text-left transition-colors",
        "hover:bg-[var(--surface-2)]",
        selected && "bg-[var(--surface-2)]",
      )}
    >
      <p className="truncate text-[10.5px] text-[var(--text)]">{row.title}</p>
      <div className="mt-0.5 flex items-center gap-2 text-[10px] text-[var(--text-3)]">
        <span className="num">{row.nodeCount} affected</span>
        {row.totals?.vessels ? (
          <span className="num">
            {row.totals.vessels.value.toFixed(0)} hulls
          </span>
        ) : null}
      </div>
    </button>
  );
}

/**
 * PROJECT 72H.
 *
 * Each offset re-queries the same temporal graph. Nothing here predicts: an
 * event past its claim horizon simply stops reaching anything, and the operator
 * watches the consequence drain rather than being shown a second model's
 * opinion of the future.
 */
function ProjectionBar({
  hours,
  onChange,
  live,
  playing,
  onPlay,
  onReset,
}: {
  hours: number;
  onChange: (hours: number) => void;
  live: boolean;
  playing: boolean;
  onPlay: () => void;
  onReset: () => void;
}) {
  return (
    <div
      className="pointer-events-auto flex items-center gap-1 rounded border border-[var(--line)] bg-[var(--surface)]/92 px-1.5 py-1 backdrop-blur"
      data-testid="projection-bar"
    >
      <span className="mr-1 text-[10px] uppercase tracking-wide text-[var(--text-3)]">
        Project
      </span>
      {PROJECTION_OFFSETS.map((offset) => (
        <button
          key={offset}
          type="button"
          data-testid="projection-offset"
          data-offset={offset}
          data-active={hours === offset}
          onClick={() => onChange(offset)}
          className={cn(
            "num rounded px-1.5 py-0.5 text-[10px] transition-colors",
            hours === offset
              ? "bg-[var(--accent)] text-[var(--surface)]"
              : "text-[var(--text-2)] hover:bg-[var(--surface-2)]",
          )}
        >
          {offset === 0 ? "NOW" : `+${offset}h`}
        </button>
      ))}

      <span className="mx-1 h-3 w-px bg-[var(--line)]" />

      <button
        type="button"
        data-testid="play-cascade"
        onClick={onPlay}
        disabled={playing}
        className="rounded px-1.5 py-0.5 text-[10px] text-[var(--text-2)] hover:bg-[var(--surface-2)] disabled:opacity-40"
      >
        {playing ? "Playing" : "Play cascade"}
      </button>
      <button
        type="button"
        data-testid="reset-cascade"
        onClick={onReset}
        className="rounded px-1.5 py-0.5 text-[10px] text-[var(--text-2)] hover:bg-[var(--surface-2)]"
      >
        Reset
      </button>

      <span className="ml-auto" data-testid="projection-state">
        <Pill tone={live ? "info" : "neutral"}>
          {live ? "propagating" : "no consequence"}
        </Pill>
      </span>
    </div>
  );
}
