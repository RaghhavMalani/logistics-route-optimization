/**
 * HTTP calls and hooks for the two lenses the backend now computes, the
 * mission comparison, the freshness coordinator and the world clock.
 *
 * Every surface here refuses rather than invents: the security lens answers
 * UNAVAILABLE under the replay, trade exposure carries no volume, and the
 * freshness payload reports an artefact's own instant rather than a
 * rewritten one. The hooks pass that through untouched.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";

import { getJson, postJson } from "./api";

/* ------------------------------------------------------------ security -- */

export interface SecurityDetection {
  rule: string;
  mmsi: string;
  confidence: number;
  evidence: Record<string, unknown>;
  threshold: Record<string, unknown>;
  observationTimestamps: string[];
  statement: string;
  basis: string;
}

export interface SecurityLens {
  status: "SECURITY ANALYTICS AVAILABLE" | "SECURITY ANALYTICS UNAVAILABLE";
  mode: string;
  stale?: boolean;
  reason: string | null;
  rules: string[];
  thresholds: Record<string, Record<string, unknown>>;
  detections: SecurityDetection[];
  tracksAnalysed: number;
  at?: string;
  basis?: string;
}

export const fetchSecurityLens = (mode: string): Promise<SecurityLens> =>
  getJson<SecurityLens>(`/security/lens?mode=${encodeURIComponent(mode)}`);

export const useSecurityLens = (mode = "DEMO"): UseQueryResult<SecurityLens> =>
  useQuery({
    queryKey: ["security", "lens", mode],
    queryFn: () => fetchSecurityLens(mode),
    staleTime: 20_000,
    refetchInterval: 30_000,
  });

/* --------------------------------------------------------------- trade -- */

export interface TradeExposureClass {
  commodityClass: string;
  label: string;
  exposed: boolean;
  chains: number;
  events: string[];
  chokepoints: string[];
  lanes: string[];
  ports: string[];
  statement: string;
}

export interface TradeExposureChain {
  eventId: string;
  chokepoint: string | null;
  chokepointName: string | null;
  laneCode: string | null;
  laneName: string | null;
  portCode: string;
  commodityClass: string;
  label: string;
  path: string[];
  sources: Array<Record<string, unknown>>;
}

export interface TradeExposure {
  kind: "STRUCTURAL EXPOSURE";
  eventId: string | null;
  portCode: string | null;
  events: string[];
  classes: TradeExposureClass[];
  chains: TradeExposureChain[];
  catalogue: { ports: string[]; classes: string[] };
  disclaimer: string;
}

export const fetchTradeExposure = (
  eventId?: string | null,
  portCode?: string | null,
): Promise<TradeExposure> => {
  const params = new URLSearchParams();
  if (eventId) params.set("eventId", eventId);
  if (portCode) params.set("portCode", portCode);
  const query = params.toString();
  return getJson<TradeExposure>(`/trade/exposure${query ? `?${query}` : ""}`);
};

export const useTradeExposure = (
  eventId?: string | null,
  portCode?: string | null,
): UseQueryResult<TradeExposure> =>
  useQuery({
    queryKey: ["trade", "exposure", eventId ?? null, portCode ?? null],
    queryFn: () => fetchTradeExposure(eventId, portCode),
    staleTime: 120_000,
  });

/* ------------------------------------------------------------ missions -- */

export interface MissionComparisonHull {
  vesselId: string;
  name: string;
  destinationPort?: string;
  recommended?: string | null;
  recommendedRealisedHours?: number | null;
  critic?: string | null;
  realisedBest?: string | null;
  realisedBestHours?: number | null;
  regretHours?: number | null;
  rankingCorrect?: boolean | null;
  closedOnArrival?: boolean | null;
  baselineRisk?: number | null;
  brier?: number | null;
  persistenceErrorHours?: number | null;
  blockedHours?: number | null;
  subject?: string | null;
  learned?: string[];
  refused?: string;
}

