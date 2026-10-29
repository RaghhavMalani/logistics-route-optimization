import { useQuery } from "@tanstack/react-query";
import { getJson } from "./api";
import type { WeatherSignal } from "@/types/portwatch";
import type { FinancialEvaluation } from "@/types/decisions";

export interface PassageConsumption {
  referenceSpeedKn: number;
  referencePropulsionTonnesPerDay: number;
  auxiliaryTonnesPerDay?: number;
  anchorageTonnesPerDay?: number;
  departureHoldTonnesPerDay?: number;
  minSpeedKn: number;
  maxSpeedKn: number;
  loadCondition: string;
  source: string;
  declaredAt: string;
}
export interface PassageRate {
  amount: number;
  currency: string;
  per: "tonne" | "hour" | "day";
  source: string;
  validFrom: string;
  validTo: string;
  applicability?: "WHOLE_MODELED_ELAPSED";
}
export interface DeclaredPassagePlan {
  schemaVersion: 1;
  referenceKind: "AT_SEA" | "NOT_DEPARTED";
  referenceAt: string;
  referenceLabel: string;
  declaredAt: string;
  remainingDistanceNm: number;
  distanceBasis: string;
  baselineSpeedKn: number;
  minSpeedKn: number;
  maxSpeedKn: number;
  alternativeSpeedKn?: number;
  baselineArrivalAt?: string;
  deadlineAt?: string;
  departureDelayHours?: number;
  departureHoldPermitted?: boolean;
  departureHoldLocation?: string;
  geometry?: Array<[number, number]>;
  finance?: {
    consumption?: PassageConsumption;
    fuelPrice?: PassageRate;
    elapsedTimeRate?: PassageRate;
    currency?: string;
  };
}
export interface CargoConnectionDeclaration {
  vesselId: string;
  name: string;
  departureAt?: string;
  loadingCutoffAt?: string;
  onwardPorts?: string[];
  availableTeu?: number;
  availableDeadweightT?: number;
  availableReeferPlugs?: number;
  acceptsHazardous?: boolean;
  acceptsOog?: boolean;
  basis?: string;
}
export interface CargoCommitmentDeclaration {
  schemaVersion: 1;
  fictionalShipment: true;
  voyageId: string;
  portCode: string;
  declaredAt: string;
  basis: string;
  mustMeet: boolean;
  shipment: {
    shipmentId: string;
    teu?: number;
    cargoClass: "dry" | "reefer" | "hazardous" | "oog" | "empty";
    destinationPort: string;
    weightT?: number;
    latestDepartureAt?: string;
  };
  transfer: {
    approachToStartHours?: number;
    basis?: string;
    acceptedSchematicHandling: boolean;
    gangs?: number;
    mode: "DIRECT" | "YARD";
    zone?: {
      zoneId: string;
      name: string;
      freeTeu?: number;
      capacityTeu?: number;
      reeferPlugsFree?: number;
      acceptsHazardous?: boolean;
      acceptsOog?: boolean;
      quayTransferMinutesPerTeu?: number;
    };
  };
  bookedConnection: CargoConnectionDeclaration;
  laterConnections: CargoConnectionDeclaration[];
}
export interface CargoOptionAssessment {
  optionId: string;
  status: "COMPATIBLE_UNDER_ASSUMPTIONS" | "BLOCKED" | "UNKNOWN";
  timingStatus: "FITS" | "MISSES" | "UNKNOWN";
  startAt?: string | null;
  readinessAt?: string | null;
  cutoffAt?: string | null;
  departureAt?: string | null;
  slackHours?: number | null;
  handlingHours?: number | null;
  stages?: {
    dischargeHours: number;
    transferOverheadHours: number;
    yardMovesHours: number;
    loadHours: number;
    totalHandlingHours: number;
  } | null;
  reasons: string[];
  missing: string[];
  requiredConstraint: { required: boolean; passed: boolean | null };
  alternativesUnavailableBecause?: string;
  alternatives: Array<{
    optionId: string;
    action: string;
    label: string;
    status: string;
    vesselId: string;
    departureAt: string;
    readinessAt: string;
    cutoffAt: string;
    slackHours: number;
    departureShiftHours: number;
    bookingStatus: string;
    execution: string;
    limitation: string;
    [key: string]: unknown;
  }>;
  [key: string]: unknown;
}
export interface FrozenCargoComparison {
  version: string;
  inputVersion: string;
  referenceAt: string;
  options: CargoOptionAssessment[];
  [key: string]: unknown;
}
export interface PassageOptionComparison {
  optionId: string;
  label: string;
  status: string;
  reason?: string;
  speedKn?: number | null;
  departureAt?: string | null;
  arrivalAt?: string | null;
  approachClearAt?: string | null;
  sailingHours?: number | null;
  commonElapsedSailingHours?: number | null;
  futureSailingHours?: number | null;
  speedChangeAt?: string | null;
  departureHoldHours?: number | null;
  anchorageWaitHours?: number | null;
  requestedWindowWaitHours?: number | null;
  forecastGateWaitHours?: number | null;
  totalElapsedHours?: number | null;
  scheduleShiftHours?: number | null;
  deadlineAt?: string | null;
  deadlineMet?: boolean | null;
  fuel?: {
    version: string;
    available: boolean;
    totalTonnes: number | null;
    unit: "tonne";
    modes: Record<
      string,
      {
        available: boolean;
        tonnes: number | null;
        hours: number | null;
        basis?: string;
        unknownBecause?: string;
        propulsionTonnes?: number | null;
        auxiliaryTonnes?: number | null;
        segments?: Array<{
          index: number;
          hours: number | null;
          speedKn: number | null;
          available: boolean;
          tonnes: number | null;
          basis?: string;
          unknownBecause?: string;
        }>;
      }
    >;
    formula: string;
    consumption: {
      source?: string;
      loadCondition?: string;
      declaredAt?: string;
    };
    missingInputs: string[];
    meaning: string;
    assumptions: string[];
  };
  finance?: FinancialEvaluation | null;
  delta?: {
    basis: "OPTION_MINUS_BASELINE";
    completeCostComparison: false;
    fuelTonnes: {
      available: boolean;
      value?: number;
      unit?: string;
      unknownBecause?: string;
    };
    components: Array<{
      key: string;
      label: string;
      available: boolean;
      money?: { amount: number; currency: string };
      basis?: string;
      unknownBecause?: string;
    }>;
    meaning: string;
  };
  consumedForecasts?: CurrentHour[];
}
export interface FrozenPassageComparison {
  version: "declared-passage-v1";
  inputVersion?: string;
  calculationAt?: string;
  commonElapsedSailingHours?: number;
  commonElapsedDistanceNm?: number;
  remainingDistanceAtCalculationNm?: number;
  projectionBasis?: string;
  referenceAt: string;
  requestedApproachAt: string;
  distanceNm: number;
  distanceBasis: string;
  baselineArrivalAt: string;
  geometryBasis: string;
  options: PassageOptionComparison[];
  limitations: string[];
}

