/**
 * What a controller and a master actually need from a fleet of fixes.
 *
 * Three derivations live here, and each one is arithmetic on values the product
 * already has rather than a new invented number:
 *
 *   port traffic      the fixes around one port, split by what they are doing.
 *   arrival sequence  a deterministic berth queue over the predicted arrivals,
 *                     which is what turns a list of ETAs into a berth wait.
 *   nearby traffic    range, bearing and CPA around one vessel.
 *
 * The advice at the end is a restatement of those three plus the forecast the
 * model already produced. It never introduces a threshold the rest of the
 * pipeline does not use.
 */

import type { ForecastPoint, PortSnapshot } from "@/types/portwatch";
import {
  closestPointOfApproach,
  compassPoint,
  haversineKm,
  type CpaResult,
} from "./geo";
import type { NavStatus, VesselClass, VesselFix } from "./traffic-types";

const HOUR_MS = 3_600_000;
const KM_PER_NM = 1.852;

/* ---------------------------------------------------------- port traffic -- */

export interface PortTraffic {
  portCode: string;
  inbound: VesselFix[];
  outbound: VesselFix[];
  anchored: VesselFix[];
  waiting: VesselFix[];
  moored: VesselFix[];
  service: VesselFix[];
  /** Under way through the area but not calling here. */
  passing: VesselFix[];
  /** Everything above, in one list. */
  all: VesselFix[];
}

/**
 * Traffic relevant to one port.
 *
 * "Relevant" is deliberately wider than "calling here": a controller watching a
 * fairway needs the ship crossing the approach as much as the one booked in,
 * so anything under way inside the radius that is bound elsewhere is kept and
 * marked as passing.
 */
export function portTraffic(
  fixes: VesselFix[],
  port: { code: string; lat: number; lon: number },
  radiusNm = 90,
): PortTraffic {
  const radiusKm = radiusNm * KM_PER_NM;
  const traffic: PortTraffic = {
    portCode: port.code,
    inbound: [],
    outbound: [],
    anchored: [],
    waiting: [],
    moored: [],
    service: [],
    passing: [],
    all: [],
  };

  for (const fix of fixes) {
    const km = haversineKm([fix.lon, fix.lat], [port.lon, port.lat]);
    const near = km <= radiusKm;
    const bound = fix.destinationId === port.code;
    const departing = fix.originId === port.code;

    if (!near && !(bound && fix.remainingKm < 1400)) continue;

    switch (fix.status) {
      case "moored":
        if (near) traffic.moored.push(fix);
        break;
      case "anchored":
        if (near) traffic.anchored.push(fix);
        break;
      case "waiting":
        if (near) traffic.waiting.push(fix);
        break;
      case "service":
        if (near) traffic.service.push(fix);
        break;
      case "inbound":
        if (bound) traffic.inbound.push(fix);
        else if (near) traffic.passing.push(fix);
        break;
      case "outbound":
        if (departing) traffic.outbound.push(fix);
        else if (near) traffic.passing.push(fix);
        break;
      default:
        if (bound && fix.remainingKm < 1400) traffic.inbound.push(fix);
        else if (near) traffic.passing.push(fix);
    }
  }

  const byEta = (a: VesselFix, b: VesselFix) => (a.etaMs ?? 0) - (b.etaMs ?? 0);
  traffic.inbound.sort(byEta);
  traffic.outbound.sort(byEta);
  traffic.waiting.sort(byEta);
  traffic.anchored.sort(byEta);
  traffic.moored.sort(byEta);
  traffic.all = [
    ...traffic.inbound,
    ...traffic.waiting,
    ...traffic.anchored,
    ...traffic.moored,
    ...traffic.outbound,
    ...traffic.passing,
    ...traffic.service,
  ];
  return traffic;
}

export function distanceNm(fix: VesselFix, point: { lat: number; lon: number }): number {
  return haversineKm([fix.lon, fix.lat], [point.lon, point.lat]) / KM_PER_NM;
}

/* ------------------------------------------------------- arrival queueing -- */

/**
 * How long a vessel of this class occupies a berth.
 *
 * Class envelopes scaled by length. These are working assumptions, not measured
 * turnarounds -- the pipeline has no per-call berth log -- and the panel that
 * uses them says so. What they buy is a queue that behaves like a queue: a
 * capesize bulker blocks a berth for a day and a half and a feeder does not.
 */
export function berthHoursFor(vesselClass: VesselClass, lengthM: number): number {
  const base: Record<VesselClass, [number, number]> = {
    container: [9, 20],
    tanker: [14, 26],
    bulk: [20, 40],
    lng: [11, 18],
    roro: [7, 13],
    cargo: [12, 24],
    passenger: [4, 9],
    service: [1, 3],
  };
  const [lo, hi] = base[vesselClass];
  const span = vesselClass === "service" ? 80 : 300;
  const scale = Math.min(1, Math.max(0, (lengthM - 90) / span));
  return lo + (hi - lo) * scale;
}

