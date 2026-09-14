/**
 * HTTP calls for the decision engine, the financial twin and the missions.
 *
 * Same rule as the rest of the service layer: no local fallback. A decision
 * the backend could not compute is an error the screen shows, never a card
 * filled in with plausible numbers.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import { getJson, postJson } from "./api";
import type {
  DecisionHandoff,
  DecisionLearning,
  DecisionList,
  DecisionProblem,
  FinanceBasis,
  FinanceTariffs,
  MissionReplayState,
  MissionReveal,
  MissionSummary,
} from "@/types/decisions";

/* ------------------------------------------------------------- decisions -- */

export interface CreateDecisionPayload {
  domain: "vessel" | "port" | "cargo";
  vesselId?: string;
  eventId?: string;
  branchId?: string;
  seed?: string;
  portCode?: string;
  shipmentId?: string;
  bunchArrivals?: number;
  horizonHours?: number;
  attentionId?: string;
  at?: string | null;
  mode?: string;
  companyId?: string | null;
  assumptions?: Array<{
    primitive: string;
    value: number;
    currency: string;
    scope?: string;
    note?: string;
  }>;
  /** Figures the hull does not declare, supplied for this scenario (gross tonnage). */
  vesselAssumptions?: Record<string, number>;
}

/** What an operator may assume to price a scenario; every figure is labelled ASSUMPTION. */
export interface ScenarioAssumptions {
  rates: Array<{ primitive: string; value: number; currency: string }>;
  vessel: Record<string, number>;
}

export const createDecision = (
  payload: CreateDecisionPayload,
  headers: Record<string, string> = {},
): Promise<DecisionProblem> =>
  postJson<DecisionProblem>("/decisions/problems", payload, headers);

export const fetchDecision = (decisionId: string): Promise<DecisionProblem> =>
  getJson<DecisionProblem>(
    `/decisions/problems/${encodeURIComponent(decisionId)}`,
  );

export const fetchDecisions = (limit = 20): Promise<DecisionList> =>
  getJson<DecisionList>(`/decisions/problems?limit=${limit}`);

export const transitionDecision = (
  decisionId: string,
  body: { target: string; optionId?: string | null; note?: string },
  headers: Record<string, string> = {},
): Promise<DecisionProblem> =>
  postJson<DecisionProblem>(
    `/decisions/problems/${encodeURIComponent(decisionId)}/transition`,
    body,
    headers,
  );

export const handoffDecision = (
  decisionId: string,
  body: Record<string, unknown> = {},
  headers: Record<string, string> = {},
): Promise<DecisionHandoff> =>
  postJson<DecisionHandoff>(
    `/decisions/problems/${encodeURIComponent(decisionId)}/handoff`,
    body,
    headers,
  );

export const recordDecisionOutcome = (
  decisionId: string,
  body: {
    actualAction: string;
    observed: Record<string, number>;
    note?: string;
  },
  headers: Record<string, string> = {},
): Promise<DecisionProblem> =>
  postJson<DecisionProblem>(
    `/decisions/problems/${encodeURIComponent(decisionId)}/outcome`,
    body,
    headers,
  );

export const fetchDecisionLearning = (): Promise<DecisionLearning> =>
  getJson<DecisionLearning>("/decisions/learning");

/* --------------------------------------------------------------- finance -- */

export const fetchFinanceBasis = (
  scope?: string | null,
): Promise<FinanceBasis> =>
  getJson<FinanceBasis>(
    `/finance/basis${scope ? `?scope=${encodeURIComponent(scope)}` : ""}`,
  );

export const fetchFinanceTariffs = (): Promise<FinanceTariffs> =>
  getJson<FinanceTariffs>("/finance/tariffs");

export const addFinanceAssumption = (
  body: {
    primitive: string;
    value: number;
    currency: string;
    scope?: string;
    note?: string;
    purpose?: string;
  },
  headers: Record<string, string> = {},
): Promise<{ added: unknown; label: string }> =>
  postJson("/finance/assumptions", body, headers);

/* -------------------------------------------------------------- missions -- */

export const fetchMissions = (): Promise<{ missions: MissionSummary[] }> =>
  getJson("/missions");

export const fetchMission = (missionId: string): Promise<MissionReplayState> =>
  getJson<MissionReplayState>(`/missions/${encodeURIComponent(missionId)}`);

export const openMissionReplay = (
  missionId: string,
  body: { offsetHours?: number; clock?: string } = {},
): Promise<MissionReplayState> =>
  postJson(`/missions/${encodeURIComponent(missionId)}/replay`, body);

export const seekMissionReplay = (
  missionId: string,
  body: { offsetHours?: number; clock?: string },
): Promise<MissionReplayState> =>
  postJson(`/missions/${encodeURIComponent(missionId)}/seek`, body);

