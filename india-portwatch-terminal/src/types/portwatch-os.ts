/**
 * Contracts for the agentic maritime OS surfaces.
 *
 * Kept apart from `portwatch.ts`, which describes the forecasting pipeline's
 * artefacts. These are the layer built on top: events, exposure, the twin,
 * cargo, advisories, agent runs and the learning ledger.
 *
 * Every field that can honestly be absent is `| null` rather than defaulted.
 * A missing calibrated probability is not 0, an uncomputed arrival shift is not
 * 0 hours, and a screen that renders either as a number is lying quietly.
 */

/* --------------------------------------------------------------- global eye -- */

export type EventCategoryKey =
  | "conflict" | "piracy" | "sanctions" | "strike" | "port_closure" | "protest"
  | "earthquake" | "cyclone" | "tsunami" | "flood" | "canal_restriction"
  | "chokepoint_disruption" | "energy_shock" | "commodity_shock" | "regulatory"
  | "logistics_disruption" | "infrastructure";

export type EventGroup =
  | "security" | "policy" | "operations" | "natural" | "chokepoint" | "market" | "other";

export interface EventSource {
  outlet: string;
  url: string | null;
  published_at: string | null;
  title: string | null;
  feed: string;
}

export interface GlobalEvent {
  eventId: string;
  title: string;
  category: EventCategoryKey | string;
  categoryLabel: string;
  categoryGroup: EventGroup | string;
  region: string | null;
  coordinates: { lat: number; lon: number } | null;
  /** How the position was established. Never presented as a geocode when it is not. */
  geolocationBasis: "reported" | "chokepoint_centroid" | "port_location" | "unlocated";
  firstSeen: string;
  lastSeen: string;
  sources: EventSource[];
  /** Distinct outlets, not article count. This is what confidence is built from. */
  sourceCount: number;
  reportCount: number;
  confidence: number;
  severity: number;
  /** Null until enough outcomes have resolved to calibrate this category. */
  probability: number | null;
  claim: string | null;
  horizonHours: number;
  chokepoints: string[];
  forecastTrack: Array<Record<string, unknown>>;
  excerpts: string[];
  reportedPorts: string[];
  calibrationNote: string | null;
  dataSource: string;
}

export interface LaneExposure {
  laneCode: string;
  laneName: string;
  chokepoint: string;
  exposure: number;
  detourNm: number | null;
  detourHours: number | null;
  alternative: string | null;
  indiaPorts: string[];
  note: string | null;
}

export interface VesselExposure {
  vesselId: string;
  vesselName: string;
  laneCode: string;
  chokepoint: string;
  exposure: number;
  hoursToRiskArea: number | null;
  /** True when a diversion is no longer available. The gate on every action. */
  alreadyEntered: boolean;
  diversionDeadline: string | null;
  delayHoursIfDiverted: number | null;
  destinationPort: string | null;
  currentEta: string | null;
  recommendedAction:
    | "evaluate_diversion" | "monitor" | "hold_or_reschedule";
  actionBasis: string;
}

export interface PortExposure {
  portCode: string;
  portName: string;
  exposure: number;
  lanes: string[];
  affectedVessels: number;
  meanArrivalShiftHours: number | null;
  note: string | null;
}

export interface EventAction {
  action: string;
  label: string;
  count: number;
  basis: string;
  vessels?: string[];
  ports?: string[];
  meanCostHours?: number | null;
  meanShiftHours?: number | null;
  earliestDeadline?: string | null;
}

export interface EventImpact extends GlobalEvent {
  decay: number;
  worstExposure: number;
  lanes: LaneExposure[];
  vessels: VesselExposure[];
  ports: PortExposure[];
  actions: EventAction[];
  notes: string[];
}

export interface IngestReport {
  rawItems: number;
  classified: number;
  unclassified: number;
  events: number;
  located: number;
  unlocated: number;
  feeds: string[];
  notes: string[];
}

export interface GlobalEyeEvents {
  events: GlobalEvent[];
  total: number;
  returned: number;
  ingest: IngestReport;
  calibration: {
    available: boolean;
    stampedEvents: number;
    resolvedClaims: number;
    globalBaseRate: number | null;
    note: string;
  };
  categories: Array<{
    key: string; label: string; group: string; actsOn: string;
    description: string; count: number;
  }>;
}