/** The mean of the class envelopes, used as the reference for scaling. */
const MEAN_CLASS_BERTH_HOURS = 19;

/**
 * Scale the class envelopes to what this port's own numbers imply.
 *
 * A queue is only meaningful if its service rate matches the throughput the
 * feed measured. JNPA turns eighteen vessels a day across thirteen berths; hold
 * a bulker on a berth for forty hours and the queue is unstable by
 * construction, and the panel reports a wait that is an artefact of the
 * assumption rather than a berth problem.
 *
 *   berth-hours available per day = berths x 24 x utilisation
 *   mean service time             = that, divided by daily calls
 *
 * Both inputs are measured. Where either is missing the scale falls back to 1
 * and the envelopes stand on their own.
 */
export function berthScaleFor(port: PortSnapshot): number {
  const berths = port.berthCount ?? null;
  const calls = port.vesselCalls ?? null;
  const utilisation = port.utilization ?? null;
  if (!berths || !calls || !utilisation) return 1;
  const meanServiceHours = (berths * 24 * utilisation) / calls;
  return Math.min(1.4, Math.max(0.3, meanServiceHours / MEAN_CLASS_BERTH_HOURS));
}

export type ArrivalRisk = "low" | "medium" | "high";

export interface ArrivalSlot {
  fix: VesselFix;
  etaMs: number;
  /** Berth index the queue assigned. */
  berth: number;
  berthHours: number;
  /** When the queue can actually take the vessel alongside. */
  alongsideMs: number;
  /** Hours between arriving and going alongside. */
  waitHours: number;
  /** Arrival that removes the wait without changing the berthing time. */
  recommendedEtaMs: number;
  /** Speed that meets the recommended arrival, knots. */
  recommendedSpeedKn: number | null;
  savedHours: number;
  /** Forecast congestion index for the day the vessel arrives. */
  congestionAtArrival: number | null;
  risk: ArrivalRisk;
}

export interface ArrivalPlan {
  slots: ArrivalSlot[];
  berths: number;
  /** Total anchor time across the sequence as it stands. */
  totalWaitHours: number;
  /** Total anchor time if every vessel took its recommended arrival. */
  staggeredWaitHours: number;
  /** Berths already occupied when the sequence starts. */
  occupied: number;
}

/**
 * A deterministic berth queue over the predicted arrivals.
 *
 * Berths free up when the vessels alongside are due to sail -- which the replay
 * already knows -- and each arrival takes the earliest berth that can have it.
 * The recommended arrival is the same berthing time reached by steaming slower,
 * so the vessel spends the difference at sea rather than at anchor. That is the
 * whole argument for staggering, and the panel shows both numbers.
 */
export function arrivalSequence(
  traffic: PortTraffic,
  port: PortSnapshot,
  options: { at: number; forecast?: ForecastPoint[] } = { at: Date.now() },
): ArrivalPlan {
  const berths = Math.max(2, port.berthCount ?? 8);
  const now = options.at;

  const scale = berthScaleFor(port);

  /*
   * When each berth next comes free.
   *
   * Two sources, and the later of the two wins. The vessels alongside carry
   * their own sailing times, which is the concrete part. The model's predicted
   * berth wait is the backlog it forecasts for the whole facility, staggered
   * across the berths so a ship arriving now waits about what the pipeline says
   * it will -- which is what stops the map contradicting the forecast beside it.
   */
  const backlogHours = Math.max(0, port.delayHours ?? 0);
  const occupiedUntil = traffic.moored
    .map((fix) => fix.etaMs ?? now)
    .sort((a, b) => a - b)
    .slice(0, berths);
  const free: number[] = Array.from({ length: berths }, (_, index) =>
    Math.max(
      occupiedUntil[index] ?? now,
      now + (backlogHours * index * HOUR_MS) / Math.max(1, berths - 1),
    ),
  ).sort((a, b) => a - b);

  // Two days of arrivals. Beyond that the queue is stacking ships that have not
  // sailed yet, and a controller reading "wait 51h" would be reading an artefact
  // of the horizon rather than a berth problem.
  const horizonMs = now + 48 * HOUR_MS;
  const queue = [...traffic.waiting, ...traffic.anchored, ...traffic.inbound]
    .filter((fix) => (fix.etaMs ?? now) <= horizonMs)
    .sort((a, b) => (a.etaMs ?? 0) - (b.etaMs ?? 0));

  const slots: ArrivalSlot[] = [];
  let totalWaitHours = 0;

  for (const fix of queue) {
    const etaMs = fix.etaMs ?? now;
    const berthHours = berthHoursFor(fix.vesselClass, fix.lengthM) * scale;

    let berth = 0;
    for (let i = 1; i < free.length; i += 1) {
      if (free[i] < free[berth]) berth = i;
    }
    const alongsideMs = Math.max(etaMs, free[berth]);
    free[berth] = alongsideMs + berthHours * HOUR_MS;

    const waitHours = Math.max(0, (alongsideMs - etaMs) / HOUR_MS);
    totalWaitHours += waitHours;

    const recommendedHours = Math.max(0.1, (alongsideMs - now) / HOUR_MS);
    const recommendedSpeedKn =
      fix.remainingKm > 1 && fix.sogKn > 0.5
        ? Math.max(4, (fix.remainingKm / KM_PER_NM) / recommendedHours)
        : null;

    slots.push({
      fix,
      etaMs,
      berth,
      berthHours,
      alongsideMs,
      waitHours,
      recommendedEtaMs: alongsideMs,
      recommendedSpeedKn,
      savedHours: waitHours,
      congestionAtArrival: congestionAt(port, options.forecast, etaMs),
      risk: waitHours >= 8 ? "high" : waitHours >= 3 ? "medium" : "low",
    });
  }

  return {
    slots,
    berths,
    totalWaitHours,
    // Staggering removes the anchor time, not the berthing time: the vessel
    // still goes alongside when a berth frees, it simply arrives then.
    staggeredWaitHours: 0,
    occupied: occupiedUntil.length,
  };
}

