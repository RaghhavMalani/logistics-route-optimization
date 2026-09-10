/**
 * Lenses: six readings of one world.
 *
 * A lens is not a page and not a filter over a different dataset. The world
 * state is identical in all six; what changes is which parts of it are drawn at
 * full weight and which recede. Switching one must never navigate, never
 * refetch and never mutate anything -- if it did, "the same world seen
 * differently" would be a slogan rather than a description.
 *
 * Three of the six describe things this deployment cannot yet observe. Those
 * do not get invented layers. They state what is missing and what would make
 * them work, because a security lens that drew plausible-looking detections
 * would be the single most damaging thing in this product: an operator would
 * act on it, and there would be nothing underneath.
 */

import type { LayerKey } from "@/components/map/basemap";

export type Lens =
  | "OPERATIONS"
  | "INTELLIGENCE"
  | "WEATHER"
  | "SECURITY"
  | "CARGO"
  | "FINANCIAL";

export interface LensDefinition {
  lens: Lens;
  label: string;
  /** One line on what this lens is for. */
  purpose: string;
  /** Layers pushed to full weight. */
  emphasise: LayerKey[];
  /** Layers dimmed but never removed -- context, not noise. */
  recede: LayerKey[];
  /** Layers switched off entirely for this reading. */
  hide: LayerKey[];
  /**
   * Present when the lens describes something this deployment cannot observe.
   * Rendered instead of a fabricated layer.
   */
  unavailable?: {
    headline: string;
    detail: string;
    /** What would have to exist for this lens to work. */
    needs: string[];
  };
}

export const LENS_DEFINITIONS: Record<Lens, LensDefinition> = {
  OPERATIONS: {
    lens: "OPERATIONS",
    label: "Operations",
    purpose: "Hulls, quays and the queues between them.",
    emphasise: ["traffic", "routes", "ports", "tracks", "cascade"],
    // Geopolitics stays visible: an event with operational consequence is
    // exactly what this lens is about, and hiding it would hide the cause.
    recede: ["events", "chokepoints", "corridors", "weather", "storms"],
    hide: ["zones", "vectors"],
  },

  INTELLIGENCE: {
    lens: "INTELLIGENCE",
    label: "Intelligence",
    purpose: "Events, the water they threaten, and how consequence travels.",
    emphasise: ["events", "chokepoints", "cascade", "corridors"],
    recede: ["traffic", "ports", "routes", "weather"],
    hide: ["zones", "vectors", "tracks", "ghosts"],
  },

  WEATHER: {
    lens: "WEATHER",
    label: "Weather",
    purpose: "The environment a passage actually crosses.",
    emphasise: ["weather", "storms", "vectors", "routes"],
    recede: ["traffic", "ports", "cascade"],
    hide: ["events", "zones", "ghosts"],
  },

  SECURITY: {
    lens: "SECURITY",
    label: "Security",
    purpose: "Identity, behaviour and proximity anomalies.",
    emphasise: ["traffic", "chokepoints", "tracks"],
    recede: ["routes", "ports", "weather", "cascade"],
    hide: ["zones", "vectors", "events"],
    unavailable: {
      headline: "No observed AIS in this deployment",
      detail:
        "Every signal this lens reads -- transmission gaps, impossible jumps, " +
        "loitering, identity changes, ship-to-ship proximity -- is a property " +
        "of observed AIS. The traffic on this chart is a deterministic replay, " +
        "so a detection drawn here would be a detection of the simulator.",
      needs: [
        "an observed AIS provider (AISStream for research, Spire or Kpler commercially)",
        "vessel identity across registries, which Global Fishing Watch provides non-commercially",
        "position history long enough to establish normal behaviour",
      ],
    },
  },

  CARGO: {
    lens: "CARGO",
    label: "Cargo",
    purpose: "Consignments moving between hulls, yards and quays.",
    emphasise: ["ports", "routes", "zones", "cascade"],
    recede: ["traffic", "weather", "chokepoints"],
    hide: ["events", "vectors", "ghosts"],
    unavailable: {
      headline: "Cargo is demo data behind real feasibility rules",
      detail:
        "The transshipment optimiser is real and its constraints are enforced, " +
        "but the manifests it runs on are generated. Drawing cargo lineage " +
        "across the world would present invented consignments as observed ones.",
      needs: [
        "a terminal operating system or customer manifest feed",
        "container lineage across the vessels and yards a consignment passes",
        "customs state, which no public source carries",
      ],
    },
  },

  FINANCIAL: {
    lens: "FINANCIAL",
    label: "Financial",
    purpose: "What the operational consequence is worth.",
    emphasise: ["ports", "cascade", "routes"],
    recede: ["traffic", "weather", "chokepoints", "events"],
    hide: ["zones", "vectors", "ghosts"],
    unavailable: {
      headline: "No cost basis is configured",
      detail:
        "Every financial figure in this product refuses rather than estimates. " +
        "There is no default rupee value anywhere, because the invented number " +
        "is the one a CFO would quote back.",
      needs: [
        "a cost model with a stated source: CUSTOMER_CONTRACT, PORT_TARIFF or PUBLIC_TARIFF",
        "or an explicit scenario assumption, which is labelled ASSUMPTION and never mixed with observed rates",
      ],
    },
  },
};

export const LENS_ORDER: Lens[] = [
  "OPERATIONS",
  "INTELLIGENCE",
  "WEATHER",
  "SECURITY",
  "CARGO",
  "FINANCIAL",
];

/**
 * The layer toggles for a lens, applied over whatever the workspace already has.
 *
 * Pure: it reads the current toggles and returns new ones. A lens that mutated
 * anything would be a mode rather than a reading, and the test that this
 * function does not touch its input is what keeps that true.
 */
export function lensLayers(
  lens: Lens,
  base: Partial<Record<LayerKey, boolean>>,
): Partial<Record<LayerKey, boolean>> {
  const definition = LENS_DEFINITIONS[lens];
  const next: Partial<Record<LayerKey, boolean>> = { ...base };
  for (const key of definition.emphasise) next[key] = true;
  for (const key of definition.recede) next[key] = base[key] ?? true;
  for (const key of definition.hide) next[key] = false;
  return next;
}

/**
 * How strongly a lens draws its receding layers.
 *
 * Receding is not hiding. A vessel on the intelligence lens still has to be
 * findable -- an operator who cannot see the traffic cannot tell what the event
 * is about -- so context drops to a readable weight rather than disappearing.
 */
export function lensOpacity(lens: Lens, key: LayerKey): number {
  const definition = LENS_DEFINITIONS[lens];
  if (definition.emphasise.includes(key)) return 1;
  if (definition.recede.includes(key)) return 0.45;
  return 0;
}