export interface TradeLane {
  code: string;
  name: string;
  chokepoints: string[];
  indiaPorts: string[];
  primaryNm: number;
  alternative: string | null;
  alternativeNm: number | null;
  detourNm: number | null;
  description: string;
}

export interface PortRiskEntry {
  portCode: string;
  portName: string;
  risk: number;
  events: Array<{ eventId: string; title: string; category: string; exposure: number }>;
  arrivalShiftHours: number;
  affectedVessels: number;
}

export interface GlobalEyeExposure {
  impacts: EventImpact[];
  portRisk: Record<string, PortRiskEntry>;
  lanes: TradeLane[];
  ingest: IngestReport;
  calibrationAvailable: boolean;
}

/* ------------------------------------------------------------------ company -- */

export interface FleetVessel {
  vessel_id: string;
  name: string;
  /** Always null for the demo carrier: no IMO was issued to a fictional hull. */
  imo: string | null;
  vessel_class: string;
  loa_m: number;
  beam_m: number;
  draught_m: number;
  capacity_teu: number;
  reefer_plugs: number;
  service_speed_kn: number;
  flag: string;
  origin_port: string | null;
  destination_port: string | null;
  lane_code: string | null;
  laneName: string | null;
  eta: string | null;
  hours_to_chokepoint: Record<string, number>;
  available_teu: number;
  available_reefer_plugs: number;
  accepts_hazardous: boolean;
  accepts_oog: boolean;
  onward_ports: string[];
  position_source: string;
  lat: number | null;
  lon: number | null;
  cargo_value_index: number;
}

export interface CompanyFleet {
  companyId: string;
  companyName: string;
  verified: boolean;
  positionSource: string;
  disclaimer: string;
  vessels: FleetVessel[];
  lanes: Array<{
    code: string; name: string; chokepoints: string[];
    alternative: string | null; detourNm: number | null;
  }>;
}

export interface CompanyRiskRow extends VesselExposure {
  eventId: string;
  eventTitle: string;
  eventCategory: string;
  eventCategoryLabel: string;
  eventSeverity: number;
  eventConfidence: number;
  eventProbability: number | null;
  eventSourceCount: number;
}

export interface CompanyRisk {
  companyId: string;
  companyName: string;
  horizonHours: number;
  fleetSize: number;
  vesselsExposed: number;
  actionRequired: CompanyRiskRow[];
  monitorOnly: CompanyRiskRow[];
  rows: CompanyRiskRow[];
  portRisk: Record<string, PortRiskEntry>;
  disclaimer: string;
  note: string;
}

export interface CompanyRoutes {
  companyId: string;
  lanes: Array<{
    laneCode: string; laneName: string; chokepoints: string[];
    primaryNm: number; alternative: string | null; detourNm: number | null;
    description: string; exposure: number;
    vessels: Array<{ vesselId: string; name: string; destination: string | null; eta: string | null }>;
    events: Array<{ eventId: string; title: string; category: string; exposure: number }>;
  }>;
  disclaimer: string;
}

/* --------------------------------------------------------------- port twin -- */

export interface TwinBerth {
  berth_id: string;
  name: string;
  length_m: number;
  depth_m: number;
  crane_ids: string[];
  handles: string[];
  x: number;
  y: number;
  heading_deg: number;
  occupied_by: string | null;
  free_at_hour: number | null;
  occupied_hours: number;
}

export interface TwinCrane {
  crane_id: string;
  name: string;
  moves_per_hour: number;
  serves: string[];
  x: number;
  y: number;
  assigned_berth: string | null;
  working_hours: number;
}

export interface TwinYardBlock {
  block_id: string;
  name: string;
  slots: number;
  tiers: number;
  accepts: string[];
  reefer_plugs: number;
  x: number;
  y: number;
  width_m: number;
  depth_m: number;
  occupied_teu: number;
  mean_dwell_hours: number;
  capacityTeu: number;
  utilisation: number;
}

export interface TwinShed {
  shed_id: string;
  name: string;
  area_m2: number;
  stores: string[];
  x: number;
  y: number;
  width_m: number;
  depth_m: number;
  occupied_m2: number;
  utilisation: number;
}

