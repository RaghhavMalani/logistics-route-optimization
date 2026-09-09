/**
 * Scenario key resolution for the command bar and deep links.
 *
 * The canonical keys and their aliases live in the backend catalogue
 * (src/decision/scenario_catalog.py); this mirror only exists so a typed
 * command resolves before the round trip. Anything unknown falls through to the
 * backend, which resolves it against the same table.
 */

export const SCENARIO_ALIASES: Record<string, string> = {
  HORMUZ: "HORMUZ",
  HORMUZ_CLOSURE: "HORMUZ",
  SUEZ: "SUEZ",
  SUEZ_BLOCKAGE: "SUEZ",
  REDSEA: "REDSEA",
  RED_SEA: "REDSEA",
  MALACCA: "MALACCA",
  MALACCA_DISRUPTION: "MALACCA",
  CYC_E: "CYC_E",
  CYCLONE_EAST: "CYC_E",
  STORM_W: "STORM_W",
  STORM_WEST: "STORM_W",
  CAPDROP: "CAPDROP",
  CAPACITY_DROP: "CAPDROP",
  LABOUR: "LABOUR",
  LABOUR_STRIKE: "LABOUR",
  LABOR_STRIKE: "LABOUR",
  DEMAND: "DEMAND",
  DEMAND_SURGE: "DEMAND",
  FUEL: "FUEL",
  FUEL_PRICE: "FUEL",
};

export function resolveScenarioKey(input: string): string {
  const normalised = String(input ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");
  return SCENARIO_ALIASES[normalised] ?? normalised ?? "HORMUZ";
}