/** The model's congestion index for the day a vessel arrives. */
export function congestionAt(
  port: PortSnapshot,
  forecast: ForecastPoint[] | undefined,
  atMs: number,
): number | null {
  if (!forecast?.length) return port.congestionIndex ?? null;
  const points = forecast
    .map((point) => ({
      ms: point.targetDate ? Date.parse(point.targetDate) : NaN,
      value: point.congestionIndex,
    }))
    .filter((point) => !Number.isNaN(point.ms))
    .sort((a, b) => a.ms - b.ms);
  if (!points.length) return port.congestionIndex ?? null;
  if (atMs <= points[0].ms) return points[0].value;
  if (atMs >= points[points.length - 1].ms) return points[points.length - 1].value;
  for (let i = 1; i < points.length; i += 1) {
    if (atMs <= points[i].ms) {
      const span = points[i].ms - points[i - 1].ms;
      const f = span > 0 ? (atMs - points[i - 1].ms) / span : 0;
      return points[i - 1].value + (points[i].value - points[i - 1].value) * f;
    }
  }
  return points[points.length - 1].value;
}

/* -------------------------------------------------------- nearby traffic -- */

export interface NearbyContact {
  fix: VesselFix;
  rangeNm: number;
  bearing: number;
  bearingPoint: string;
  cpa: CpaResult;
  /** True when both vessels are making way, so the CPA means something. */
  computable: boolean;
}

/**
 * Contacts around one vessel.
 *
 * The CPA is only meaningful while both vessels hold course and speed, so a
 * contact at anchor is reported with its range and bearing and the CPA is
 * marked as not computable rather than printed as a reassuring large number.
 */
export function nearbyTraffic(
  own: VesselFix,
  fixes: VesselFix[],
  radiusNm = 40,
  limit = 12,
): NearbyContact[] {
  const contacts: NearbyContact[] = [];
  for (const fix of fixes) {
    if (fix.id === own.id) continue;
    const rangeNm = distanceNm(fix, { lat: own.lat, lon: own.lon });
    if (rangeNm > radiusNm) continue;
    const cpa = closestPointOfApproach(
      { lon: own.lon, lat: own.lat, cog: own.cog, sogKn: own.sogKn },
      { lon: fix.lon, lat: fix.lat, cog: fix.cog, sogKn: fix.sogKn },
    );
    contacts.push({
      fix,
      rangeNm,
      bearing: cpa.bearing,
      bearingPoint: compassPoint(cpa.bearing),
      cpa,
      computable: own.sogKn > 0.5 && fix.sogKn > 0.5,
    });
  }
  contacts.sort((a, b) => {
    const closing = (contact: NearbyContact) =>
      contact.computable && contact.cpa.tcpaMinutes > 0 && contact.cpa.tcpaMinutes < 180
        ? contact.cpa.cpaNm
        : contact.rangeNm + 1000;
    return closing(a) - closing(b);
  });
  return contacts.slice(0, limit);
}

/* ---------------------------------------------------------------- advice -- */

export type AdviceLevel = "hold" | "adjust" | "act";

export interface VesselAdvice {
  headline: string;
  detail: string;
  level: AdviceLevel;
  /** Where the recommendation came from, named so it can be argued with. */
  basis: string;
  confidence: number | null;
}

