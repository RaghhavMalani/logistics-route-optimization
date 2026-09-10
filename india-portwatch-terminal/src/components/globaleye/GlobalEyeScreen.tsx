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

import { ActionRail } from "./ActionRail";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { useCascadeReveal } from "./useCascadeReveal";

export type GlobalEyeScope = "national" | "company" | "port";

/** The horizons the projection offers, in hours from now. */
const PROJECTION_OFFSETS = [0, 3, 6, 12, 24, 48, 72] as const;

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

  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedAttentionId, setSelectedAttentionId] = useState<string | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [projectionHours, setProjectionHours] = useState(0);

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
    setSelectedEventId(live[0].eventId);
  }, [live, selectedEventId]);

  const cascade = useWorldCascade(selectedEventId, identityHeaders, at);
  const reveal = useCascadeReveal(
    selectedEventId ? `${selectedEventId}@${projectionHours}` : null,
  );

  const affected = cascade.data?.affected;
  const layers = useMemo(
    () => cascadeLayers(affected, reveal.reveal),
    [affected, reveal.reveal],
  );

  const detail = useAttentionItem(
    evidenceOpen ? selectedAttentionId : null,
    identityHeaders,
    at,
  );

  /** Selecting an item drives the world: subject, cascade and camera. */
  const selectItem = useCallback(
    (item: AttentionItem) => {
      setSelectedAttentionId(item.attentionId);
      const eventId = item.cascadeId.split(":").pop() ?? null;
      if (eventId && eventId !== selectedEventId) setSelectedEventId(eventId);
      if (item.subjectType === "vessel") {
        workspace.setSelectedVesselId(item.subjectId);
      }
      if (item.subjectType === "port") {
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
    [affected, selectedEventId, workspace],
  );

  const inspect = useCallback(
    (item: AttentionItem) => {
      selectItem(item);
      setEvidenceOpen(true);
    },
    [selectItem],
  );

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

  return (
    <div className="absolute inset-0">
      <h1 className="sr-only">{title}</h1>

      <MaritimeMap
        layers={{ ...workspace.layers, events: true, routes: true, cascade: true }}
        data={{
          ...workspace.data,
          cascade: layers.cascade,
          rings: layers.rings,
        }}
        weatherRaster={workspace.raster}
        windFrame={workspace.frame}
        showWind={workspace.showWind && workspace.layers.weather}
        vesselFilter={workspace.vesselFilter}
        focusIds={layers.focusIds.size ? layers.focusIds : null}
        selectedVesselId={workspace.selectedVesselId}
        onSelectVessel={workspace.setSelectedVesselId}
        labels={workspace.labels}
        selectedPortCode={workspace.selectedPortCode}
        onSelectPort={workspace.setSelectedPortCode}
        focus={workspace.focus}
        overlay={
          <>
            {/* ---------------------------------------------- action rail -- */}
            <div className="pointer-events-none absolute left-2.5 top-2.5 z-20 flex w-[286px] flex-col gap-2">
              <FloatPanel
                title="Action required"
                note={
                  <span className="num">
                    {attention.data?.actionable ?? 0}/{attention.data?.total ?? 0}
                  </span>
                }
                testId="action-rail"
                className="pointer-events-auto"
                footer={
                  "Ranked by the loss attention can still prevent: consequence × " +
                  "confidence × urgency, cut when no option remains."
                }
              >
                <ActionRail
                  items={attention.data?.items ?? []}
                  total={attention.data?.total ?? 0}
                  selectedId={selectedAttentionId}
                  onSelect={selectItem}
                  onInspect={inspect}
                  loading={attention.isLoading}
                />
              </FloatPanel>

              {/* ------------------------------------------- world events -- */}
              <FloatPanel
                title="Live consequence"
                note={<span className="num">{live.length}</span>}
                testId="cascade-register"
                className="pointer-events-auto"
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
                        setSelectedEventId(row.eventId);
                        setSelectedAttentionId(null);
                        if (row.lat != null && row.lon != null) {
                          workspace.flyTo([row.lon, row.lat], 4.2);
                        }
                      }}
                    />
                  ))
                )}
              </FloatPanel>
            </div>

            {/* ------------------------------------------------- evidence -- */}
            {evidenceOpen && selectedAttentionId ? (
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
                      onClose={() => setEvidenceOpen(false)}
                    />
                  )}
                </FloatPanel>
              </div>
            ) : null}

            {/* ------------------------------------------------- headline -- */}
            {selectedCascade ? (
              <div
                className="pointer-events-none absolute left-1/2 top-2.5 z-20 w-[420px] -translate-x-1/2"
                data-testid="cascade-headline"
              >
                <div className="rounded border border-[var(--line)] bg-[var(--surface)]/92 px-2.5 py-1.5 backdrop-blur">
                  <p className="truncate text-[11px] font-medium text-[var(--text)]">
                    {selectedCascade.title}
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[9.5px] text-[var(--text-2)]">
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
                    <span className="num ml-auto text-[var(--text-3)]">
                      {affected?.lanes.length ?? 0} lanes · {affected?.ports.length ?? 0} ports
                    </span>
                  </div>
                </div>
              </div>
            ) : null}

            {/* -------------------------------------------------- legend -- */}
            <div className="pointer-events-none absolute bottom-2.5 left-2.5 z-20 w-[248px]">
              <EnvironmentLegend workspace={workspace} frame={workspace.frame} />
            </div>

            {/* ----------------------------------------------- transport -- */}
            <div className="pointer-events-none absolute bottom-2.5 left-[266px] right-2.5 z-20 flex flex-col gap-1.5">
              <ProjectionBar
                hours={projectionHours}
                onChange={setProjectionHours}
                live={Boolean(selectedCascade?.live)}
                playing={reveal.playing}
                onPlay={reveal.play}
                onReset={reveal.reset}
              />
              <TimeTransport timeline={workspace.timeline} weatherAt={workspace.weatherAt} />
            </div>
          </>
        }
      />
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
      <div className="mt-0.5 flex items-center gap-2 text-[9px] text-[var(--text-3)]">
        <span className="num">{row.nodeCount} affected</span>
        {row.totals?.vessels ? (
          <span className="num">{row.totals.vessels.value.toFixed(0)} hulls</span>
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
      <span className="mr-1 text-[9px] uppercase tracking-wide text-[var(--text-3)]">
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