export interface TwinGate {
  gate_id: string;
  name: string;
  lanes: number;
  trucks_per_hour: number;
  x: number;
  y: number;
  queue_trucks: number;
}

export interface TwinVehicle {
  vehicle_id: string;
  kind: string;
  moves_per_hour: number;
  x: number;
  y: number;
  assigned_block: string | null;
}

export interface TwinCall {
  call_id: string;
  vessel_id: string;
  name: string;
  vessel_class: string;
  loa_m: number;
  draught_m: number;
  eta_hour: number;
  moves: number;
  cargo_type: string;
  latest_departure_hour: number | null;
  priority: number;
  state: "approaching" | "waiting" | "alongside" | "departed";
  arrived_hour: number | null;
  berth_id: string | null;
  berthed_hour: number | null;
  departed_hour: number | null;
  assigned_cranes: string[];
  wait_hours: number;
  imposed_delay_hours: number;
  turnaroundHours: number | null;
  effectiveEta: number;
}

export interface TwinMetrics {
  hour: number;
  queueLength: number;
  alongside: number;
  berthUtilisation: number;
  yardUtilisation: number;
  craneCapacityMovesPerHour: number;
  completedCalls: number;
  meanWaitHours: number | null;
  maxWaitHours: number | null;
  meanTurnaroundHours: number | null;
  missedDepartures: number;
  yardOverflowBlocks: number;
  weatherImpact: number;
  eventRisk: number;
}

export interface PortTwinState {
  portCode: string;
  portName: string;
  hour: number;
  epoch: string | null;
  /** SCHEMATIC in this deployment. The banner is not optional. */
  geometryBasis: "SCHEMATIC" | "SURVEYED";
  geometryDisclaimer: string | null;
  extentM: [number, number];
  seawardBearing: number;
  berths: TwinBerth[];
  cranes: TwinCrane[];
  yardBlocks: TwinYardBlock[];
  sheds: TwinShed[];
  gates: TwinGate[];
  vehicles: TwinVehicle[];
  calls: TwinCall[];
  weatherImpact: number;
  eventRisk: number;
  metrics: TwinMetrics;
  notes: string[];
}

export interface PolicyDescriptor {
  policyId: string;
  name: string;
  family: string;
  description: string;
}

export interface TwinSimulation {
  portCode: string;
  portName: string;
  policy: PolicyDescriptor;
  horizonHours: number;
  metrics: TwinMetrics & { rejectedActions: number; violations: number };
  snapshots: Record<string, TwinMetrics>;
  reward: number;
  rewardBreakdown: Record<string, number>;
  violations: Array<Record<string, unknown>>;
  rejectedActions: Array<Record<string, unknown>>;
  trace: Array<{ hour: number; kind: string; subject: string; detail: string }>;
  finalState: PortTwinState;
  geometryBasis: string;
  note: string;
}

export interface TwinOptimizeRow {
  policy: PolicyDescriptor;
  metrics: TwinMetrics;
  reward: number;
  rewardBreakdown: Record<string, number>;
  violations: number;
  rejectedActions: number;
  improvementVsBaseline: number | null;
}

export interface TwinOptimize {
  portCode: string;
  horizonHours: number;
  policies: TwinOptimizeRow[];
  baselinePolicyId: string;
  geometryBasis: string;
  note: string;
}

/* ------------------------------------------------------------------- cargo -- */

export interface CargoAssignment {
  shipmentId: string;
  vesselId: string;
  vesselName: string;
  destinationPort: string;
  zoneId: string | null;
  teu: number;
  value: number;
  hoursSaved: number | null;
  handlingHours: number;
  readyHour: number;
  cutoffHour: number | null;
  slackHours: number | null;
  directTransfer: boolean;
  rationale: string;
}

export interface CargoUnplaced {
  shipmentId: string;
  teu: number;
  destinationPort: string;
  cargoClass: string;
  reasons: string[];
  nearestVessel: string | null;
  shortfallHours: number | null;
}

export interface CargoPlan {
  portCode: string;
  assignments: CargoAssignment[];
  unplaced: CargoUnplaced[];
  residualCapacity: Record<string, number>;
  totalValue: number;
  totalTeu: number;
  foregoneValue: number;
  placedCount: number;
  unplacedCount: number;
  notes: string[];
  disclaimer: string;
  method: string;
  yardBlocks?: TwinYardBlock[];
  geometryBasis?: string;
}