export interface AdviceInputs {
  fix: VesselFix;
  port: PortSnapshot | null;
  slot: ArrivalSlot | null;
  worstExposure: { level: "normal" | "watch" | "severe"; leadHours: number } | null;
  closestContact: NearbyContact | null;
  /** The routing artefact's own reroute call, for a vessel it scored. */
  reroute?: { to: string; savedWaitHours: number | null } | null;
}

/**
 * The one instruction shown against a vessel.
 *
 * Ordered by what would actually change a bridge decision first: a close-quarters
 * situation, then severe weather on the leg, then a berth wait worth slowing
 * down for, then the optimizer's reroute, then hold. Every branch restates a
 * number that is already on the screen.
 */
export function vesselAdvice(input: AdviceInputs): VesselAdvice {
  const { fix, port, slot, worstExposure, closestContact, reroute } = input;

  if (
    closestContact?.computable &&
    closestContact.cpa.cpaNm < 0.6 &&
    closestContact.cpa.tcpaMinutes > 0 &&
    closestContact.cpa.tcpaMinutes < 45
  ) {
    return {
      headline: "MONITOR CLOSE QUARTERS",
      detail: `${closestContact.fix.name} closes to ${closestContact.cpa.cpaNm.toFixed(2)} nm in ${Math.round(closestContact.cpa.tcpaMinutes)} min on a steady course.`,
      level: "act",
      basis: "Closest point of approach under constant velocity",
      confidence: null,
    };
  }

  if (worstExposure?.level === "severe") {
    return {
      headline: "WATCH WEATHER CELL",
      detail: `Severe conditions forecast on this leg about ${Math.round(worstExposure.leadHours)}h out. Review passage timing before committing to the approach.`,
      level: "act",
      basis: "Forecast weather impact sampled along the remaining passage",
      confidence: null,
    };
  }

  if (reroute && reroute.savedWaitHours != null && reroute.savedWaitHours < -0.5) {
    return {
      headline: `REROUTE VIA ${reroute.to.toUpperCase()}`,
      detail: `The route optimizer scores the alternative call lower even after the diversion penalty, with ${Math.abs(reroute.savedWaitHours).toFixed(1)}h less berth wait.`,
      level: "act",
      basis: "Route optimizer artefact",
      confidence: port?.confidence ?? null,
    };
  }

  if (slot && slot.waitHours >= 2 && slot.recommendedSpeedKn != null) {
    const delta = fix.sogKn - slot.recommendedSpeedKn;
    if (delta >= 0.3) {
      return {
        headline: `SLOW STEAM ${delta.toFixed(1)} KN`,
        detail: `Berth is predicted free in ${((slot.alongsideMs - fix.at) / HOUR_MS).toFixed(1)}h. Making ${slot.recommendedSpeedKn.toFixed(1)} kn arrives on the berth instead of waiting ${slot.waitHours.toFixed(1)}h at anchor.`,
        level: "adjust",
        basis: "Berth queue over predicted arrivals",
        confidence: port?.confidence ?? null,
      };
    }
    return {
      headline: `DELAY ARRIVAL ${slot.waitHours.toFixed(0)}H`,
      detail: `Every berth is committed until ${new Date(slot.alongsideMs).toUTCString().slice(17, 22)}Z. Arriving then avoids ${slot.waitHours.toFixed(1)}h in the anchorage.`,
      level: "adjust",
      basis: "Berth queue over predicted arrivals",
      confidence: port?.confidence ?? null,
    };
  }

  if (worstExposure?.level === "watch") {
    return {
      headline: "MAINTAIN COURSE, WEATHER WATCH",
      detail: `Elevated weather impact on the leg about ${Math.round(worstExposure.leadHours)}h out. No action needed yet.`,
      level: "hold",
      basis: "Forecast weather impact sampled along the remaining passage",
      confidence: null,
    };
  }

  return {
    headline: "MAINTAIN COURSE",
    detail: port
      ? `${port.name} is in ${port.regime} regime with a predicted wait of ${(port.delayHours ?? 0).toFixed(1)}h. Nothing on the passage argues for a change.`
      : "Nothing on the passage argues for a change.",
    level: "hold",
    basis: "Forecast and berth queue at the destination",
    confidence: port?.confidence ?? null,
  };
}

/* -------------------------------------------------------------- grouping -- */

export const STATUS_TONE: Record<NavStatus, "ok" | "info" | "warn" | "crit" | "unc" | "neutral"> = {
  underway: "neutral",
  inbound: "info",
  outbound: "ok",
  anchored: "unc",
  waiting: "warn",
  moored: "neutral",
  service: "neutral",
};

export function countByStatus(fixes: VesselFix[]): Record<NavStatus, number> {
  const counts: Record<NavStatus, number> = {
    underway: 0,
    inbound: 0,
    outbound: 0,
    anchored: 0,
    waiting: 0,
    moored: 0,
    service: 0,
  };
  for (const fix of fixes) counts[fix.status] += 1;
  return counts;
}
