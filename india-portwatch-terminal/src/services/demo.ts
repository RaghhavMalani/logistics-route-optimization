import type { Session } from "@/auth/types";
import type { Workspace, Scenario } from "./public-workspace";
import type { PortTwinState, TwinMetrics } from "@/types/portwatch-os";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { getJson, postJson } from "./api";

/** The one visitor-owned world; route adapters never query operational APIs. */
export function useDemoWorkspace() {
  const auth = useAuth();
  return useQuery({
    queryKey: ["demo-world", auth.session?.accessToken],
    queryFn: ({ signal }) =>
      getJson<DemoWorkspaceData>("/demo/workspace", {}, { signal }),
    enabled: auth.mode === "demo",
    staleTime: 10000,
    retry: false,
  });
}
export function useDemoAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) =>
      postJson(path, body ?? {}),
    onSuccess: () => client.invalidateQueries({ queryKey: ["demo-world"] }),
  });
}
export interface DemoVessel {
  id: string;
  name: string;
  laneCode: string;
  portCode: string;
  hoursToRisk: number;
  etaHours: number;
  lat: number;
  lon: number;
  cargo: string;
  status: string;
  mmsi: null;
}
export interface DemoComparison {
  id: string;
  vesselId: string;
  recordedAt: string;
  result: Scenario;
}
export interface DemoProposal {
  comparisonId: string;
  optionId: string;
  vesselId: string;
  etaShiftHours: number | null;
  createdAt: string;
  state: string;
}
export interface DemoPortOption {
  policy: string;
  metrics: TwinMetrics;
  violations: unknown[];
  rejectedActions: unknown[];
  finalState: PortTwinState;
}
export interface DemoAdvisory {
  id: string;
  proposal: DemoProposal;
  state: string;
  issuedAt: string;
  portPlan: {
    policy: string;
    inputs: { weatherImpact: number; horizonHours: number };
    seed: number;
    metrics: TwinMetrics;
    violations: unknown[];
  };
  acknowledgedAt?: string;
  meaning: string;
  outcome?: {
    reportedWaitingHours: number;
    recordedAt: string;
    source: string;
    meaning: string;
  };
}
export interface DemoWorkspaceData {
  session: Session;
  scene: Workspace;
  twin: PortTwinState;
  scope: string;
  world: {
    version: string;
    epoch: string;
    meaning: string;
    organisation: string;
    portCode: string;
    selectedVessel: string;
    event: {
      id: string;
      title: string;
      source: string;
      chokepoint: string;
      closureHours: number;
    };
    fleet: DemoVessel[];
    comparisons: DemoComparison[];
    proposal: DemoProposal | null;
    portComparison: {
      recordedAt: string;
      inputs: { weatherImpact: number; horizonHours: number };
      seed: number;
      meaning: string;
      options: DemoPortOption[];
    } | null;
    advisories: DemoAdvisory[];
  };
}
