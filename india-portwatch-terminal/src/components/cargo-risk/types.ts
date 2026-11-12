export type Rule = "R1" | "R2" | "R3" | "R4" | "R5";
export type Sourced<T> = { value: T; basis: string; source: string };
export type Interval = {
  estimate: number;
  lower95: number;
  upper95: number;
  standardError: number;
};
export type CargoDeclaration = {
  id: string;
  name: string;
  handlingClass: Sourced<"dry" | "reefer" | "DG"> | null;
  deadline: string | null;
  deliveryClock: string | null;
  source: string;
};
export type CargoLoss = {
  id: string;
  priority: number | null;
  onTime: Interval | null;
  spoilage: Interval | null;
  deadlineBasis: string | null;
  insuredValue: Sourced<{ amount: string; currency: string }> | null;
  unknown: Record<string, string>;
  expectedExtraCost: Interval | null;
  drivers: Record<string, { expected: number; basis: string[] }>;
};
export type RiskOption = {
  id: string;
  label: string;
  arrival: { hours: [number, number, number]; mean: Interval };
  cost: {
    scope: string;
    knownSubtotal: { expected: number; cvar95: number } | null;
    dots: number[];
    unknown: Record<string, string>;
    uncertainty: { mean: Interval; cvar95: Interval } | null;
  };
  consignments: CargoLoss[];
};
export type RiskReport = {
  status: "SHADOW";
  seed: number;
  asOf: string;
  inputHash: string;
  currency: string;
  scope: string;
  keepOptionId: string;
  diagnostics: {
    n: number;
    threshold: number;
    stop: string;
    difference: Interval | null;
  };
  decision: { rule: Rule; optionId: string | null; reason: string };
  options: RiskOption[];
  cargo: CargoDeclaration[];
  excludedOptions: { label: string; reason: string }[];
  closureSensitivity: {
    grid: { closureHours: number; optionId: string | null }[];
    flips: {
      lowerHours: number;
      upperHours: number;
      fromOptionId: string;
      toOptionId: string;
    }[];
    basis: string;
  };
  sourceBasis: {
    closure: string;
    handling: string;
    fuel: string | null;
    fx: string | null;
    options: Record<string, { passage: string; weather: string; port: string }>;
  };
};
export type RiskResponse =
  RiskReport | { status: "UNAVAILABLE"; reason: string };
export type CargoTone = "ok" | "warn" | "crit" | "unknown";
