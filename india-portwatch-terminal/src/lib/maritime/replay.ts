/**
 * The deterministic traffic replay engine.
 *
 * India PortWatch has no per-vessel AIS licence. Rather than draw three rows
 * from the routing artefact and call it a traffic picture, this generates a
 * full fleet and moves it along the water-only route catalogue — and declares
 * itself as SIMULATED_TRAFFIC everywhere it surfaces. Nothing here is presented
 * as an observation.
 *
 * Three properties make it usable as more than decoration:
 *
 *   deterministic  a vessel's whole voyage is a closed-form function of its
 *                  seed and the clock, so two runs, two machines and a
 *                  screenshot taken a week apart agree exactly.
 *   stateless      a fix is computed from the time, never accumulated, so
 *                  scrubbing the timeline backwards is as exact as running
 *                  forwards and nothing drifts.
 *   geographic     every position sits on a catalogue leg, which means every
 *                  position is on water and every track is a plausible passage.
 *
 * Density is driven by the port artefacts: a port with eighteen daily calls and
 * high queue pressure gets more ships at anchor than one with five. The traffic
 * is invented, but the shape of it is not arbitrary.
 */

import type { PortSnapshot } from "@/types/portwatch";
import {
  bearingDeg,
  destination,
  fixAt,
  haversineKm,
  measurePath,
  slicePath,
  type Position,
} from "./geo";
import {
  PORT_WAYPOINTS,
  seaRoute,
  WAYPOINTS,
  waypoint,
  type SeaRoute,
  type Waypoint,
} from "./searoutes";
import { seawardBearing } from "./port-geometry";
import { isWater, nudgeToWater } from "./water";
import {
  VESSEL_CLASSES,
  type NavStatus,
  type TrafficSource,
  type TrafficSourceInfo,
  type Vessel,
  type VesselClass,
  type VesselFix,
} from "./traffic-types";

const KN_TO_KMH = 1.852;
const HOUR_MS = 3_600_000;

/* ------------------------------------------------------------------ rng --- */

