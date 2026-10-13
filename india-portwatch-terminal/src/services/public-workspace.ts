import { useQuery } from "@tanstack/react-query";
import { getJson } from "./api";
import type { PublicExplore } from "./public-research";

export type TimeMode = "current" | "replay" | "projection";
export type SceneLayer =
  | "events"
  | "routes"
  | "vessels"
  | "weather"
  | "economics"
  | "infrastructure"
  | "cameras";
export interface Workspace extends Omit<PublicExplore, "ports" | "events"> {
  timeMode: TimeMode;
  collectedAt: string;
  timeMeaning: string;
  vesselMeaning: string;
  ports: (PublicExplore["ports"][number] & {
    location: { lat: number; lon: number };
    capacityMeaning: string;
  })[];
  events: (PublicExplore["events"][number] & {
    coordinates: { lat: number; lon: number } | null;
    chokepoints: string[];
    availableAt: string;
  })[];
  routes: {
    id: string;
    name: string;
    portCodes: string[];
    chokepoints: string[];
    positions: number[][];
    meaning: string;
  }[];
  chokepoints: { id: string; name: string; lat: number; lon: number }[];
  weather: {
    portCode: string;
    observedAt: string;
    windKnots: number | null;
    gustKnots: number | null;
    rainfallMm24h: number | null;
    waveHeightM: number | null;
    visibilityKm: number | null;
    dataSource: string;
    timestampMeaning: string;
    status: string;
    availableAt: string;
  }[];
  economics: {
    id: string;
    label: string;
    value: number | null;
    unit: string;
    source: string;
    observedAt: string | null;
    status: string;
    shippingConnection: string;
  }[];
  cameras: {
    id: string;
    name: string;
    portCode: string;
    lat: number;
    lon: number;
    coverage: string;
    mediaUrl: string;
    feedType: string;
    source: string;
    health: string;
    lastFrameAt: string | null;
    healthNote: string;
  }[];
  layers: { id: SceneLayer; label: string; status: string; coverage: string }[];
}
export interface ScenarioInputs {
  riskChokepoint: string;
  laneCode: string;
  portCode: string;
  hoursToRisk: number;
  speedKn: number;
  closureHours: number;
  severity: number;
  waveM: number;
  charterUsdDay: number;
  bunkerUsdTonne: number;
  fuelTonnesDay: number;
}
export interface Measure {
  value: number | null;
  unit: string;
  available: boolean;
  basis: string;
  unknownBecause: string | null;
  confidence: number | null;
}
export interface ScenarioOption {
  optionId: string;
  label: string;
  feasible: boolean;
  isBaseline: boolean;
  status: string;
  geometry: number[][];
  params: { speedKn?: number; portCode?: string };
  constraints: { label: string; passed: boolean; detail: string }[];
  rejectedBy: { label: string; detail: string }[];
  evaluation: {
    objectives: Record<string, Measure>;
    notes: string[];
    financial: {
      total: { amount: number; currency: string } | null;
      partialTotal: { amount: number; currency: string } | null;
      complete: boolean;
      components: {
        key: string;
        label: string;
        state: string;
        money: { amount: number; currency: string } | null;
        reason: string;
        isAssumption: boolean;
      }[];
      unknown: { reason: string }[];
    };
  } | null;
  critic: { verdict: string; reasons: string[] } | null;
}
export interface Scenario {
  at: string;
  meaning: string;
  forecastConnection: string;
  uncertainty: string;
  position: { lat: number; lon: number; basis: string; observed: false };
  options: ScenarioOption[];
  doNothingStatement: string;
  recommendation: {
    optionId: string;
    provisionalOptionId: string | null;
    kind: string;
    statement: string;
    why: string;
    rankingBasis: {
      objectivesUsed: string[];
      objectivesDropped: Record<string, string>;
      method: string;
    };
    robustness: { durationConfidence: { label: string } } | null;
  } | null;
  availableActions: {
    kind: string;
    label: string;
    availability: { status: string; reason: string };
  }[];
  observedOutcome: null;
}
export interface Feedback {
  forecasts: {
    id: string;
    variable: string;
    issuedAt: string;
    targetDate: string;
    horizonDays: number;
    original: number;
    corrected: number;
    unit: string;
    observed: number | null;
    observationSource: string | null;
    status: string;
    correction: { status?: string; reason?: string };
  }[];
  note: string;
}
export const DEFAULT_SCENARIO: ScenarioInputs = {
  riskChokepoint: "SUEZ",
  laneCode: "EUR_IND",
  portCode: "INNSA",
  hoursToRisk: 24,
  speedKn: 16,
  closureHours: 72,
  severity: 1,
  waveM: 2,
  charterUsdDay: 30000,
  bunkerUsdTonne: 650,
  fuelTonnesDay: 45,
};
const params = (input: Record<string, string | number>) =>
  new URLSearchParams(
    Object.entries(input).map(([k, v]) => [k, String(v)]),
  ).toString();
export function usePublicWorkspace(mode: TimeMode, at: string) {
  return useQuery({
    queryKey: ["public-workspace", mode, at],
    queryFn: ({ signal }) =>
      getJson<Workspace>(
        `/public/workspace?${params({ mode, ...(mode === "current" ? {} : { at }) })}`,
        {},
        { signal },
      ),
    staleTime: 60_000,
    enabled: Boolean(at),
    retry: 1,
  });
}
export function usePublicScenario(input: ScenarioInputs | null, at: string) {
  return useQuery({
    queryKey: ["public-scenario", input, at],
    queryFn: ({ signal }) =>
      getJson<Scenario>(
        `/public/scenario?${params({ ...input!, at })}`,
        {},
        { signal },
      ),
    enabled: input !== null && Boolean(at),
    staleTime: 60_000,
    retry: false,
  });
}
export function usePublicFeedback(
  portCode: string,
  variable: string,
  at: string,
) {
  return useQuery({
    queryKey: ["public-weather-feedback", portCode, variable, at],
    enabled: Boolean(at),
    queryFn: ({ signal }) =>
      getJson<Feedback>(
        `/public/weather-feedback?${params({ portCode, variable, at })}`,
        {},
        { signal },
      ),
    staleTime: 60_000,
    retry: 1,
  });
}