export interface MissionComparisonCard {
  missionId: string;
  name: string;
  subjectKind: "chokepoint" | "port";
  subject: string;
  eventCategory: string;
  startTimestamp: string;
  forecastHorizonHours: number;
  outcome: {
    blockedHours: number;
    closures: Record<string, Record<string, string>>;
    shipsWaitingPeak: number | null;
  };
  predictionErrorHours: number | null;
  hulls: MissionComparisonHull[];
  regret: {
    totalHours: number | null;
    meanHours: number | null;
    hullsWithZeroRegret: number;
    hullsScored: number;
  };
  rankingCorrectShare: number | null;
  calibration: {
    meanBrier: number | null;
    meanBaselineRisk: number | null;
    closedOnArrivalShare: number | null;
  };
  dataCompleteness: {
    observations: number;
    withStatedTime: number;
    statedTimeShare: number;
    sources: number;
    visibleAtStart: number;
    hiddenAtStart: number;
    queueFigureStated: boolean;
  };
  refused: Record<string, string>;
  disclaimer: string;
}

export interface MissionComparison {
  missions: MissionComparisonCard[];
  table: Array<{
    key: string;
    label: string;
    values: Record<string, number | boolean | null>;
  }>;
  note: string;
}

export const fetchMissionComparison = (): Promise<MissionComparison> =>
  getJson<MissionComparison>("/missions/compare");

export const useMissionComparison = (): UseQueryResult<MissionComparison> =>
  useQuery({
    queryKey: ["missions", "compare"],
    queryFn: fetchMissionComparison,
    staleTime: 300_000,
    gcTime: 1_800_000,
  });

/* ----------------------------------------------------------- freshness -- */

export interface FreshnessArtifact {
  artifact: string;
  label: string;
  provider: string;
  state:
    | "MISSING"
    | "FRESH"
    | "DUE"
    | "EXPIRED"
    | "STALE"
    | "NOT_APPLICABLE"
    | "SIMULATED";
  ageSeconds: number | null;
  observedAt: string | null;
  sourceTimestamp: string | null;
  sourceLagSeconds: number | null;
  expiresAt: string | null;
  reason: string;
  detail: Record<string, unknown>;
  policy: {
    freshForSeconds: number;
    leadSeconds: number;
    staleAfterSeconds: number;
    rationale: string;
    feeds: string[];
  };
  job: {
    refreshable: boolean;
    state: "IDLE" | "RUNNING" | "RETRY_SCHEDULED" | "FAILED" | "DISABLED";
    eligibility: string | null;
    attemptsThisCycle: number;
    nextAttemptAt: string | null;
    lastResult: {
      ok: boolean;
      skipped: boolean;
      changed: boolean;
      startedAt: string;
      finishedAt: string;
      durationSeconds: number;
      attempt: number;
      reason: string;
      error: string | null;
      detail: Record<string, unknown>;
    } | null;
    lastGood: { finishedAt: string } | null;
    invalidatedBy: string[];
  };
}

export interface Freshness {
  at: string;
  scheduler: { running: boolean; tickSeconds: number; ticks: number };
  artifacts: FreshnessArtifact[];
  summary: Record<string, number>;
}

export const fetchFreshness = (
  headers: Record<string, string>,
): Promise<Freshness> => getJson<Freshness>("/admin/freshness", headers);

export const useFreshness = (
  headers: Record<string, string>,
): UseQueryResult<Freshness> =>
  useQuery({
    queryKey: ["admin", "freshness"],
    queryFn: () => fetchFreshness(headers),
    staleTime: 10_000,
    refetchInterval: 15_000,
  });

export function useRefreshArtifact(headers: Record<string, string>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (artifact: string) =>
      postJson<{ outcome: string }>(
        `/admin/freshness/${encodeURIComponent(artifact)}/refresh`,
        {},
        headers,
      ),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ["admin", "freshness"] }),
  });
}

/* --------------------------------------------------------- world clock -- */

export interface WorldClockState {
  mode: "LIVE" | "REPLAY" | "HISTORICAL_MISSION" | "SCENARIO";
  now: string;
  wallNow: string;
  anchor: string | null;
  rate: number | null;
  frozen: boolean;
  setBy: string;
  reason: string;
  subject: Record<string, unknown>;
  offsetFromWallSeconds: number;
}

export const fetchWorldClock = (): Promise<WorldClockState> =>
  getJson<WorldClockState>("/world/clock");

export const useWorldClock = (): UseQueryResult<WorldClockState> =>
  useQuery({
    queryKey: ["world", "clock"],
    queryFn: fetchWorldClock,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
