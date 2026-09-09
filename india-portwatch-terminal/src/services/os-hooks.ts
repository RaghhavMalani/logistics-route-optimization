/**
 * Query hooks for the agentic maritime OS surfaces.
 *
 * Separate from `hooks.ts`, which serves the forecasting pipeline's artefacts,
 * because the cache policies genuinely differ: an event feed goes stale in
 * minutes where a forecast artefact does not, and a twin simulation costs real
 * server time and is worth holding for longer than either.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import {
  fetchAdvisories,
  fetchAdvisoryPolicy,
  fetchAgentArchitecture,
  fetchCargoOpportunities,
  fetchCargoPlan,
  fetchCompanyCargo,
  fetchCompanyFleet,
  fetchCompanyRisk,
  fetchCompanyRoutes,
  fetchEventCalibration,
  fetchEventImpact,
  fetchGlobalEvents,
  fetchGlobalExposure,
  fetchLearningSummary,
  fetchMisses,
  fetchPolicies,
  fetchPortTwin,
  fetchReliability,
  fetchToolCatalogue,
  fetchTwinOptimize,
  fetchTwinSimulation,
} from "./portwatch-os";
import type {
  AdvisoryList,
  AdvisoryPolicy,
  AgentArchitecture,
  CargoOpportunities,
  CargoPlan,
  CompanyFleet,
  CompanyRisk,
  CompanyRoutes,
  EventCalibration,
  EventImpact,
  GlobalEyeEvents,
  GlobalEyeExposure,
  LearningMisses,
  LearningPolicies,
  LearningSummary,
  PortTwinState,
  ReliabilityTable,
  ToolCatalogue,
  TwinOptimize,
  TwinSimulation,
} from "@/types/portwatch-os";

/** Structural artefacts: the tool catalogue, the advisory policy. */
const STATIC = { staleTime: 300_000, gcTime: 1_800_000 } as const;
/** An event feed is worth re-reading on a view change. */
const FEED = { staleTime: 120_000, gcTime: 900_000 } as const;
/** A simulation costs real time server-side, so hold it. */
const HEAVY = { staleTime: 300_000, gcTime: 1_800_000 } as const;

/* -------------------------------------------------------------- global eye -- */

export const useGlobalEvents = (
  params: Parameters<typeof fetchGlobalEvents>[0] = {},
): UseQueryResult<GlobalEyeEvents> =>
  useQuery({
    queryKey: ["global-eye", "events", params],
    queryFn: () => fetchGlobalEvents(params),
    ...FEED,
  });

export const useEventImpact = (
  eventId: string | null | undefined,
  companyId?: string | null,
): UseQueryResult<EventImpact> =>
  useQuery({
    queryKey: ["global-eye", "impact", eventId, companyId ?? null],
    queryFn: () => fetchEventImpact(eventId as string, companyId),
    enabled: Boolean(eventId),
    ...FEED,
  });

export const useGlobalExposure = (
  params: Parameters<typeof fetchGlobalExposure>[0] = {},
): UseQueryResult<GlobalEyeExposure> =>
  useQuery({
    queryKey: ["global-eye", "exposure", params],
    queryFn: () => fetchGlobalExposure(params),
    ...FEED,
  });

export const useEventCalibration = (): UseQueryResult<EventCalibration> =>
  useQuery({
    queryKey: ["global-eye", "calibration"],
    queryFn: fetchEventCalibration,
    ...STATIC,
  });

/* ----------------------------------------------------------------- company -- */

export const useCompanyFleet = (
  companyId?: string | null,
): UseQueryResult<CompanyFleet> =>
  useQuery({
    queryKey: ["company", "fleet", companyId ?? null],
    queryFn: () => fetchCompanyFleet(companyId),
    ...STATIC,
  });

export const useCompanyRisk = (
  companyId?: string | null,
  horizonHours = 72,
): UseQueryResult<CompanyRisk> =>
  useQuery({
    queryKey: ["company", "risk", companyId ?? null, horizonHours],
    queryFn: () => fetchCompanyRisk(companyId, horizonHours),
    ...FEED,
  });

export const useCompanyRoutes = (
  companyId?: string | null,
): UseQueryResult<CompanyRoutes> =>
  useQuery({
    queryKey: ["company", "routes", companyId ?? null],
    queryFn: () => fetchCompanyRoutes(companyId),
    ...FEED,
  });

export const useCompanyCargo = (
  portCode: string | null | undefined,
  companyId?: string | null,
): UseQueryResult<CargoOpportunities> =>
  useQuery({
    queryKey: ["company", "cargo", portCode, companyId ?? null],
    queryFn: () => fetchCompanyCargo(portCode as string, companyId),
    enabled: Boolean(portCode),
    ...HEAVY,
  });