/** xmur3: string to a well-mixed 32-bit seed. */
function hashSeed(text: string): number {
  let h = 1779033703 ^ text.length;
  for (let i = 0; i < text.length; i += 1) {
    h = Math.imul(h ^ text.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return (h ^= h >>> 16) >>> 0;
}

/** mulberry32: small, fast, and identical everywhere it runs. */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function pick<T>(random: () => number, list: readonly T[]): T {
  return list[Math.floor(random() * list.length) % list.length];
}

function between(random: () => number, lo: number, hi: number): number {
  return lo + random() * (hi - lo);
}

/* ----------------------------------------------------------------- names -- */

/**
 * Operator names are invented.
 *
 * A screenshot of this product shows a hundred ships with names, speeds and
 * ETAs. Putting a real carrier's brand on a generated position would create a
 * plausible record of a voyage that never happened, which is exactly the class
 * of thing the rest of this codebase refuses to do. These read like the
 * industry without belonging to anyone in it.
 */
const OPERATORS = [
  "Coromandel", "Konkan", "Malabar", "Deccan", "Andaman", "Nicobar",
  "Laccadive", "Kachchh", "Godavari", "Mahanadi", "Narmada", "Zuari",
  "Palar", "Vaigai", "Periyar", "Sharavathi", "Chilika", "Rann",
] as const;

const SHIP_NAMES = [
  "Aurora", "Meridian", "Vanguard", "Horizon", "Sentinel", "Voyager",
  "Endeavour", "Trader", "Pioneer", "Mariner", "Ranger", "Kestrel",
  "Lyra", "Orion", "Vega", "Rigel", "Altair", "Sirius", "Corvus",
  "Compass", "Beacon", "Tempest", "Monsoon", "Zephyr", "Spinnaker",
  "Halyard", "Capstan", "Fathom", "Leeward", "Windward", "Bearing",
  "Azimuth", "Sextant", "Astrolabe", "Quadrant", "Bowline", "Jetstream",
  "Cascade", "Trident", "Nautilus", "Corsair", "Pelican", "Frigate",
  "Albatross", "Cormorant", "Petrel", "Skua", "Tern", "Gannet",
] as const;

const SERVICE_NAMES = [
  "Pilot", "Tug", "Bunker", "Survey", "Dredger", "Patrol", "Line Boat",
] as const;

const FLAGS = ["IN", "SG", "PA", "LR", "MT", "HK", "MH", "CY", "AE", "LK"] as const;

/* --------------------------------------------------------------- classes -- */

const CLASS_KEYS = Object.keys(VESSEL_CLASSES) as VesselClass[];
const CUMULATIVE_SHARE = (() => {
  const out: Array<[VesselClass, number]> = [];
  let total = 0;
  for (const key of CLASS_KEYS) {
    if (key === "service") continue;
    total += VESSEL_CLASSES[key].share;
    out.push([key, total]);
  }
  return out.map(([key, value]) => [key, value / total] as [VesselClass, number]);
})();

function pickClass(random: () => number): VesselClass {
  const roll = random();
  for (const [key, edge] of CUMULATIVE_SHARE) {
    if (roll <= edge) return key;
  }
  return "cargo";
}

/* ------------------------------------------------------------- port lore -- */

interface PortLore {
  id: string;
  name: string;
  short: string;
  lon: number;
  lat: number;
  seaward: number;
  /** Daily calls from the AIS aggregate, or a floor where none was measured. */
  calls: number;
  anchorageCount: number;
  queuePressure: number;
  berths: number;
  waitHours: number;
  risk: string;
}

function buildPortLore(ports: PortSnapshot[]): Map<string, PortLore> {
  const lore = new Map<string, PortLore>();
  const byCode = new Map(ports.map((port) => [port.code, port]));
  for (const wp of PORT_WAYPOINTS) {
    const port = byCode.get(wp.id) ?? null;
    lore.set(wp.id, {
      id: wp.id,
      name: port?.name ?? wp.name,
      short: port?.short ?? wp.id.slice(2),
      lon: wp.lon,
      lat: wp.lat,
      seaward: seawardBearing(wp.id, wp.lon, wp.lat),
      calls: Math.max(3, port?.vesselCalls ?? 4),
      anchorageCount: port?.anchorageCount ?? 1,
      queuePressure: port?.queuePressure ?? 0.25,
      berths: Math.max(4, port?.berthCount ?? 8),
      waitHours: port?.delayHours ?? 6,
      risk: port?.risk ?? "normal",
    });
  }
  return lore;
}

/* -------------------------------------------------------------- voyages --- */

/** The state a designed vessel is meant to be in at the replay epoch. */
type Seat = "transit" | "approach" | "inbound" | "outbound" | "anchored" | "moored" | "service";

interface Voyage {
  vessel: Vessel;
  route: SeaRoute;
  /** Waypoint the outbound leg starts from. */
  fromId: string;
  toId: string;
  legHours: number;
  stayAtToHours: number;
  stayAtFromHours: number;
  cycleHours: number;
  /** Position in the cycle at the epoch, 0 to 1. */
  phase: number;
  /** Share of a port stay spent at anchor before going alongside. */
  anchorShare: number;
  anchorAt: Position;
  anchorFrom: Position;
  berthAt: Position;
  berthFrom: Position;
  /** Anchored vessels at a pressured port read as waiting for a berth. */
  waits: boolean;
  /** Service craft orbit a port instead of running a leg. */
  orbit: { centre: Position; km: number; periodHours: number } | null;
  /**
   * How far to starboard of the passage centreline this vessel runs, in km.
   *
   * Every ship on a leg shares one polyline, so without an offset they stack on
   * top of each other: the chart shows one thick line instead of traffic, and a
   * closest-point-of-approach between two of them is zero for the wrong reason.
   * Offsetting to starboard is also what a separation scheme does, so opposing
   * traffic on the same leg naturally splits into two lanes.
   */
  laneKm: number;
}

function anchoragePoint(lore: PortLore, random: () => number): Position {
  const spread = between(random, -46, 46);
  const km = between(random, 6, 11 + Math.min(20, lore.anchorageCount * 3.2 + lore.queuePressure * 15));
  const point = destination([lore.lon, lore.lat], lore.seaward + spread, km);
  return nudgeToWater(point[0], point[1]);
}

function berthPoint(lore: PortLore, random: () => number): Position {
  const point = destination(
    [lore.lon, lore.lat],
    lore.seaward + between(random, -70, 70),
    between(random, 1.4, 4.6),
  );
  return nudgeToWater(point[0], point[1]);
}

/**
 * Place a vessel in the cycle so it is in `seat` at the epoch.
 *
 * The cycle runs: outbound leg, stay at the far port, return leg, stay at the
 * home port. Choosing the phase rather than the state keeps the engine
 * closed-form -- the seat is only an opening position, and the vessel leaves it
 * on its own as the clock runs.
 */
function phaseForSeat(
  seat: Seat,
  random: () => number,
  legHours: number,
  stayAtToHours: number,
  stayAtFromHours: number,
  cycleHours: number,
  anchorShare: number,
): number {
  const at = (hours: number) => hours / cycleHours;
  switch (seat) {
    case "approach":
      // Inside the last fifty kilometres or so: the ships a harbour view has to
      // show, because a port picture with an empty approach is not a picture.
      return at(legHours * between(random, 0.955, 0.999));
    case "inbound":
      // Still running in. Spread wide enough that the arrival sequence covers a
      // shift rather than an hour: eighteen ships all thirty minutes out is not
      // a queue, it is a pile-up.
      return at(legHours * between(random, 0.62, 0.95));
    case "outbound":
      // Recently clear of the home port on the return leg.
      return at(legHours + stayAtToHours + legHours * between(random, 0.005, 0.2));
    case "anchored":
      return at(legHours + stayAtToHours * between(random, 0.02, Math.max(0.05, anchorShare - 0.02)));
    case "moored":
      return at(legHours + stayAtToHours * between(random, anchorShare + 0.03, 0.97));
    case "service":
    case "transit":
    default:
      return random();
  }
}

function designVoyage(
  id: string,
  fromId: string,
  toId: string,
  seat: Seat,
  lore: Map<string, PortLore>,
  options: { owned?: boolean; forcedClass?: VesselClass; name?: string } = {},
): Voyage | null {
  const route = seaRoute(fromId, toId);
  if (!route) return null;

  const random = rng(hashSeed(id));
  const vesselClass = options.forcedClass ?? (seat === "service" ? "service" : pickClass(random));
  const spec = VESSEL_CLASSES[vesselClass];
  const serviceSpeedKn = Number(between(random, spec.speedKn[0], spec.speedKn[1]).toFixed(1));
  const lengthM = Math.round(between(random, spec.lengthM[0], spec.lengthM[1]));

  const operator = pick(random, OPERATORS);
  const name =
    options.name ??
    (vesselClass === "service"
      ? `${lore.get(toId)?.short ?? toId.slice(2)} ${pick(random, SERVICE_NAMES)} ${1 + Math.floor(random() * 9)}`
      : `${operator} ${pick(random, SHIP_NAMES)}`);

  const legHours = route.km / (serviceSpeedKn * KN_TO_KMH);
  const toLore = lore.get(toId);
  const fromLore = lore.get(fromId);
  const stayAtToHours = toLore
    ? between(random, 14, 26) + toLore.waitHours * between(random, 0.6, 1.4)
    : between(random, 10, 20);
  const stayAtFromHours = fromLore
    ? between(random, 14, 26) + fromLore.waitHours * between(random, 0.6, 1.4)
    : between(random, 10, 20);
  const cycleHours = legHours * 2 + stayAtToHours + stayAtFromHours;

  const anchorShare = toLore
    ? Math.min(0.75, 0.12 + toLore.queuePressure * 0.75)
    : 0.2;

  const anchorLore = toLore ?? fromLore;
  const homeLore = fromLore ?? toLore;

  const digits = hashSeed(`${id}:replay`).toString().padStart(9, "0").slice(0, 8);

  return {
    vessel: {
      id,
      replayId: `SIM-${digits}`,
      imo: null,
      name,
      operator: vesselClass === "service" ? `${toLore?.name ?? toId} port services` : `${operator} Lines`,
      callsign: `V${digits.slice(0, 4)}`,
      flag: pick(random, FLAGS),
      vesselClass,
      lengthM,
      beamM: Math.round(lengthM * between(random, 0.13, 0.17)),
      draughtM: Number(between(random, 6.5, 15.8).toFixed(1)),
      dwt: Math.round(lengthM * between(random, 180, 420)),
      originId: fromId,
      destinationId: toId,
      homePortId: WAYPOINTS[toId]?.kind === "port" ? toId : (WAYPOINTS[fromId]?.kind === "port" ? fromId : null),
      serviceSpeedKn,
      owned: options.owned === true,
    },
    route,
    fromId,
    toId,
    legHours,
    stayAtToHours,
    stayAtFromHours,
    cycleHours,
    phase: phaseForSeat(seat, random, legHours, stayAtToHours, stayAtFromHours, cycleHours, anchorShare),
    anchorShare,
    anchorAt: anchorLore ? anchoragePoint(anchorLore, random) : [route.path.coords[0][0], route.path.coords[0][1]],
    anchorFrom: homeLore ? anchoragePoint(homeLore, random) : [route.path.coords[0][0], route.path.coords[0][1]],
    berthAt: anchorLore ? berthPoint(anchorLore, random) : [WAYPOINTS[toId].lon, WAYPOINTS[toId].lat],
    berthFrom: homeLore ? berthPoint(homeLore, random) : [WAYPOINTS[fromId].lon, WAYPOINTS[fromId].lat],
    waits: (toLore?.queuePressure ?? 0) >= 0.42 && random() < 0.66,
    laneKm: between(random, 0.6, 4.2),
    orbit:
      seat === "service" && toLore
        ? {
            centre: [toLore.lon, toLore.lat],
            km: between(random, 3, 13),
            periodHours: between(random, 2.5, 7),
          }
        : null,
  };
}

/* ------------------------------------------------------------ resolution -- */

const APPROACH_KM = 55;

function resolve(voyage: Voyage, at: number, epoch: number): VesselFix {
  const { vessel, route } = voyage;

  if (voyage.orbit) {
    // Harbour craft do not run a passage; they work a sector of the approach.
    const turns = ((at - epoch) / HOUR_MS) / voyage.orbit.periodHours + voyage.phase;
    const angle = (turns % 1) * 360;
    const point = nudgeToWater(
      ...destination(voyage.orbit.centre, angle, voyage.orbit.km),
    );
    const ahead = destination(voyage.orbit.centre, angle + 6, voyage.orbit.km);
    return {
      ...vessel,
      at,
      lon: point[0],
      lat: point[1],
      cog: bearingDeg(point, ahead),
      heading: bearingDeg(point, ahead),
      sogKn: vessel.serviceSpeedKn * 0.55,
      status: "service",
      progress: 0,
      travelledKm: 0,
      remainingKm: 0,
      etaMs: null,
      etaMinutes: null,
      etaKind: null,
      routeKey: null,
    };
  }

  const elapsedHours = (at - epoch) / HOUR_MS;
  const cyclePosition =
    (((voyage.phase + elapsedHours / voyage.cycleHours) % 1) + 1) % 1;
  const s = cyclePosition * voyage.cycleHours;

  const outboundEnd = voyage.legHours;
  const stayToEnd = outboundEnd + voyage.stayAtToHours;
  const returnEnd = stayToEnd + voyage.legHours;

  /* ------------------------------------------------------------- at sea -- */
  if (s < outboundEnd || (s >= stayToEnd && s < returnEnd)) {
    const outbound = s < outboundEnd;
    const legElapsed = outbound ? s : s - stayToEnd;
    const fraction = Math.min(1, Math.max(0, legElapsed / voyage.legHours));
    const travelledKm = fraction * route.path.km;
    const along = outbound ? travelledKm : route.path.km - travelledKm;
    const fix = fixAt(route.path, along);
    const course = outbound ? fix.course : (fix.course + 180) % 360;
    // Starboard of the centreline, so opposing traffic passes port-to-port.
    const offset = destination(fix.position, (course + 90) % 360, voyage.laneKm);
    const position = isWater(offset[0], offset[1]) ? offset : fix.position;

    const remainingKm = route.path.km - travelledKm;
    // Speed is not constant across a passage: a ship slows on approach and
    // works up after departure, which is what makes an ETA move.
    const approachFactor =
      remainingKm < APPROACH_KM
        ? 0.45 + 0.55 * (remainingKm / APPROACH_KM)
        : travelledKm < APPROACH_KM
          ? 0.5 + 0.5 * (travelledKm / APPROACH_KM)
          : 1;
    const sogKn = Number((vessel.serviceSpeedKn * approachFactor).toFixed(1));

    const status: NavStatus =
      remainingKm < APPROACH_KM ? "inbound" : travelledKm < APPROACH_KM ? "outbound" : "underway";

    const hoursOut = remainingKm / Math.max(1, vessel.serviceSpeedKn * KN_TO_KMH);
    const destinationId = outbound ? voyage.toId : voyage.fromId;
    const originId = outbound ? voyage.fromId : voyage.toId;

    return {
      ...vessel,
      originId,
      destinationId,
      at,
      lon: position[0],
      lat: position[1],
      cog: course,
      heading: course,
      sogKn,
      status,
      progress: fraction,
      travelledKm,
      remainingKm,
      etaMs: at + hoursOut * HOUR_MS,
      etaMinutes: hoursOut * 60,
      etaKind: "arrival",
      routeKey: outbound ? `${voyage.fromId}>${voyage.toId}` : `${voyage.toId}>${voyage.fromId}`,
    };
  }

  /* ------------------------------------------------------------ in port -- */
  const atFarPort = s >= outboundEnd && s < stayToEnd;
  const stayHours = atFarPort ? voyage.stayAtToHours : voyage.stayAtFromHours;
  const stayElapsed = atFarPort ? s - outboundEnd : s - returnEnd;
  const anchorHours = stayHours * voyage.anchorShare;
  const anchored = stayElapsed < anchorHours;

  const portId = atFarPort ? voyage.toId : voyage.fromId;
  const anchorPoint = atFarPort ? voyage.anchorAt : voyage.anchorFrom;
  const berth = atFarPort ? voyage.berthAt : voyage.berthFrom;
  const point = anchored ? anchorPoint : berth;

  // A ship at anchor swings on the tide; a ship alongside does not.
  const swing = anchored
    ? (Math.sin(((at - epoch) / HOUR_MS) * 0.5 + voyage.phase * 12) * 28 + voyage.phase * 360) % 360
    : (voyage.phase * 360 + (WAYPOINTS[portId] ? 0 : 0)) % 360;

  const status: NavStatus = anchored ? (voyage.waits ? "waiting" : "anchored") : "moored";
  const nextEventHours = anchored ? anchorHours - stayElapsed : stayHours - stayElapsed;

  return {
    ...vessel,
    originId: atFarPort ? voyage.fromId : voyage.toId,
    destinationId: portId,
    at,
    lon: point[0],
    lat: point[1],
    cog: swing,
    heading: swing,
    sogKn: anchored ? Number((0.1 + (voyage.phase % 0.2)).toFixed(1)) : 0,
    status,
    progress: 1,
    travelledKm: route.path.km,
    remainingKm: 0,
    etaMs: at + nextEventHours * HOUR_MS,
    etaMinutes: nextEventHours * 60,
    etaKind: anchored ? "berthing" : "departure",
    routeKey: null,
  };
}

/* ----------------------------------------------------------- fleet build -- */

export interface ReplayOptions {
  ports: PortSnapshot[];
  /** Instant the replay is anchored to; positions at this time are fixed. */
  epoch: number;
  /** Long-haul population. Harbour traffic is generated on top of this. */
  oceanFleet?: number;
  seed?: string;
  /** Vessels the signed-in operator owns, from the routing artefact. */
  owned?: OwnedVesselSeed[];
}

export interface OwnedVesselSeed {
  id: string;
  name: string;
  /** Waypoint the vessel is bound for. */
  destinationId: string;
  /** Waypoint it sailed from, if the artefact implies one. */
  originId?: string | null;
  /** Arrival the artefact declared, epoch ms. */
  etaMs: number | null;
  vesselClass?: VesselClass;
}

/**
 * The far ports a given Indian port trades with.
 *
 * Weighted so a leg is chosen for a reason: the Gulf and Suez runs from the
 * west coast, Malacca and the Bay from the east, and a coastal leg for every
 * port so the near field is never empty.
 */
function partnersFor(portId: string): string[] {
  const west = ["INMUN", "INIXY", "INNSA", "INBOM", "INMRM", "INNML", "INCOK"];
  const isWest = west.includes(portId);
  const coastal = isWest ? west : ["INMAA", "INENR", "INVTZ", "INPRT", "INCCU", "INTUT"];
  const foreign = isWest
    ? ["AEJEA", "AEFJR", "HORMUZ", "OMSLL", "SUEZ", "EGPSD", "BAB_EL_MANDEB", "PKKHI", "KEMBA", "MVMLE", "LKCMB"]
    : ["SGSIN", "MYPKG", "MALACCA", "BDCGP", "MMRGN", "LKCMB", "IDBLW", "AEJEA"];
  return [
    ...coastal.filter((id) => id !== portId),
    ...coastal.filter((id) => id !== portId),
    ...foreign,
    "LKCMB",
    "SGSIN",
  ];
}

function seatCounts(lore: PortLore): Record<Seat, number> {
  const calls = lore.calls;
  return {
    moored: Math.min(lore.berths, 4 + Math.round(calls * 0.55)),
    anchored: 3 + Math.round(lore.anchorageCount * 1.7 + lore.queuePressure * 9),
    approach: 4 + Math.round(calls * 0.4),
    inbound: 4 + Math.round(calls * 0.7),
    outbound: 3 + Math.round(calls * 0.45),
    service: 4,
    transit: 0,
  };
}

export function createReplaySource(options: ReplayOptions): TrafficSource {
  const seed = options.seed ?? "portwatch-traffic-v2";
  const lore = buildPortLore(options.ports);
  const voyages: Voyage[] = [];
  const byId = new Map<string, Voyage>();

  const add = (voyage: Voyage | null) => {
    if (!voyage || byId.has(voyage.vessel.id)) return;
    voyages.push(voyage);
    byId.set(voyage.vessel.id, voyage);
  };

  /* -------------------------------------------------- harbour population -- */
  for (const port of lore.values()) {
    const partners = partnersFor(port.id);
    const counts = seatCounts(port);
    const seats: Seat[] = ["moored", "anchored", "approach", "inbound", "outbound", "service"];
    for (const seat of seats) {
      for (let i = 0; i < counts[seat]; i += 1) {
        const id = `${seed}:${port.id}:${seat}:${i}`;
        const random = rng(hashSeed(id));
        const partner =
          seat === "service"
            ? partners[0]
            : partners[Math.floor(random() * partners.length) % partners.length];
        // The designed seat describes the far end of the leg, so the port under
        // inspection has to be the `to` waypoint.
        add(designVoyage(id, partner, port.id, seat, lore));
      }
    }
  }

  /* ------------------------------------------------------- ocean traffic -- */
  const oceanTarget = options.oceanFleet ?? 190;
  const portIds = [...lore.keys()];
  for (let i = 0; i < oceanTarget; i += 1) {
    const id = `${seed}:ocean:${i}`;
    const random = rng(hashSeed(id));
    const home = portIds[Math.floor(random() * portIds.length) % portIds.length];
    const partners = partnersFor(home);
    const partner = partners[Math.floor(random() * partners.length) % partners.length];
    add(designVoyage(id, home, partner, "transit", lore));
  }

  /* ---------------------------------------------------- operator vessels -- */
  for (const own of options.owned ?? []) {
    const destinationId = own.destinationId;
    const originId =
      own.originId ??
      (() => {
        const random = rng(hashSeed(`${seed}:own:${own.id}`));
        const partners = partnersFor(destinationId).filter(
          (id) => WAYPOINTS[id]?.kind === "gateway",
        );
        return partners[Math.floor(random() * partners.length) % partners.length];
      })();
    const voyage = designVoyage(`own:${own.id}`, originId, destinationId, "transit", lore, {
      owned: true,
      name: own.name,
      forcedClass: own.vesselClass ?? "container",
    });
    if (!voyage) continue;

    // Anchor the phase so the vessel arrives when the routing artefact says it
    // will: the map then agrees with the fleet board instead of contradicting it.
    if (own.etaMs != null) {
      const hoursToEta = (own.etaMs - options.epoch) / HOUR_MS;
      const arrivalPhase = voyage.legHours / voyage.cycleHours;
      const phase = arrivalPhase - hoursToEta / voyage.cycleHours;
      voyage.phase = ((phase % 1) + 1) % 1;
    }
    add(voyage);
  }

  const info: TrafficSourceInfo = {
    kind: "SIMULATED_TRAFFIC",
    label: "Simulated replay",
    provider: "India PortWatch traffic replay",
    detail:
      "No AIS provider is configured for this deployment. Positions, names and " +
      "identifiers are generated deterministically and moved along the water-only " +
      "route graph. They are not observations and no vessel here is a real ship.",
    epoch: options.epoch,
    observed: false,
  };

  const roster = voyages.map((voyage) => voyage.vessel);

  return {
    info,
    roster: () => roster,
    fixes: (at: number) => voyages.map((voyage) => resolve(voyage, at, options.epoch)),
    fix: (id: string, at: number) => {
      const voyage = byId.get(id);
      return voyage ? resolve(voyage, at, options.epoch) : null;
    },
    route: (id: string) => {
      const voyage = byId.get(id);
      if (!voyage) return null;
      return { coords: voyage.route.path.coords, km: voyage.route.path.km };
    },
  };
}

/* ------------------------------------------------------------- utilities -- */

/** The passage a fix is running, oriented the way the vessel is going. */
export function fixRoute(
  source: TrafficSource,
  fix: VesselFix,
): { coords: Position[]; km: number } | null {
  if (!fix.routeKey) return null;
  const [from, to] = fix.routeKey.split(">");
  const route = seaRoute(from, to);
  return route ? { coords: route.path.coords, km: route.path.km } : null;
}

/**
 * Where a vessel has been and where it is going, as two polylines.
 *
 * The past track is reconstructed from the same closed form that produced the
 * present fix, so it is the vessel's actual replayed history rather than a
 * remembered buffer that would be empty on first paint.
 */
export function trackAndAhead(
  fix: VesselFix,
): { track: Position[]; ahead: Position[] } | null {
  if (!fix.routeKey) return null;
  const [from, to] = fix.routeKey.split(">");
  const route = seaRoute(from, to);
  if (!route) return null;
  return {
    track: slicePath(route.path, Math.max(0, fix.travelledKm - 900), fix.travelledKm),
    ahead: slicePath(route.path, fix.travelledKm, route.path.km),
  };
}

/** The predicted position `minutes` ahead, holding course and speed. */
export function deadReckon(fix: VesselFix, minutes: number): Position {
  const km = (fix.sogKn * KN_TO_KMH * minutes) / 60;
  if (!fix.routeKey) return destination([fix.lon, fix.lat], fix.cog, km);
  const [from, to] = fix.routeKey.split(">");
  const route = seaRoute(from, to);
  if (!route) return destination([fix.lon, fix.lat], fix.cog, km);
  return fixAt(route.path, fix.travelledKm + km).position;
}

/** Straight-line separation between two fixes, in nautical miles. */
export function separationNm(a: VesselFix, b: VesselFix): number {
  return haversineKm([a.lon, a.lat], [b.lon, b.lat]) / 1.852;
}

export function waypointName(id: string | null | undefined): string {
  if (!id) return "—";
  return waypoint(id)?.name ?? id;
}

export function waypointShort(id: string | null | undefined): string {
  if (!id) return "—";
  const wp: Waypoint | null = waypoint(id);
  if (!wp) return id;
  return wp.name.replace(/\s*\(.*\)$/, "").split(" / ")[0];
}

/** Approximate the path a measured polyline would take, for external callers. */
export function pathOf(coords: Position[]) {
  return measurePath(coords);
}