export interface CargoOpportunity {
  shipmentId: string;
  outboundVesselId: string;
  vesselName: string;
  destinationPort: string;
  zoneId: string | null;
  window: {
    readyHour: number;
    cutoffHour: number | null;
    handlingHours: number;
    slackHours: number | null;
    feasible: boolean;
  };
  feasible: boolean;
  reasons: string[];
  hoursSaved: number | null;
  directTransfer: boolean;
  value: number;
  rationale: string;
  teu: number;
  cargoClass: string;
}

export interface CargoOpportunities {
  portCode: string;
  opportunities: CargoOpportunity[];
  shipmentsConsidered: number;
  vesselsInScope?: number;
  disclaimer: string;
}

/* -------------------------------------------------------------- advisories -- */

export type AdvisoryState =
  | "draft" | "under_review" | "issued" | "acknowledged" | "accepted"
  | "queried" | "declined" | "rejected" | "withdrawn" | "expired" | "completed";

export interface AdvisoryAuditEntry {
  at: string;
  actor: string;
  actor_role: "issuer" | "recipient" | "system";
  action: string;
  from_state: string;
  to_state: string;
  reason: string | null;
  changes: Record<string, unknown>;
}

export interface Advisory {
  advisoryId: string;
  kind: string;
  kindLabel: string;
  portCode: string;
  issuer: string;
  issuerOrganisation: string;
  recipientVesselId: string;
  recipientVesselName: string;
  recipientOrganisation: string;
  createdAt: string;
  recommendation: Record<string, unknown>;
  reason: string;
  state: AdvisoryState;
  isTerminal: boolean;
  modelConfidence: number | null;
  predictionIds: string[];
  evidence: Record<string, unknown>;
  criticVerdict: string | null;
  criticReasons: string[];
  decisionId: string | null;
  validUntil: string | null;
  issuedAt: string | null;
  respondedAt: string | null;
  responseReason: string | null;
  modifiedFrom: Record<string, unknown> | null;
  audit: AdvisoryAuditEntry[];
  availableTransitions: Array<{
    target: AdvisoryState; label: string;
    actorRole: "issuer" | "recipient" | "system"; requiresReason: boolean;
  }>;
}

export interface AdvisoryList {
  advisories: Advisory[];
  counts: Record<string, number>;
  principal: {
    actor: string; role: string; portCode: string | null;
    organisation: string | null; vesselIds: string[]; isAdmin: boolean;
  };
}

export interface AdvisoryPolicy {
  states: AdvisoryState[];
  kinds: Array<{
    key: string; label: string; requiredField: string;
    unit: string | null; description: string;
  }>;
  transitions: Array<{
    from: string; to: string; actorRole: string;
    label: string; requiresReason: boolean;
  }>;
  rules: string[];
  identity: { source: string; verified: boolean; note: string };
}

/* ------------------------------------------------------------------ agents -- */

export type ToolAccess = "READ" | "SIMULATE" | "PROPOSE" | "EXECUTE";

export interface ToolCallTrace {
  tool: string;
  access: ToolAccess | string;
  arguments: Record<string, unknown>;
  ok: boolean;
  durationMs: number;
  error: string | null;
  unavailable: boolean;
  computedBy: string;
  agent?: string;
}

export interface AgentFinding {
  label: string;
  value: unknown;
  sourceTool: string;
  detail: string;
  confidence: number | null;
  unit: string | null;
}

export interface AgentResultView {
  agent: string;
  outcome: "complete" | "partial" | "blocked";
  summary: string;
  confidence: number | null;
  findings: AgentFinding[];
  gaps: string[];
  trace: ToolCallTrace[];
  toolsUsed: string[];
  unavailableTools: string[];
  ranAt: string;
  data: Record<string, unknown>;
}

export interface CriticCheckView {
  name: string;
  passed: boolean;
  severity: "blocking" | "qualifying";
  detail: string;
  remedy: string | null;
}

export interface CriticVerdictView {
  verdict: "APPROVED" | "MODIFIED" | "REJECTED";
  checks: CriticCheckView[];
  reasons: string[];
  qualifications: string[];
  adjustedConfidence: number | null;
  failedChecks: string[];
  ranAt: string;
}

