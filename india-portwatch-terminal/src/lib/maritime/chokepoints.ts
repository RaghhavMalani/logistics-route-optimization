/**
 * The chokepoints the event feed scores exposure against.
 *
 * Kept next to the routing graph rather than inside a map layer because both
 * the chart and the event intelligence screens key off the same codes, and the
 * codes come from the pipeline.
 */

export interface Chokepoint {
  code: string;
  name: string;
  lat: number;
  lon: number;
  coast: "west" | "east";
  /** Routing-graph waypoint this chokepoint corresponds to, where one exists. */
  waypointId: string | null;
}

export const CHOKEPOINTS: Chokepoint[] = [
  { code: "HORMUZ", name: "Strait of Hormuz", lat: 26.6, lon: 56.3, coast: "west", waypointId: "HORMUZ" },
  { code: "BAB_EL_MANDEB", name: "Bab-el-Mandeb", lat: 12.6, lon: 43.3, coast: "west", waypointId: "BAB_EL_MANDEB" },
  { code: "SUEZ", name: "Suez Canal", lat: 30.0, lon: 32.55, coast: "west", waypointId: "SUEZ" },
  { code: "MALACCA", name: "Strait of Malacca", lat: 2.5, lon: 101.0, coast: "east", waypointId: "MALACCA" },
  { code: "PANAMA", name: "Panama Canal", lat: 9.08, lon: -79.68, coast: "west", waypointId: null },
];

export const CHOKEPOINT_BY_CODE = new Map<string, Chokepoint>(
  CHOKEPOINTS.map((choke) => [choke.code, choke]),
);