export const decideOnMission = (
  missionId: string,
  vesselId: string,
  headers: Record<string, string> = {},
): Promise<DecisionProblem> =>
  postJson(
    `/missions/${encodeURIComponent(missionId)}/decide`,
    { vesselId },
    headers,
  );

export const chooseOnMission = (
  missionId: string,
  body: { vesselId: string; optionId: string },
  headers: Record<string, string> = {},
): Promise<DecisionProblem> =>
  postJson(`/missions/${encodeURIComponent(missionId)}/choose`, body, headers);

export const revealMission = (
  missionId: string,
  headers: Record<string, string> = {},
): Promise<MissionReveal> =>
  postJson(`/missions/${encodeURIComponent(missionId)}/reveal`, {}, headers);

/* ----------------------------------------------------------------- hooks -- */

const HEAVY = { staleTime: 300_000, gcTime: 1_800_000 } as const;

export const useDecision = (
  decisionId: string | null | undefined,
): UseQueryResult<DecisionProblem> =>
  useQuery({
    queryKey: ["decision", decisionId],
    queryFn: () => fetchDecision(decisionId as string),
    enabled: Boolean(decisionId),
    ...HEAVY,
  });

export const useDecisions = (limit = 20): UseQueryResult<DecisionList> =>
  useQuery({
    queryKey: ["decisions", limit],
    queryFn: () => fetchDecisions(limit),
    staleTime: 30_000,
  });

export const useDecisionLearning = (): UseQueryResult<DecisionLearning> =>
  useQuery({
    queryKey: ["decisions", "learning"],
    queryFn: fetchDecisionLearning,
    staleTime: 60_000,
  });

export const useFinanceBasis = (
  scope?: string | null,
): UseQueryResult<FinanceBasis> =>
  useQuery({
    queryKey: ["finance", "basis", scope ?? null],
    queryFn: () => fetchFinanceBasis(scope),
    staleTime: 60_000,
  });

export const useFinanceTariffs = (): UseQueryResult<FinanceTariffs> =>
  useQuery({
    queryKey: ["finance", "tariffs"],
    queryFn: fetchFinanceTariffs,
    ...HEAVY,
  });

export const useMissions = (): UseQueryResult<{ missions: MissionSummary[] }> =>
  useQuery({ queryKey: ["missions"], queryFn: fetchMissions, ...HEAVY });

export const useMission = (
  missionId: string | null,
): UseQueryResult<MissionReplayState> =>
  useQuery({
    queryKey: ["mission", missionId],
    queryFn: () => fetchMission(missionId as string),
    enabled: Boolean(missionId),
    staleTime: 10_000,
  });

/** Create a decision and prime its cache so the panel opens without a second round trip. */
export function useCreateDecision(headers: Record<string, string>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateDecisionPayload) =>
      createDecision(payload, headers),
    onSuccess: (problem) => {
      client.setQueryData(["decision", problem.decisionId], problem);
      void client.invalidateQueries({ queryKey: ["decisions"] });
    },
  });
}

export function useDecisionWorkflow(headers: Record<string, string>) {
  const client = useQueryClient();
  const settle = (problem: DecisionProblem) => {
    client.setQueryData(["decision", problem.decisionId], problem);
    void client.invalidateQueries({ queryKey: ["decisions"] });
  };
  const transition = useMutation({
    mutationFn: (args: {
      decisionId: string;
      target: string;
      optionId?: string | null;
      note?: string;
    }) =>
      transitionDecision(
        args.decisionId,
        { target: args.target, optionId: args.optionId, note: args.note },
        headers,
      ),
    onSuccess: settle,
  });
  const handoff = useMutation({
    mutationFn: (args: {
      decisionId: string;
      body?: Record<string, unknown>;
    }) => handoffDecision(args.decisionId, args.body ?? {}, headers),
    onSuccess: (result) => {
      void client.invalidateQueries({
        queryKey: ["decision", result.decision.decisionId],
      });
      void client.invalidateQueries({ queryKey: ["advisories"] });
    },
  });
  const outcome = useMutation({
    mutationFn: (args: {
      decisionId: string;
      actualAction: string;
      observed: Record<string, number>;
      note?: string;
    }) =>
      recordDecisionOutcome(
        args.decisionId,
        {
          actualAction: args.actualAction,
          observed: args.observed,
          note: args.note,
        },
        headers,
      ),
    onSuccess: (problem) => {
      client.setQueryData(["decision", problem.decisionId], problem);
      void client.invalidateQueries({ queryKey: ["decisions", "learning"] });
    },
  });
  return { transition, handoff, outcome };
}