export interface AgentRun {
  runId: string;
  question: string;
  intent: string;
  intentLabel: string;
  intentBasis: string;
  role: string;
  startedAt: string;
  durationMs: number;
  outcome: "complete" | "partial" | "blocked";
  summary: string;
  confidence: number | null;
  gaps: string[];
  agents: AgentResultView[];
  trace: ToolCallTrace[];
  recommendation: {
    kind: string; subject: string; action: string;
    values: Record<string, unknown>; expectedImpact: Record<string, number>;
    confidence: number | null; evidenceTools: string[]; reason: string;
  } | null;
  critic: CriticVerdictView | null;
  decisionId: string | null;
  /**
   * What the world should show, derived from what the tools returned.
   *
   * Every command names the tool call that justifies it, and carries its own
   * safety class: UI commands run on arrival, SIMULATION needs an open
   * simulation context, OPERATIONAL never runs from an answer.
   */
  spatial: Array<{
    kind: string;
    subject: string | null;
    evidenceTool: string;
    reason: string;
    params: Record<string, unknown>;
    safety: "UI" | "SIMULATION" | "OPERATIONAL";
    autoExecutable: boolean;
  }>;
  note: string;
}

export interface AgentArchitecture {
  command: { name: string; purpose: string; maxAccess: string };
  intents: Array<{
    key: string; label: string; agents: string[];
    highImpact: boolean; description: string;
  }>;
  agents: Array<{
    name: string; purpose: string; allowedTools: string[];
    maxAccess: string; failureModes: string[];
  }>;
  critic: { name: string; purpose: string; verdicts: string[]; checks: string[]; note: string };
  boundary: { note: string };
}

export interface ToolCatalogue {
  ceiling: string;
  tools: Array<{
    name: string; description: string; access: ToolAccess;
    computedBy: string; returns: string; failureModes: string[];
    inputSchema: { type: string; properties: Record<string, { type: string; description: string }>; required: string[] };
  }>;
  byAccess: Record<string, string[]>;
  boundary: Record<string, string>;
}

/* ---------------------------------------------------------------- learning -- */

export interface ErrorReportView {
  count: number;
  meanAbsoluteError: number | null;
  rootMeanSquareError: number | null;
  bias: number | null;
  medianAbsoluteError: number | null;
  intervalCoverage: number | null;
  nominalCoverage: number | null;
  coverageError: number | null;
}

export interface CalibrationBinView {
  lower: number;
  upper: number;
  count: number;
  meanPredicted: number | null;
  observedRate: number | null;
  gap: number | null;
}

export interface BinaryScoreView {
  count: number;
  brier: number | null;
  logLoss: number | null;
  baseRate: number | null;
  referenceBrier: number | null;
  brierSkill: number | null;
  meanLeadTimeHours: number | null;
  falseAlarmRate: number | null;
  calibration: {
    bins: CalibrationBinView[];
    expectedCalibrationError: number | null;
    maxCalibrationError: number | null;
    overForecast: number | null;
    sampleCount: number;
  } | null;
  confusion: {
    truePositive: number; falsePositive: number;
    trueNegative: number; falseNegative: number;
    precision: number | null; recall: number | null;
    falsePositiveRate: number | null; f1: number | null;
  } | null;
}

export interface SliceReportView {
  key: string;
  label: string;
  count: number;
  continuous: ErrorReportView | null;
  binary: BinaryScoreView | null;
}

export interface LearningSummary {
  counts: Record<string, Record<string, number>>;
  overall: SliceReportView;
  events: {
    available: boolean;
    count?: number;
    note?: string;
    overall?: BinaryScoreView;
    byCategory?: Record<string, BinaryScoreView>;
    byRegion?: Record<string, BinaryScoreView>;
    byHorizon?: Record<string, BinaryScoreView>;
    byConfidence?: Record<string, BinaryScoreView>;
    bySource?: Record<string, BinaryScoreView>;
  };
  decisions: {
    available: boolean;
    count?: number;
    resolved?: number;
    takeUpRate?: number | null;
    meanReward?: number | null;
    meanImpactError?: number | null;
    byKind?: Record<string, { count: number; takeUpRate: number | null; meanReward: number | null }>;
  };
  activePolicyId: string | null;
  reliabilityRows: number;
  ranAt: string;
  note: string;
}

