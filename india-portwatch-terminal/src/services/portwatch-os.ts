/**
 * HTTP calls for the agentic maritime OS surfaces.
 *
 * Same rule as `portwatch.ts`: no local fallback data. If the backend cannot
 * serve an artefact, the request fails and the screen says so.
 *
 * The advisory calls take identity headers built by `advisoryHeaders`. They are
 * asserted rather than verified in this deployment and the API says so in its
 * own policy endpoint; putting them together in one place is what makes swapping
 * in a real token a change to two functions.
 */

import { getJson, postJson } from "./api";
import type {
  Advisory,
  AdvisoryList,
  AdvisoryPolicy,
  AgentArchitecture,
  AgentRun,
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

/* -------------------------------------------------------------- global eye -- */

export const fetchGlobalEvents = (params: {
  category?: string;
  group?: string;
  minSeverity?: number;
  minConfidence?: number;
  limit?: number;
} = {}): Promise<GlobalEyeEvents> => {
  const query = new URLSearchParams();
  if (params.category) query.set("category", params.category);
  if (params.group) query.set("group", params.group);
  if (params.minSeverity != null) query.set("min_severity", String(params.minSeverity));
  if (params.minConfidence != null) query.set("min_confidence", String(params.minConfidence));
  query.set("limit", String(params.limit ?? 60));
  return getJson<GlobalEyeEvents>(`/global-eye/events?${query}`);
};

export const fetchEventImpact = (
  eventId: string,
  companyId?: string | null,
): Promise<EventImpact> =>
  getJson<EventImpact>(
    `/global-eye/events/${encodeURIComponent(eventId)}` +
      (companyId ? `?company_id=${encodeURIComponent(companyId)}` : ""),
  );

export const fetchGlobalExposure = (params: {
  companyId?: string | null;
  portCode?: string | null;
  limit?: number;
} = {}): Promise<GlobalEyeExposure> => {
  const query = new URLSearchParams();
  if (params.companyId) query.set("company_id", params.companyId);
  if (params.portCode) query.set("port_code", params.portCode);
  query.set("limit", String(params.limit ?? 20));
  return getJson<GlobalEyeExposure>(`/global-eye/exposure?${query}`);
};

export const fetchEventCalibration = (): Promise<EventCalibration> =>
  getJson<EventCalibration>("/global-eye/calibration");

/* ----------------------------------------------------------------- company -- */

export const fetchCompanyFleet = (companyId?: string | null): Promise<CompanyFleet> =>
  getJson<CompanyFleet>(
    "/company/fleet" + (companyId ? `?company_id=${encodeURIComponent(companyId)}` : ""),
  );

export const fetchCompanyRisk = (
  companyId?: string | null,
  horizonHours = 72,
): Promise<CompanyRisk> => {
  const query = new URLSearchParams({ horizon_hours: String(horizonHours) });
  if (companyId) query.set("company_id", companyId);
  return getJson<CompanyRisk>(`/company/risk?${query}`);
};

export const fetchCompanyRoutes = (companyId?: string | null): Promise<CompanyRoutes> =>
  getJson<CompanyRoutes>(
    "/company/routes" + (companyId ? `?company_id=${encodeURIComponent(companyId)}` : ""),
  );

export const fetchCompanyVessel = (
  vesselId: string,
  companyId?: string | null,
): Promise<Record<string, unknown>> =>
  getJson(
    `/company/vessels/${encodeURIComponent(vesselId)}` +
      (companyId ? `?company_id=${encodeURIComponent(companyId)}` : ""),
  );

export const fetchCompanyCargo = (
  portCode: string,
  companyId?: string | null,
): Promise<CargoOpportunities> => {
  const query = new URLSearchParams({ port_code: portCode });
  if (companyId) query.set("company_id", companyId);
  return getJson<CargoOpportunities>(`/company/cargo?${query}`);
};

/* --------------------------------------------------------------- port twin -- */

export const fetchPortTwin = (portCode: string): Promise<PortTwinState> =>
  getJson<PortTwinState>(`/port-twin/${encodeURIComponent(portCode)}`);

export const fetchTwinSimulation = (
  portCode: string,
  policy = "greedy",
  horizonHours = 24,
): Promise<TwinSimulation> =>
  getJson<TwinSimulation>(
    `/port-twin/${encodeURIComponent(portCode)}/simulate` +
      `?policy=${encodeURIComponent(policy)}&horizon_hours=${horizonHours}`,
  );

export const fetchTwinOptimize = (
  portCode: string,
  horizonHours = 24,
): Promise<TwinOptimize> =>
  getJson<TwinOptimize>(
    `/port-twin/${encodeURIComponent(portCode)}/optimize?horizon_hours=${horizonHours}`,
  );

export const fetchTwinBenchmark = (
  portCode: string,
  episodes = 20,
): Promise<Record<string, unknown>> =>
  getJson(`/port-twin/${encodeURIComponent(portCode)}/benchmark?episodes=${episodes}`);

/* ------------------------------------------------------------------- cargo -- */

export const fetchCargoPlan = (portCode: string): Promise<CargoPlan> =>
  getJson<CargoPlan>(`/cargo/optimize?port_code=${encodeURIComponent(portCode)}`);

export const fetchCargoOpportunities = (
  portCode: string,
  limit = 25,
): Promise<CargoOpportunities> =>
  getJson<CargoOpportunities>(
    `/cargo/opportunities?port_code=${encodeURIComponent(portCode)}&limit=${limit}`,
  );

/* -------------------------------------------------------------- advisories -- */

export const fetchAdvisoryPolicy = (): Promise<AdvisoryPolicy> =>
  getJson<AdvisoryPolicy>("/advisories/policy");

export const fetchAdvisories = (
  headers: Record<string, string>,
  params: { state?: string; portCode?: string; vesselId?: string } = {},
): Promise<AdvisoryList> => {
  const query = new URLSearchParams();
  if (params.state) query.set("state", params.state);
  if (params.portCode) query.set("port_code", params.portCode);
  if (params.vesselId) query.set("vessel_id", params.vesselId);
  const suffix = query.toString();
  return getJson<AdvisoryList>(`/advisories${suffix ? `?${suffix}` : ""}`, headers);
};

export const createAdvisory = (
  headers: Record<string, string>,
  payload: Record<string, unknown>,
): Promise<Advisory> => postJson<Advisory>("/advisories", payload, headers);

export const transitionAdvisory = (
  headers: Record<string, string>,
  advisoryId: string,
  target: string,
  reason?: string,
): Promise<Advisory> =>
  postJson<Advisory>(
    `/advisories/${encodeURIComponent(advisoryId)}/transition`,
    { target, reason },
    headers,
  );

export const modifyAdvisory = (
  headers: Record<string, string>,
  advisoryId: string,
  changes: Record<string, unknown>,
  reason: string,
): Promise<Advisory> =>
  postJson<Advisory>(
    `/advisories/${encodeURIComponent(advisoryId)}/modify`,
    { changes, reason },
    headers,
  );

/* ------------------------------------------------------------------ agents -- */

export const fetchAgentArchitecture = (): Promise<AgentArchitecture> =>
  getJson<AgentArchitecture>("/agents");

export const fetchToolCatalogue = (maxAccess = "PROPOSE"): Promise<ToolCatalogue> =>
  getJson<ToolCatalogue>(`/agents/tools?max_access=${encodeURIComponent(maxAccess)}`);

export const runAgent = (payload: {
  question: string;
  role?: string;
  portCode?: string | null;
  vesselId?: string | null;
  companyId?: string | null;
  eventId?: string | null;
  horizonHours?: number;
  includeResults?: boolean;
}): Promise<AgentRun> => postJson<AgentRun>("/agents/run", payload);

export const fetchAgentRuns = (limit = 20): Promise<{ runs: Array<Record<string, unknown>>; total: number }> =>
  getJson(`/agents/runs?limit=${limit}`);

export const fetchAgentRun = (runId: string): Promise<AgentRun> =>
  getJson<AgentRun>(`/agents/runs/${encodeURIComponent(runId)}?include_results=true`);

/* ---------------------------------------------------------------- learning -- */

export const fetchLearningSummary = (): Promise<LearningSummary> =>
  getJson<LearningSummary>("/learning/summary");

export const fetchReliability = (contributor?: string): Promise<ReliabilityTable> =>
  getJson<ReliabilityTable>(
    "/learning/reliability" +
      (contributor ? `?contributor=${encodeURIComponent(contributor)}` : ""),
  );

export const fetchMisses = (limit = 10): Promise<LearningMisses> =>
  getJson<LearningMisses>(`/learning/misses?limit=${limit}`);

export const fetchPolicies = (): Promise<LearningPolicies> =>
  getJson<LearningPolicies>("/learning/policies");

export const fetchLearningOutcomes = (params: {
  domain?: string;
  model?: string;
  limit?: number;
} = {}): Promise<Record<string, unknown>> => {
  const query = new URLSearchParams();
  if (params.domain) query.set("domain", params.domain);
  if (params.model) query.set("model", params.model);
  query.set("limit", String(params.limit ?? 200));
  return getJson(`/learning/outcomes?${query}`);
};

export const runOutcomePass = (): Promise<Record<string, unknown>> =>
  postJson("/learning/run", {});

export const approvePolicy = (
  policyId: string,
  approver: string,
  reason?: string,
): Promise<Record<string, unknown>> =>
  postJson(`/learning/policies/${encodeURIComponent(policyId)}/approve`, {
    approver,
    reason,
  });
