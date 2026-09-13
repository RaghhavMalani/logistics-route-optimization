/**
 * An observed transponder, shown as exactly what it said.
 *
 * This panel is the counterpart of the replay inspector and is deliberately
 * poorer. The replay knows a hull's class, length, operator and voyage because
 * it wrote them; a transponder reports an MMSI and a position, and -- on a
 * separate cadence, if at all -- a typed name, IMO and destination. Every
 * field here is either what a message carried or the phrase "not stated",
 * and there is no class glyph, because inferring a class from a name is the
 * kind of quiet invention this product refuses.
 *
 * The badge at the top says OBSERVED AIS, and the freshness beside it says
 * LIVE or STALE from the transponder's own timestamp -- the same two words the
 * replay inspector never gets to use.
 */

import { Pill } from "@/components/kit/primitives";
import { formatAge, formatInstant } from "@/components/fabric/signal-format";
import { cn } from "@/lib/utils";
import type { ObservedTrack, TrafficMode } from "@/types/portwatch-os";

import { Field, FloatPanel, PanelSection } from "./panels";

function stated(value: string | null | undefined): React.ReactNode {
  return value ? (
    <span className="num">{value}</span>
  ) : (
    <span className="text-[var(--text-3)]">not stated</span>
  );
}

function number(
  value: number | null | undefined,
  unit: string,
  digits = 1,
): React.ReactNode {
  return value == null ? (
    <span className="text-[var(--text-3)]">not available</span>
  ) : (
    <span className="num">
      {value.toFixed(digits)}
      {unit}
    </span>
  );
}

export function ObservedVesselInspector({
  track,
  traffic,
  onClose,
  className,
}: {
  track: ObservedTrack;
  traffic: TrafficMode | null;
  onClose: () => void;
  className?: string;
}) {
  const latest = track.latest;
  const ageSeconds = track.lastSeen
    ? Math.max(0, (Date.now() - Date.parse(track.lastSeen)) / 1000)
    : null;
  const title = track.name ?? `MMSI ${track.mmsi}`;

  return (
    <FloatPanel
      title={title}
      note={<span className="num">{track.mmsi}</span>}
      onClose={onClose}
      testId="observed-inspector"
      width={330}
      className={cn("max-h-full", className)}
      footer={
        <span>
          Position and identity are what transponder {track.mmsi} reported,
          received over {latest?.providerId ?? "the AIS feed"}. Nothing here has
          been filled in from a registry or a name match. A field marked{" "}
          <em>not stated</em> was not in any message received.
        </span>
      }
    >
      <div
        className="flex items-center gap-1.5 border-b border-[var(--line)] px-2 py-1.5"
        data-testid="vessel-source"
        data-source="OBSERVED_AIS"
        data-freshness={track.freshness}
      >
        <Pill tone="ok" solid>
          OBSERVED AIS
        </Pill>
        <Pill
          tone={
            track.freshness === "LIVE"
              ? "ok"
              : track.freshness === "STALE"
                ? "warn"
                : "unc"
          }
        >
          {track.freshness}
        </Pill>
        <span className="num ml-auto text-[10px] text-[var(--text-3)]">
          {formatAge(ageSeconds)} ago
        </span>
      </div>

      <PanelSection title="Last observation">
        <Field label="Reported at">
          <span className="num">{formatInstant(track.lastSeen)}</span>
        </Field>
        <Field label="Position">
          {latest ? (
            <span className="num">
              {latest.lat.toFixed(4)}, {latest.lon.toFixed(4)}
            </span>
          ) : (
            "—"
          )}
        </Field>
        <Field label="Speed over ground">
          {number(latest?.sogKnots, " kn")}
        </Field>
        <Field label="Course over ground">
          {number(latest?.cogDegrees, "°", 0)}
        </Field>
        <Field
          label="Heading"
          hint="511 in the message means no heading; shown as not available"
        >
          {number(latest?.headingDegrees, "°", 0)}
        </Field>
        <Field label="Navigational status">{stated(latest?.navStatus)}</Field>
        <Field label="Positions held">
          <span className="num">{track.positions}</span>
          {track.duplicates || track.outOfOrder ? (
            <span className="ml-1 text-[9.5px] text-[var(--text-3)]">
              {track.duplicates} dup · {track.outOfOrder} late
            </span>
          ) : null}
        </Field>
      </PanelSection>

      <PanelSection title="Identity, as stated by the transponder">
        <Field label="MMSI">
          <span className="num">{track.mmsi}</span>
        </Field>
        <Field
          label="IMO"
          hint="Only a static-data message states an IMO; a position report never does"
        >
          {stated(track.imo)}
        </Field>
        <Field label="Name">{stated(track.name)}</Field>
        <Field label="Call sign">{stated(track.callsign)}</Field>
        <Field label="Destination (typed)">
          {stated(track.destinationText)}
        </Field>
        <Field label="ETA (typed)">{stated(track.etaText)}</Field>
      </PanelSection>

      <PanelSection title="Source">
        <Field label="Provider">
          <span className="num">
            {latest?.providerId ?? traffic?.providerId ?? "—"}
          </span>
        </Field>
        <Field label="Traffic mode">
          <Pill tone={traffic?.mode === "LIVE_AIS" ? "ok" : "warn"}>
            {traffic?.mode ?? "—"}
          </Pill>
        </Field>
        {traffic?.health ? (
          <>
            <Field label="Socket">
              <span className="num">{traffic.health.health}</span>
            </Field>
            <Field label="Feed last good">
              <span className="num">
                {formatInstant(traffic.health.lastGoodObservationAt)}
              </span>
            </Field>
          </>
        ) : null}
        {latest?.rawRef ? (
          <Field label="Raw reference">
            <span className="num text-[9.5px]">{latest.rawRef}</span>
          </Field>
        ) : null}
      </PanelSection>
    </FloatPanel>
  );
}

/**
 * The observed selection for a workspace, or nothing.
 *
 * One component so every chart wires it the same way: the map reports the
 * MMSI that was clicked, the workspace holds it, and this finds the track in
 * the last poll. A track that has since been evicted simply stops rendering.
 */
export function ObservedSelection({
  workspace,
  className,
}: {
  workspace: {
    observedTracks: { tracks: ObservedTrack[]; traffic: TrafficMode } | null;
    selectedObservedMmsi: string | null;
    setSelectedObservedMmsi: (mmsi: string | null) => void;
  };
  className?: string;
}) {
  const mmsi = workspace.selectedObservedMmsi;
  const track = mmsi
    ? workspace.observedTracks?.tracks.find((t) => t.mmsi === mmsi)
    : null;
  if (!track) return null;
  return (
    <ObservedVesselInspector
      track={track}
      traffic={workspace.observedTracks?.traffic ?? null}
      onClose={() => workspace.setSelectedObservedMmsi(null)}
      className={className}
    />
  );
}