export interface ReliabilityWeight {
  contributor: string;
  context: string;
  dimensions: string[];
  weight: number;
  previousWeight: number | null;
  delta: number | null;
  samples: number;
  meanAbsoluteError: number | null;
  bias: number | null;
  calibrationError: number | null;
  updatedAt: string;
  fittedFrom: string | null;
  fittedTo: string | null;
  notes: string | null;
}

export interface ReliabilityTable {
  weights: ReliabilityWeight[];
  changedCount: number;
  contributors: string[];
  method: string;
}

export interface AttributionShare {
  contributor: string;
  signal: number;
  weight: number;
  contribution: number;
  share: number | null;
  ownError: number;
}

export interface MissReport {
  predictionId: string;
  subject: string;
  target: string;
  validAt: string;
  kind: string;
  predicted: number | null;
  observed: number | null;
  error: number | null;
  context: Record<string, unknown>;
  attribution: {
    predictionId: string;
    /** False when no per-contributor signals were recorded. Render the reason. */
    available: boolean;
    reason: string | null;
    predicted: number | null;
    observed: number | null;
    error: number | null;
    residual: number | null;
    dominant: string | null;
    shares: AttributionShare[];
  };
  reliabilityChanges: Array<{
    contributor: string; context: string;
    from: number; to: number; delta: number; samples: number;
  }>;
}

export interface LearningMisses {
  misses: MissReport[];
  resolvedCount: number;
  attributionAvailable: number;
  method: string;
}

export interface PolicyRecordView {
  policyId: string;
  name: string;
  family: string;
  version: string;
  state: "candidate" | "evaluating" | "approved" | "rejected" | "retired";
  environment: string | null;
  training: Record<string, unknown>;
  evaluation: Record<string, unknown>;
  safetyChecks: Record<string, boolean>;
  approvedBy: string | null;
  approvedAt: string | null;
  rejectionReason: string | null;
  createdAt: string;
  updatedAt: string;
  notes: string | null;
}

export interface LearningPolicies {
  policies: PolicyRecordView[];
  activePolicyId: string | null;
  states: { candidate: number; evaluating: number; approved: number };
  note: string;
}

export interface EventCalibration {
  calibrator: {
    available: boolean;
    fittedAt: string | null;
    globalBaseRate: number | null;
    globalCount: number;
    minGlobalSamples: number;
    minCategorySamples: number;
    categoryBase: Record<string, { rate: number; count: number }>;
    buckets: Array<{
      category: string; bucket: number; label: string; count: number;
      occurrences: number; observedRate: number | null;
      probability: number; prior: number; meanRawScore: number | null;
    }>;
    inSample: Record<string, unknown>;
  };
  scores: LearningSummary["events"];
}

/* --------------------------------------------------------- world engine -- */

/**
 * A dimensioned magnitude the World State Engine produced.
 *
 * The unit travels with the value because a cascade changes unit as it
 * propagates -- risk becomes exposed hulls becomes delay hours becomes yard
 * pressure. A number without its unit is not a claim this product makes.
 */
export interface WorldQuantity {
  value: number;
  unit: string;
  unitLabel: string;
  confidence: number;
  interval: { start: string | null; end: string | null };
  attrs: Record<string, unknown>;
}

/** One hop of a cascade. The unit of Evidence Mode. */
export interface CascadeStep {
  depth: number;
  from: string;
  to: string;
  edgeKind: string;
  rule: string;
  source: string;
  incoming: WorldQuantity;
  outgoing: WorldQuantity[];
  declined: string | null;
}

/** One thing a cascade reached, with the geometry needed to place it. */
export interface CascadeSubject {
  key: string;
  id: string;
  kind: string;
  label: string;
  depth: number;
  lat: number | null;
  lon: number | null;
  attrs: Record<string, unknown>;
  quantities: Record<string, WorldQuantity>;
  steps: number[];
}

export interface CascadeAffected {
  chokepoints: CascadeSubject[];
  lanes: CascadeSubject[];
  vessels: CascadeSubject[];
  ports: CascadeSubject[];
}

