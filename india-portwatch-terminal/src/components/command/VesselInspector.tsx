/**
 * The vessel inspector.
 *
 * Ordered the way a bridge or a control room reads a contact: what it is doing
 * now, where the passage goes, what it will meet on the way, what it will find
 * when it arrives, who else is around it, and only then what the model suggests.
 * The recommendation is last because it is a conclusion, and a conclusion is
 * worth nothing if the numbers above it are not on the same screen.
 */

import { useMemo } from "react";

import { useFixes, useTraffic, useTrafficTick } from "@/components/app/traffic-context";
import { Num, Pill, ProvenanceTag } from "@/components/kit/primitives";
import {
  compassPoint,
  formatBearing,
  formatDuration,
  formatPosition,
} from "@/lib/maritime/geo";
import { seaRoute, waypoint } from "@/lib/maritime/searoutes";
import {
  NAV_STATUS_LABEL,
  VESSEL_CLASSES,
  type VesselFix,
} from "@/lib/maritime/traffic-types";
import {
  arrivalSequence,
  congestionAt,
  nearbyTraffic,
  portTraffic,
  vesselAdvice,
  STATUS_TONE,
} from "@/lib/maritime/traffic-views";
import {
  EXPOSURE_COLOR,
  routeExposure,
  worstExposure,
  type ExposureSegment,
} from "@/lib/maritime/weather-field";
import type { WeatherTimeline } from "@/lib/maritime/weather-model";
import { useForecast } from "@/services/hooks";
import type { FleetRow, PortSnapshot } from "@/types/portwatch";
import { cn } from "@/lib/utils";
import { EmptyNote, Field, FloatPanel, PanelSection } from "./panels";

function clockZ(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return "n/a";
  const date = new Date(ms);
  return `${String(date.getUTCDate()).padStart(2, "0")} ${String(date.getUTCHours()).padStart(2, "0")}:${String(
    date.getUTCMinutes(),
  ).padStart(2, "0")}Z`;
}

