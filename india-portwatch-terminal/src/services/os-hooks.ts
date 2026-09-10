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
  fetchAttention,
  fetchAttentionItem,
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
  fetchWorldCascade,
  fetchWorldCascades,
} from "./portwatch-os";
import type {
  AdvisoryList,
  AdvisoryPolicy,
  AgentArchitecture,
  AttentionDetail,
  AttentionQueue,
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
  WorldCascade,
  WorldCascadeList,
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
 *
 * The key therefore carries *every* field the server authorises on, not just
 * the actor and role. Two identities sharing a role, or one session whose port
 * or vessel scope changes, would otherwise read each other's rows straight out
 * of the long-lived QueryClient without a request ever being made.
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
      headers["X-PortWatch-Org"] ?? null,
      headers["X-PortWatch-Port"] ?? null,
      headers["X-PortWatch-Vessels"] ?? null,
      headers["X-PortWatch-Admin"] ?? null,
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

/* --------------------------------------------------------- world engine -- */

/**
 * Every live event's consequence at one instant.
 *
 * `at` is part of the key, so scrubbing the timeline is a cache lookup after
 * the first visit to each horizon rather than a refetch -- which is what lets
 * the transport feel like moving through time rather than loading it.
 */
export const useWorldCascades = (at?: string | null): UseQueryResult<WorldCascadeList> =>
  useQuery({
    queryKey: ["world", "cascades", at ?? "now"],
    queryFn: () => fetchWorldCascades(at),
    staleTime: 60_000,
    gcTime: 600_000,
  });

export const useWorldCascade = (
  eventId: string | null,
  headers: Record<string, string>,
  at?: string | null,
): UseQueryResult<WorldCascade> =>
  useQuery({
    queryKey: [
      "world", "cascade", eventId,
      headers["X-PortWatch-Actor"] ?? null,
      headers["X-PortWatch-Role"] ?? null,
      headers["X-PortWatch-Port"] ?? null,
      headers["X-PortWatch-Org"] ?? null,
      headers["X-PortWatch-Vessels"] ?? null,
      at ?? "now",
    ],
    queryFn: () => fetchWorldCascade(eventId as string, at, headers),
    enabled: Boolean(eventId),
    staleTime: 60_000,
    gcTime: 600_000,
  });

/**
 * The ranked action queue for the signed-in identity.
 *
 * The identity is in the key for the same reason the advisory list carries it:
 * two roles see different queues from one world, and serving one of them the
 * other's is the leak the scoping exists to prevent.
 */
export const useAttention = (
  headers: Record<string, string>,
  at?: string | null,
  limit = 5,
): UseQueryResult<AttentionQueue> =>
  useQuery({
    queryKey: [
      "attention",
      headers["X-PortWatch-Actor"] ?? null,
      headers["X-PortWatch-Role"] ?? null,
      headers["X-PortWatch-Port"] ?? null,
      headers["X-PortWatch-Org"] ?? null,
      headers["X-PortWatch-Vessels"] ?? null,
      at ?? "now",
      limit,
    ],
    queryFn: () => fetchAttention(headers, at, limit),
    staleTime: 30_000,
    gcTime: 300_000,
  });

export const useAttentionItem = (
  attentionId: string | null,
  headers: Record<string, string>,
  at?: string | null,
): UseQueryResult<AttentionDetail> =>
  useQuery({
    queryKey: [
      "attention", "item", attentionId,
      headers["X-PortWatch-Actor"] ?? null,
      headers["X-PortWatch-Role"] ?? null,
      at ?? "now",
    ],
    queryFn: () => fetchAttentionItem(attentionId as string, headers, at),
    enabled: Boolean(attentionId),
    staleTime: 30_000,
  });
