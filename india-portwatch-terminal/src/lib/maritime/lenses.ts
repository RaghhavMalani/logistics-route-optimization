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
    hide: ["zones", "vectors", "seastate"],
  },

  INTELLIGENCE: {
    lens: "INTELLIGENCE",
    label: "Intelligence",
    purpose: "Events, the water they threaten, and how consequence travels.",
    emphasise: ["events", "chokepoints", "cascade", "corridors"],
    recede: ["traffic", "ports", "routes", "weather"],
    hide: ["zones", "vectors", "tracks", "ghosts", "seastate"],
  },

  WEATHER: {
    lens: "WEATHER",
    label: "Weather",
    purpose: "The environment a passage actually crosses.",
    emphasise: ["weather", "storms", "vectors", "routes", "seastate"],
    recede: ["traffic", "ports", "cascade"],
    hide: ["events", "zones", "ghosts"],
  },

  SECURITY: {
    lens: "SECURITY",
    label: "Security",
    purpose: "Identity, behaviour and proximity anomalies.",
    emphasise: ["traffic", "chokepoints", "tracks"],
    recede: ["routes", "ports", "weather", "cascade"],
    hide: ["zones", "vectors", "events", "seastate"],
    // The lens asks the backend's security rules; under the replay the answer
    // is SECURITY ANALYTICS UNAVAILABLE and this is why. The marker on the bar
    // says so before the click.
    unavailable: {
      headline: "No observed AIS in this deployment",
      detail:
        "Every rule this lens runs -- prolonged AIS gap, improbable jump, " +
        "loitering, route deviation, destination inconsistency, abnormal speed " +
        "state, repeated identity conflict -- is a property of observed AIS. The " +
        "traffic on this chart is a deterministic replay, so a detection drawn " +
        "here would be a detection of the simulator.",
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
    // Structural exposure is real and sourced: which Indian cargo classes the
    // selected event reaches, through which straits, lanes and ports. What
    // stays unavailable is cargo *lineage* -- the manifests are generated --
    // and the exposure panel says so in its own disclaimer rather than
    // drawing consignments across the world.
    purpose: "Which Indian cargo classes the event structurally reaches.",
    emphasise: ["ports", "routes", "cascade", "chokepoints"],
    recede: ["traffic", "weather", "events"],
    hide: ["zones", "vectors", "ghosts", "seastate"],
  },

  FINANCIAL: {
    lens: "FINANCIAL",
    label: "Financial",
    purpose: "What the operational consequence is worth.",
    emphasise: ["ports", "cascade", "routes"],
    recede: ["traffic", "weather", "chokepoints", "events"],
    hide: ["zones", "vectors", "ghosts", "seastate"],
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