export interface CurrentHour {
  validAt: string;
  wind_speed_10m: number | null;
  wind_gusts_10m: number | null;
  wind_direction_10m?: number | null;
  precipitation: number | null;
  visibility: number | null;
  wave_height: number | null;
}
export interface FrozenEnvironment {
  evidenceVersion?: string;
  evidenceId: string;
  snapshotId: string;
  responseSha256: string;
  portCode: string;
  voyageId: string;
  issuedAt: string | null;
  observedAt: string | null;
  availableAt: string;
  earliestVoyageArrival: string;
  plannedArrival: string;
  firstClearApproach: string;
  forecastGateWaitHours: number;
  noWeatherGateWaitHours: number;
  consumedForecasts: CurrentHour[];
  assumptions: { maxGustKn: number; minVisibilityM: number; scope: string };
  // Both forms are frozen evidence. Never fill either from live provenance.
  activityObservation?: string;
  activityContext?: FrozenActivityContext;
  passagePlan?: DeclaredPassagePlan;
  passageComparison?: FrozenPassageComparison;
  cargoCommitment?: CargoCommitmentDeclaration;
  cargoComparison?: FrozenCargoComparison;
  meaning: string;
}
export interface FrozenActivityContext {
  schemaVersion: 1;
  projectionVersion: string;
  operationalUse: "CONTEXT_ONLY";
  calculationEffect: "NONE";
  portCode: string;
  provider: string | null;
  sourceProductId: string | null;
  sourceVersion: string | null;
  observationDate: string | null;
  observedFrom: string | null;
  observedThrough: string | null;
  datePrecision: string | null;
  sourceReceiptId: string | null;
  originalRef: string | null;
  originalHash: string | null;
  firstAvailableAt: string | null;
  unknownReason: string | null;
}
export interface CurrentEnvironment {
  portCode: string;
  status?: string;
  sources: Record<
    string,
    {
      status: string;
      availableAt: string | null;
      issuedAt: string | null;
      source: string;
    }
  >;
  hourly: CurrentHour[];
  daily: {
    date: string;
    wind_speed: number | null;
    wind_gust: number | null;
    rainfall: number | null;
    wave_height: number | null;
    observed: null;
    matchStatus: string;
  }[];
  regionalHazards: {
    id: string;
    title: string;
    source: string;
    publishedAt: string;
    validThrough: string;
    relationship: string;
  }[];
}

export function useCurrentMapWeather() {
  return useQuery({
    queryKey: ["current-map-weather"],
    queryFn: ({ signal }) =>
      getJson<WeatherSignal[]>("/weather/current-map", {}, { signal }),
    staleTime: 60000,
    refetchInterval: 60000,
  });
}