/* --------------------------------------------------------------- port twin -- */

export const usePortTwin = (
  portCode: string | null | undefined,
): UseQueryResult<PortTwinState> =>
  useQuery({
    queryKey: ["port-twin", portCode],
    queryFn: () => fetchPortTwin(portCode as string),
    enabled: Boolean(portCode),
    ...STATIC,
  });

export const useTwinSimulation = (
  portCode: string | null | undefined,
  policy = "greedy",
  horizonHours = 24,
): UseQueryResult<TwinSimulation> =>
  useQuery({
    queryKey: ["port-twin", "simulate", portCode, policy, horizonHours],
    queryFn: () => fetchTwinSimulation(portCode as string, policy, horizonHours),
    enabled: Boolean(portCode),
    ...HEAVY,
  });

export const useTwinOptimize = (
  portCode: string | null | undefined,
  horizonHours = 24,
): UseQueryResult<TwinOptimize> =>
  useQuery({
    queryKey: ["port-twin", "optimize", portCode, horizonHours],
    queryFn: () => fetchTwinOptimize(portCode as string, horizonHours),
    enabled: Boolean(portCode),
    ...HEAVY,
  });

/* ------------------------------------------------------------------- cargo -- */

export const useCargoPlan = (
  portCode: string | null | undefined,
): UseQueryResult<CargoPlan> =>
  useQuery({
    queryKey: ["cargo", "plan", portCode],
    queryFn: () => fetchCargoPlan(portCode as string),
    enabled: Boolean(portCode),
    ...HEAVY,
  });

export const useCargoOpportunities = (
  portCode: string | null | undefined,
  limit = 25,
): UseQueryResult<CargoOpportunities> =>
  useQuery({
    queryKey: ["cargo", "opportunities", portCode, limit],
    queryFn: () => fetchCargoOpportunities(portCode as string, limit),
    enabled: Boolean(portCode),
    ...HEAVY,
  });

/* -------------------------------------------------------------- advisories -- */

export const useAdvisoryPolicy = (): UseQueryResult<AdvisoryPolicy> =>
  useQuery({ queryKey: ["advisories", "policy"], queryFn: fetchAdvisoryPolicy, ...STATIC });

/**
 * Advisories visible to the signed-in identity.
 *
 * The acting identity is part of the query key. A controller and a master
 * looking at the same port see different rows, and caching both under one key
 * would show one of them the other's view -- which for a draft advisory is
 * exactly the leak the workflow exists to prevent.
 */
export const useAdvisories = (
  headers: Record<string, string>,
  params: { state?: string; portCode?: string; vesselId?: string } = {},
): UseQueryResult<AdvisoryList> =>
  useQuery({
    queryKey: [
      "advisories",
      headers["X-PortWatch-Actor"] ?? null,
      headers["X-PortWatch-Role"] ?? null,
      params,
    ],
    queryFn: () => fetchAdvisories(headers, params),
    enabled: Boolean(headers["X-PortWatch-Actor"]),
    staleTime: 20_000,
    gcTime: 300_000,
  });

/* ------------------------------------------------------------------ agents -- */

export const useAgentArchitecture = (): UseQueryResult<AgentArchitecture> =>
  useQuery({ queryKey: ["agents", "architecture"], queryFn: fetchAgentArchitecture, ...STATIC });

export const useToolCatalogue = (maxAccess = "EXECUTE"): UseQueryResult<ToolCatalogue> =>
  useQuery({
    queryKey: ["agents", "tools", maxAccess],
    queryFn: () => fetchToolCatalogue(maxAccess),
    ...STATIC,
  });

/* ---------------------------------------------------------------- learning -- */

export const useLearningSummary = (): UseQueryResult<LearningSummary> =>
  useQuery({ queryKey: ["learning", "summary"], queryFn: fetchLearningSummary, ...FEED });

export const useReliability = (contributor?: string): UseQueryResult<ReliabilityTable> =>
  useQuery({
    queryKey: ["learning", "reliability", contributor ?? null],
    queryFn: () => fetchReliability(contributor),
    ...FEED,
  });

export const useMisses = (limit = 10): UseQueryResult<LearningMisses> =>
  useQuery({
    queryKey: ["learning", "misses", limit],
    queryFn: () => fetchMisses(limit),
    ...FEED,
  });

export const usePolicies = (): UseQueryResult<LearningPolicies> =>
  useQuery({ queryKey: ["learning", "policies"], queryFn: fetchPolicies, ...FEED });
