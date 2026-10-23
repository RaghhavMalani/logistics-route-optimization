import { useQuery } from "@tanstack/react-query";
import { getJson } from "./api";
import type { WeatherSignal } from "@/types/portwatch";

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