export interface WorldCascade {
  eventId: string;
  title: string;
  live: boolean;
  category?: string;
  lat?: number | null;
  lon?: number | null;
  seed?: { node: string; quantity: WorldQuantity };
  at: string | null;
  reached?: Array<{ node: Record<string, unknown>; depth: number }>;
  steps?: CascadeStep[];
  narrative?: string[];
  affected?: CascadeAffected;
  totals?: Record<string, WorldQuantity>;
  notes?: string[];
  nodeCount: number;
  truncated?: boolean;
  attentionItems?: AttentionItem[];
  reason?: string;
}

export interface WorldCascadeList {
  at: string;
  cascades: WorldCascade[];
  total: number;
}

export interface WorldStateSummary {
  at: string;
  summary: {
    nodes: number;
    edges: number;
    byNodeKind: Record<string, number>;
    byEdgeKind: Record<string, number>;
  };
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
  rules: Array<{
    appliesTo: string; on: string; fromUnit: string; rule: string; explains: string;
  }>;
  projectionOffsets: number[];
  maxHorizonHours: number;
}

export interface ProjectionFrame {
  offsetHours: number;
  at: string;
  live: boolean;
  nodeCount: number;
  affected: CascadeAffected;
  totals: Record<string, WorldQuantity>;
  notes: string[];
}

export interface WorldProjection {
  eventId: string;
  title: string;
  base: string;
  horizonHours: number;
  frames: ProjectionFrame[];
}

/* ------------------------------------------------------------ attention -- */

export interface AttentionEffect {
  value: number | null;
  unit: string | null;
  confidence: number | null;
  statement: string;
  available: boolean;
  unavailableBecause: string | null;
  rule: string | null;
}

export interface AttentionOption {
  action: string;
  summary: string;
  closesInHours: number | null;
  effect: AttentionEffect;
  tradeoff: string;
}

export type AttentionStatus =
  | "ACT_NOW"
  | "ACT_SOON"
  | "WATCH"
  | "MONITOR_ONLY"
  | "NO_ACTION_AVAILABLE";

export interface AttentionItem {
  attentionId: string;
  subjectType: string;
  subjectId: string;
  subjectLabel: string;
  scope: string;
  headline: string;
  reason: string;
  severity: number;
  confidence: number;
  urgency: number;
  status: AttentionStatus;
  actionable: boolean;
  actionDeadline: string | null;
  interventionWindowHours: number | null;
  baselineOutcome: string;
  doNothingOutcome: string;
  recommendedAction: AttentionOption | null;
  alternativeActions: AttentionOption[];
  expectedOperationalEffect: AttentionEffect;
  expectedFinancialEffect: AttentionEffect;
  financialEffectAvailable: boolean;
  cascadeId: string;
  evidenceNodeKey: string;
  priority: number;
  priorityBasis: Record<string, number>;
}

export interface AttentionQueue {
  at: string;
  scope: string;
  items: AttentionItem[];
  total: number;
  actionable: number;
}

export interface AttentionDetail {
  item: AttentionItem;
  evidence: CascadeStep[];
  narrative: string[];
  cascade: { eventId: string; title: string; seed: string; at: string };
}

/* -------------------------------------------------------- signal fabric -- */

export interface SignalAvailability {
  status: string;
  reason: string;
  needs: string[];
}

export interface SignalQuality {
  level: string;
  usable: boolean;
  reasons: string[];
}

export interface SignalHealthRow {
  capability: string;
  providerId: string;
  providerName: string;
  availability: SignalAvailability;
  /** LIVE | CACHED | STALE | EXPIRED | UNKNOWN | UNAVAILABLE */
  freshness: string;
  /** Age of the reading, not of the request that fetched it. */
  ageSeconds: number | null;
  quality: SignalQuality | null;
  licenceMode: string;
  commercialUse: boolean | null;
  attributionRequired: boolean | null;
}

export interface TrafficMode {
  mode: "LIVE_AIS" | "SIMULATED_TRAFFIC" | "UNAVAILABLE";
  providerId: string | null;
  statement: string;
  availability: SignalAvailability;
}

export interface SignalHealth {
  mode: string;
  traffic: TrafficMode;
  signals: SignalHealthRow[];
  /** Capabilities the registry knows and nothing reads yet. */
  unwired: string[];
}