export function useRouteExposure(
  fix: VesselFix | null,
  timeline: WeatherTimeline,
): ExposureSegment[] {
  return useMemo(() => {
    if (!fix?.routeKey || !timeline.available) return [];
    const [from, to] = fix.routeKey.split(">");
    const route = seaRoute(from, to);
    if (!route) return [];
    const ahead = route.path.coords.filter(
      (_, index) => route.path.cumulative[index] >= fix.travelledKm,
    );
    if (ahead.length < 2) return [];
    return routeExposure(ahead, {
      at: fix.at,
      speedKn: Math.max(4, fix.serviceSpeedKn),
      frameAt: (at) => timeline.frameAt(at),
    });
    // The exposure only needs to move when the vessel does, not every frame.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fix?.id, fix?.routeKey, Math.round((fix?.travelledKm ?? 0) / 25), timeline]);
}

export function VesselInspector({
  fix,
  ports,
  timeline,
  onClose,
  onIsolate,
  isolated,
  onFollow,
  following,
  onSelectVessel,
  ownRow,
  className,
}: {
  fix: VesselFix;
  ports: PortSnapshot[];
  timeline: WeatherTimeline;
  onClose: () => void;
  onIsolate?: () => void;
  isolated?: boolean;
  onFollow?: () => void;
  following?: boolean;
  onSelectVessel?: (id: string) => void;
  /** The routing artefact's row, when this is a vessel the operator owns. */
  ownRow?: FleetRow | null;
  className?: string;
}) {
  const at = useTrafficTick(2);
  const fixes = useFixes(1);
  const { source } = useTraffic();

  const destination = ports.find((port) => port.code === fix.destinationId) ?? null;
  const forecast = useForecast(destination?.code ?? null);
  const spec = VESSEL_CLASSES[fix.vesselClass];

  const exposure = useRouteExposure(fix, timeline);
  const worst = worstExposure(exposure);

  const contacts = useMemo(() => nearbyTraffic(fix, fixes, 45, 8), [fix, fixes]);

  const slot = useMemo(() => {
    if (!destination?.location) return null;
    const traffic = portTraffic(fixes, {
      code: destination.code,
      lat: destination.location.lat,
      lon: destination.location.lon,
    });
    const plan = arrivalSequence(traffic, destination, {
      at,
      forecast: forecast.data ?? undefined,
    });
    return plan.slots.find((entry) => entry.fix.id === fix.id) ?? null;
  }, [at, destination, fix.id, fixes, forecast.data]);

  const advice = useMemo(
    () =>
      vesselAdvice({
        fix,
        port: destination,
        slot,
        worstExposure: worst ? { level: worst.level, leadHours: worst.leadHours } : null,
        closestContact: contacts[0] ?? null,
        reroute:
          ownRow?.reroute && ownRow.recommendedPortName
            ? {
                to: ownRow.recommendedPortName,
                savedWaitHours: ownRow.portWaitDeltaHours,
              }
            : null,
      }),
    [contacts, destination, fix, ownRow, slot, worst],
  );

  const congestionOnArrival =
    destination && fix.etaMs != null
      ? congestionAt(destination, forecast.data ?? undefined, fix.etaMs)
      : null;

  return (
    <FloatPanel
      title={fix.name}
      note={<span className="num">{fix.replayId}</span>}
      onClose={onClose}
      testId="vessel-inspector"
      width={330}
      className={cn("max-h-full", className)}
      footer={
        <span>
          Position, identity and voyage are <span className="text-[var(--unc)]">SIMULATED</span> by
          the PortWatch replay engine and moved along the water-only route graph. Not an AIS
          observation. Route geometry is non-navigational.
        </span>
      }
    >
      <div className="flex items-center gap-1.5 border-b border-[var(--line)] px-2 py-1.5">
        <span
          aria-hidden
          className="h-[9px] w-[9px] shrink-0 rounded-[1px]"
          style={{ background: spec.color }}
        />
        <span className="text-[11px] text-[var(--text-2)]">{spec.label}</span>
        <Pill tone={STATUS_TONE[fix.status]}>{NAV_STATUS_LABEL[fix.status]}</Pill>
        <span className="num ml-auto text-[10px] text-[var(--text-3)]">{fix.flag}</span>
      </div>

      <div className="flex gap-1 border-b border-[var(--line)] px-2 py-1.5">
        {onFollow ? (
          <button
            type="button"
            onClick={onFollow}
            aria-pressed={following}
            className={cn(
              "rounded-[2px] border px-1.5 py-[2px] text-[10px] transition-colors",
              following
                ? "border-[var(--info)] bg-[var(--info-dim)] text-[var(--info)]"
                : "border-[var(--line-strong)] text-[var(--text-2)] hover:text-[var(--text)]",
            )}
          >
            {following ? "Following" : "Follow"}
          </button>
        ) : null}
        {onIsolate ? (
          <button
            type="button"
            onClick={onIsolate}
            aria-pressed={isolated}
            className={cn(
              "rounded-[2px] border px-1.5 py-[2px] text-[10px] transition-colors",
              isolated
                ? "border-[var(--info)] bg-[var(--info-dim)] text-[var(--info)]"
                : "border-[var(--line-strong)] text-[var(--text-2)] hover:text-[var(--text)]",
            )}
          >
            {isolated ? "Show all traffic" : "Isolate"}
          </button>
        ) : null}
      </div>

      {/* --------------------------------------------------------- now -- */}
      <PanelSection title="Now">
        <Field label="Speed over ground">
          <Num value={fix.sogKn} digits={1} unit="kn" />
        </Field>
        <Field label="Course / heading">
          <span className="num">
            {formatBearing(fix.cog)} <span className="text-[var(--text-3)]">{compassPoint(fix.cog)}</span>
          </span>
        </Field>
        <Field label="Position">
          <span className="num text-[10.5px]">{formatPosition(fix.lat, fix.lon)}</span>
        </Field>
        <Field label="Length / draught">
          <span className="num">
            {fix.lengthM} m · {fix.draughtM.toFixed(1)} m
          </span>
        </Field>
        <Field label="IMO number" hint="No IMO number is issued: this is a simulated vessel.">
          <span className="text-[var(--unc)]">not issued · simulated</span>
        </Field>
      </PanelSection>

      {/* ------------------------------------------------------- route -- */}
      <PanelSection
        title="Passage"
        right={
          fix.routeKey ? (
            <span className="num">{(fix.progress * 100).toFixed(0)}%</span>
          ) : (
            "alongside"
          )
        }
      >
        <div className="mb-1.5 flex items-center gap-1.5 text-[11px]">
          <span className="truncate text-[var(--text-2)]">
            {waypoint(fix.originId)?.name ?? fix.originId}
          </span>
          <span className="text-[var(--text-3)]">→</span>
          <span className="truncate font-medium text-[var(--text)]">
            {waypoint(fix.destinationId)?.name ?? fix.destinationId}
          </span>
        </div>
        <div className="mb-1.5 h-[3px] w-full overflow-hidden rounded-[1px] bg-[var(--panel-3)]">
          <div
            className="h-full bg-[var(--info)]"
            style={{ width: `${Math.min(100, Math.max(0, fix.progress * 100))}%` }}
          />
        </div>
        <Field label="Distance remaining">
          <Num value={fix.remainingKm / 1.852} digits={0} unit="nm" />
        </Field>
        <Field label={fix.etaKind === "berthing" ? "Berthing" : fix.etaKind === "departure" ? "Departs" : "ETA"}>
          <span className="num">
            {clockZ(fix.etaMs)}
            <span className="ml-1 text-[10px] text-[var(--text-3)]">
              {formatDuration(fix.etaMinutes)}
            </span>
          </span>
        </Field>
      </PanelSection>

      {/* ---------------------------------------------- route weather -- */}
      <PanelSection
        title="Weather along the passage"
        right={worst ? worst.level.toUpperCase() : "—"}
      >
        {exposure.length === 0 ? (
          <p className="text-[10.5px] leading-snug text-[var(--text-3)]">
            {fix.routeKey
              ? "No forecast coverage along this passage."
              : "Vessel is in port; there is no passage to sample."}
          </p>
        ) : (
          <>
            <div className="mb-1.5 flex h-[6px] overflow-hidden rounded-[1px]">
              {exposure.map((segment, index) => (
                <span
                  key={index}
                  className="flex-1"
                  title={`${segment.label} at +${Math.round(segment.leadHours)}h`}
                  style={{ background: EXPOSURE_COLOR[segment.level] }}
                />
              ))}
            </div>
            <ul className="space-y-[3px]">
              {exposure.slice(0, 5).map((segment, index) => (
                <li key={index} className="flex items-baseline gap-2 text-[10.5px]">
                  <span className="num w-[38px] shrink-0 text-[var(--text-3)]">
                    +{Math.round(segment.leadHours)}h
                  </span>
                  <span
                    aria-hidden
                    className="h-[7px] w-[7px] shrink-0 rounded-[1px]"
                    style={{ background: EXPOSURE_COLOR[segment.level] }}
                  />
                  <span className="min-w-0 flex-1 truncate text-[var(--text-2)]">
                    {segment.rainMm != null ? `${segment.rainMm.toFixed(1)} mm` : "—"} ·{" "}
                    {segment.windKn != null ? `${segment.windKn.toFixed(0)} kn` : "—"}
                  </span>
                  <span className="num shrink-0 text-[var(--text-3)]">
                    {segment.impact != null ? segment.impact.toFixed(3) : "n/a"}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </PanelSection>

      {/* ------------------------------------------------- destination -- */}
      <PanelSection
        title="Destination"
        right={destination ? destination.regime : undefined}
      >
        {destination ? (
          <>
            <Field label="Congestion now">
              <Num value={destination.observedCongestionIndex ?? destination.congestionIndex} digits={1} />
            </Field>
            <Field label="Congestion at arrival">
              <Num value={congestionOnArrival} digits={1} />
            </Field>
            <Field label="Predicted berth wait">
              <Num value={destination.delayHours} digits={1} unit="h" />
            </Field>
            <Field label="Queue ahead of you" hint="From the berth queue over predicted arrivals.">
              {slot ? (
                <span className="num">
                  berth {slot.berth + 1} · wait {slot.waitHours.toFixed(1)}h
                </span>
              ) : (
                <span className="text-[var(--text-3)]">n/a</span>
              )}
            </Field>
            <div className="mt-1 flex items-center gap-1.5">
              <ProvenanceTag
                status={destination.dataStatus}
                ageHours={destination.dataAgeHours}
                detail={`Port state observed ${destination.observedAt ?? "—"}`}
              />
              <span className="text-[10px] text-[var(--text-3)]">
                model {destination.model ?? "—"}
              </span>
            </div>
          </>
        ) : (
          <EmptyNote>
            This passage ends at a gateway outside the modelled port set, so there is no
            congestion forecast for it.
          </EmptyNote>
        )}
      </PanelSection>

      {/* ---------------------------------------------- nearby traffic -- */}
      <PanelSection title="Nearby traffic" right={`${contacts.length} within 45 nm`}>
        {contacts.length === 0 ? (
          <p className="text-[10.5px] text-[var(--text-3)]">No contact within 45 nautical miles.</p>
        ) : (
          <ul className="space-y-[2px]">
            {contacts.map((contact) => (
              <li key={contact.fix.id}>
                <button
                  type="button"
                  onClick={() => onSelectVessel?.(contact.fix.id)}
                  className="grid w-full grid-cols-[1fr_44px_46px_50px] items-baseline gap-1.5 rounded-[2px] px-1 py-[2px] text-left hover:bg-[var(--panel-3)]"
                >
                  <span className="min-w-0 truncate text-[10.5px] text-[var(--text-2)]">
                    {contact.fix.name}
                  </span>
                  <span className="num text-right text-[10px] text-[var(--text-3)]">
                    {contact.rangeNm.toFixed(1)}nm
                  </span>
                  <span className="num text-right text-[10px] text-[var(--text-3)]">
                    {formatBearing(contact.bearing)}
                  </span>
                  <span
                    className={cn(
                      "num text-right text-[10px]",
                      contact.computable && contact.cpa.cpaNm < 1 && contact.cpa.tcpaMinutes > 0
                        ? "text-[var(--warn)]"
                        : "text-[var(--text-3)]",
                    )}
                    title={
                      contact.computable
                        ? `CPA ${contact.cpa.cpaNm.toFixed(2)} nm in ${contact.cpa.tcpaMinutes.toFixed(0)} min`
                        : "Both vessels must be making way for a CPA to mean anything."
                    }
                  >
                    {contact.computable ? `${contact.cpa.cpaNm.toFixed(1)}nm` : "—"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-1 text-[9px] leading-snug text-[var(--text-3)]">
          CPA assumes both vessels hold course and speed. A contact at anchor shows range and
          bearing only.
        </p>
      </PanelSection>

      {/* ------------------------------------------------ recommendation -- */}
      <PanelSection title="Recommendation">
        <div className="flex items-center gap-1.5">
          <Pill
            tone={advice.level === "act" ? "warn" : advice.level === "adjust" ? "info" : "ok"}
            solid
          >
            {advice.headline}
          </Pill>
        </div>
        <p className="mt-1.5 text-[11px] leading-snug text-[var(--text-2)]">{advice.detail}</p>
        <div className="mt-1 flex items-baseline justify-between gap-2 text-[9.5px] text-[var(--text-3)]">
          <span className="truncate">{advice.basis}</span>
          {advice.confidence != null ? (
            <span className="num">conf {advice.confidence.toFixed(2)}</span>
          ) : null}
        </div>
      </PanelSection>

      <div className="px-2 py-1.5 text-[9.5px] text-[var(--text-3)]">
        Source: {source.info.provider}
      </div>
    </FloatPanel>
  );
}

/* ------------------------------------------------------------ hover card -- */

export function VesselHoverCard({ fix }: { fix: VesselFix }) {
  const spec = VESSEL_CLASSES[fix.vesselClass];
  return (
    <div>
      <div className="mb-1 flex items-center gap-1.5">
        <span
          aria-hidden
          className="h-[8px] w-[8px] shrink-0 rounded-[1px]"
          style={{ background: spec.color }}
        />
        <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium text-[var(--text)]">
          {fix.name}
        </span>
        <Pill tone={STATUS_TONE[fix.status]}>{NAV_STATUS_LABEL[fix.status]}</Pill>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-[2px] text-[10.5px]">
        <dt className="text-[var(--text-3)]">Type</dt>
        <dd className="text-right text-[var(--text-2)]">{spec.label}</dd>
        <dt className="text-[var(--text-3)]">Speed</dt>
        <dd className="num text-right text-[var(--text-2)]">{fix.sogKn.toFixed(1)} kn</dd>
        <dt className="text-[var(--text-3)]">Heading</dt>
        <dd className="num text-right text-[var(--text-2)]">
          {formatBearing(fix.cog)} {compassPoint(fix.cog)}
        </dd>
        <dt className="text-[var(--text-3)]">Route</dt>
        <dd className="truncate text-right text-[var(--text-2)]">
          {waypoint(fix.originId)?.name?.split(" (")[0] ?? "—"} →{" "}
          {waypoint(fix.destinationId)?.name?.split(" (")[0] ?? "—"}
        </dd>
        <dt className="text-[var(--text-3)]">
          {fix.etaKind === "berthing" ? "Berthing" : fix.etaKind === "departure" ? "Departs" : "ETA"}
        </dt>
        <dd className="num text-right text-[var(--text-2)]">{clockZ(fix.etaMs)}</dd>
      </dl>
      <div className="mt-1 border-t border-[var(--line)] pt-1 text-[9px] text-[var(--unc)]">
        SIMULATED position · click to inspect
      </div>
    </div>
  );
}
