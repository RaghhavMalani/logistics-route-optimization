/**
 * API contract for the India PortWatch terminal.
 *
 * Every type here mirrors exactly what the backend serves from pipeline
 * artefacts. Fields are nullable wherever the pipeline can genuinely fail to
 * produce a value: the UI renders the gap rather than substituting a plausible
 * number, which is the whole point of the provenance model.
 */

export type RiskLevel = "normal" | "congested" | "severe";
export type OperationalRiskLevel = "normal" | "medium" | "high" | "severe";
export type Coast = "west" | "east" | "south";

/** Provenance vocabulary shared by the pipeline, the API and this UI. */
export type DataStatus =
  | "LIVE"
  | "CACHED_LIVE"
  | "STALE"
  | "SYNTHETIC"
  | "UNAVAILABLE";

export interface GeoPoint {
  lat: number;
  lon: number;
}

export interface HistoryPoint {
  date: string | null;
  value: number | null;
}

/* -------------------------------------------------------------- health ---- */

export interface HealthSources {
  readiness: number;
  live: string[];
  cached: string[];
  stale: string[];
  synthetic: string[];
  unavailable: string[];
}

export interface Health {
  status: string;
  service: string;
  serverTimeUtc: string;
  intelligence: "live" | "cached" | "stale" | "not_ready";
  cacheAgeSeconds: number | null;
  lastRefreshUtc: string | null;
  model: string | null;
  forecastOrigin: string | null;
  forecastOriginStatus: DataStatus | null;
  forecastOriginAgeHours: number | null;
  horizonDays: number | null;
  ports: number | null;
  availablePorts: string[];
  artefacts: Record<string, boolean>;
  benchmark: {
    available: boolean;
    version?: string | null;
    generatedAt?: string | null;
    bestModel?: string | null;
    folds?: number | null;
  };
  sources: HealthSources;
}

export interface ProvenanceSource {
  source: string;
  status: DataStatus;
  provider: string;
  detail: string;
  observed_at: string | null;
  fetched_at: string | null;
  age_seconds: number | null;
  ageHours: number | null;
  /** How old this source may get before the pipeline marks it STALE. */
  freshness_budget_hours?: number | null;
  confidence: number;
  fallback: string | null;
  rows: number | null;
  isReal: boolean;
}

export interface Provenance {
  generatedAt?: string;
  readiness: number;
  counts?: Record<string, number>;
  live?: string[];
  cached?: string[];
  stale?: string[];
  synthetic?: string[];
  unavailable?: string[];
  sources: Record<string, ProvenanceSource>;
  forecastOrigin?: string | null;
  cacheAgeSeconds?: number | null;
  reason?: string;
}

/* --------------------------------------------------------------- ports ---- */

export interface PortSnapshot {
  code: string;
  portCode: string;
  modelId: string | null;
  name: string;
  short: string;
  authority: string | null;
  location: GeoPoint | null;
  coast: Coast | null;

  observedCongestionIndex: number | null;
  observedAt: string | null;
  dataStatus: DataStatus;
  dataAgeHours: number | null;
  throughputTonnes: number | null;
  vesselCalls: number | null;
  anchorageCount: number | null;
  queuePressure: number | null;
  capacityPressure: number | null;
  anomalyScore: number | null;
  weatherImpact: number | null;
  aisConfidence: number | null;
  dataQuality: number | null;
  utilization: number | null;
  congestionHistory: HistoryPoint[];

  /**
   * Specialist signals. Present on the observed port-state payload (and hence
   * on the intelligence chain); the radar's port list carries the subset it
   * needs, so these stay optional rather than being defaulted to zero.
   */
  berthPressure?: number | null;
  arrivalClustering?: number | null;
  queueMomentum?: number | null;
  throughputStress?: number | null;
  disruptionPressure?: number | null;
  disruptionExposure?: number | null;
  weatherPersistence?: number | null;
  weatherShock?: number | null;
  specialistStress?: number | null;
  turnaroundPressure?: number | null;
  vesselDensity?: number | null;
  capacityIndex?: number | null;
  berthCount?: number | null;

  congestionIndex: number;
  congestion: number;
  peakCongestionIndex: number;
  peakDay: number;
  delayHours: number;
  forecastQ10: number | null;
  forecastQ90: number | null;
  modelDisagreement: number | null;
  confidence: number;
  model: string | null;
  forecastOrigin: string | null;
  forecastHorizonDays: number;

  regime: string;
  regimeConfidence: number | null;
  transitionRisk24h: number | null;
  expectedRemainingDays: number | null;
  recommendedAction: string | null;
  actionTitle: string | null;
  priorityScore: number | null;

  risk: RiskLevel;
  dataSource: string;
}

/* ------------------------------------------------------------ forecast ---- */

export interface ForecastPoint {
  portCode: string;
  day: number;
  targetDate: string | null;
  originDate: string | null;
  dateLabel: string;
  congestionIndex: number;
  q10: number;
  q50: number;
  q90: number;
  intervalWidth: number;
  delayHoursP50: number;
  throughputTonnes: number | null;
  weatherProbability: number;
  severity: "LOW" | "MOD" | "HIGH" | "SEVERE";
  confidence: number;
  source: string;
  modelDisagreement: number | null;
  tftWeight: number | null;
  gbmWeight: number | null;
  conformalOffset: number | null;
  dataStatus: DataStatus;
  dataAgeHours: number | null;
}

export interface RegimeState {
  portCode: string;
  state: string;
  probabilities: { normal: number; congested: number; severe: number };
  daysInState: number;
  expectedRemainingDays: number;
  transitionRisk24h: number;
  confidence: number;
  observedAt: string | null;
  dataStatus: DataStatus;
  dataAgeHours: number | null;
  source: string;
  history: Array<{
    date: string | null;
    state: string;
    severe: number | null;
    congested: number | null;
  }>;
}

export interface DecisionDriver {
  factor: string;
  contribution: number | null;
}

export interface Decision {
  id: string;
  portCode: string;
  severity: string;
  title: string;
  action: string;
  actions: string[];
  target: string;
  horizonDay: number;
  targetDate: string | null;
  rationale: string;
  topDrivers: DecisionDriver[];
  expectedImpact: string;
  expectedDelaySavedHours: number | null;
  alternativeAction: string;
  uncertainty: number | null;
  congestionProbability: number | null;
  portEntryRisk: string;
  priorityScore: number;
  confidence: number;
  originDate: string | null;
  source: string;
  schedule: Array<{
    horizonDay: number;
    targetDate: string | null;
    action: string;
    priority: number;
    congestionProbability: number | null;
  }>;
}

/* --------------------------------------------------- model intelligence --- */

export interface PipelineNode {
  key: string;
  name: string;
  kind?: "expert" | "model" | "decision";
  inputSignal: string;
  score: number | null;
  confidence: number | null;
  effectOnForecast: string;
  observedAt: string | null;
  rows: number;
  available: boolean;
  artefact: string;
  dataStatus: DataStatus;
  ageHours: number | null;
  modelCard?: string;
  disagreement?: number | null;
  benchmarkLeader?: string | null;
  coverage80?: number | null;
}

export interface BenchmarkRow {
  model: string;
  n: number;
  /** Null where the model produced no prediction for this cell. */
  mae: number | null;
  rmse: number | null;
  mape_pct: number | null;
  pinball_q10?: number | null;
  pinball_q50?: number | null;
  pinball_q90?: number | null;
  coverage_80pct?: number | null;
  interval_width?: number | null;
  calibration_error?: number | null;
  horizon_day?: number;
  port_id?: string;
  regime?: string;
}

export interface CalibrationEntry {
  nominal: number;
  empirical: number;
  error: number;
  meanWidth: number;
}

export interface Benchmark {
  available: boolean;
  reason?: string;
  version?: string;
  generatedAt?: string;
  target?: string;
  horizonDays?: number;
  protocol?: string;
  trainOrigins?: number;
  summary?: {
    folds: number;
    testRows: number;
    models: string[];
    bestModel: string;
    bestMae: number | null;
    bestRmse: number | null;
    bestCoverage80: number | null;
    naiveMae: number | null;
    skillVsNaive: number | null;
    tftEvaluated: boolean;
    ensembleSecondModel: string;
    ensembleMembers?: string[];
  };
  models?: BenchmarkRow[];
  byHorizon?: BenchmarkRow[];
  byPort?: BenchmarkRow[];
  byRegime?: BenchmarkRow[];
  calibration?: {
    levels: number[];
    models: Record<string, CalibrationEntry[]>;
  };
  ensembleWeights?: {
    members: string[];
    globalWeights: Record<string, number>;
    byHorizon: Record<string, Record<string, number>>;
    byRegime?: Record<string, Record<string, number>>;
    conformalByHorizon: Record<string, number>;
    fitted: boolean;
    source: string;
    folds: number;
    generatedAt: string | null;
    secondOpinionModel: string | null;
  };
}

export interface ChainStage {
  stage: string;
  label: string;
  observedAt: string | null;
  status: DataStatus | null;
  metrics: Record<string, string | number | null>;
  confidence: number | null;
}

/**
 * The observed port state the pipeline exported, as served by the intelligence
 * chain. It is deliberately a different shape from `PortSnapshot`: this is what
 * was *measured*, with no forecast fields mixed in, so a null here means the
 * feed genuinely did not carry that value.
 */
export interface PortObservedState {
  portCode: string;
  modelId: string;
  name: string;
  short: string;
  authority: string | null;
  coast: Coast | null;
  location: GeoPoint;
  capacityIndex: number | null;
  berthCount: number | null;

  observedAt: string | null;
  dataAgeHours: number | null;
  dataStatus: DataStatus;

  congestionIndex: number | null;
  delayHours: number | null;
  throughputTonnes: number | null;
  utilization: number | null;
  queuePressure: number | null;
  turnaroundPressure: number | null;
  vesselCalls: number | null;
  vesselDensity: number | null;
  anchorageCount: number | null;
  capacityPressure: number | null;
  queueMomentum: number | null;
  throughputStress: number | null;
  anomalyScore: number | null;
  specialistStress: number | null;
  weatherImpact: number | null;
  weatherPersistence: number | null;
  weatherShock: number | null;
  arrivalClustering: number | null;
  berthPressure: number | null;
  disruptionExposure: number | null;
  disruptionPressure: number | null;
  dataQuality: number | null;
  aisConfidence: number | null;

  congestionHistory: HistoryPoint[];
}

export interface IntelligenceChain {
  portCode: string;
  name: string;
  stages: ChainStage[];
  decision: Decision | null;
  regime: RegimeState | null;
  forecast: ForecastPoint[];
  state: PortObservedState;
}

/* ------------------------------------------------------------- weather ---- */

export interface WeatherSignal {
  portCode: string;
  name: string;
  observedAt: string | null;
  windKnots: number | null;
  gustKnots: number | null;
  rainfallMm24h: number | null;
  waveHeightM: number | null;
  visibilityKm: number | null;
  seaState: string | null;
  windRisk: number | null;
  rainRisk: number | null;
  waveRisk: number | null;
  stormRisk: number | null;
  impactScore: number | null;
  confidence: number | null;
  weatherRegime: string | null;
  shockScore: number | null;
  persistenceScore: number | null;
  forwardLoad: number | null;
  forecast: Array<{ date: string | null; impact: number | null }>;
  advisory: string;
  dataSource: string;
}

export interface WeatherIntelligence {
  available: boolean;
  reason?: string;
  observedAt?: string | null;
  meanImpact?: number | null;
  meanWindRisk?: number | null;
  meanRainRisk?: number | null;
  meanWaveRisk?: number | null;
  meanStormRisk?: number | null;
  meanWindKnots?: number | null;
  meanWaveHeightM?: number | null;
  persistentPorts?: string[];
  highestImpactPort?: string | null;
  highestImpactScore?: number | null;
  portsCovered?: number;
  dataSource?: string;
}

/* ---------------------------------------------------------------- news ---- */

export interface NewsEvent {
  id: string;
  timestamp: string;
  title: string;
  source: string;
  url: string;
  tag: string;
  entity: string;
  chokepoint: string | null;
  chokepointName: string | null;
  severity: "normal" | "watch" | "high" | "severe";
  severityScore: number;
  affectedPorts: string[];
  exposure: Array<{ portCode: string; name: string; exposure: number }>;
  dataSource: string;
}

export interface AlertEvent {
  id: string;
  portCode: string;
  severity: string;
  text: string;
  action: string;
  priority: number | null;
  confidence: number | null;
  ts: string | null;
  dataSource: string;
}

export interface NewsBundle {
  events: NewsEvent[];
  alerts: AlertEvent[];
  sentiment: Array<{
    entity: string;
    mentions: number;
    riskScore: number | null;
    sentiment: number | null;
    eventSpike?: number | null;
    confidence: number | null;
  }>;
  summary: {
    totalEvents: number;
    totalAlerts: number;
    severeEvents: number;
    eventsAvailable: boolean;
    dataSource: string;
  };
}

/* -------------------------------------------------- vessels and routing --- */

export interface VesselActivity {
  portCode: string;
  name: string;
  location: GeoPoint;
  dailyPortCalls: number;
  queueBuildup: number;
  queuePressure: number;
  waitingProxy: number;
  confidence: number | null;
  observedAt: string | null;
  basis: string;
}

export interface VesselBundle {
  vessels: VesselActivity[];
  basis: string;
  observedAt: string | null;
}

export interface FeedAdapter {
  key: string;
  name: string;
  status: DataStatus;
  provider: string;
  observedAt: string | null;
  ageHours: number | null;
  confidence: number | null;
  detail: string;
  granularity: string;
}

/**
 * One vessel scored by the route optimizer.
 *
 * There is no IMO number and no position: the routing artefact carries a
 * declared call and an arrival window, not an AIS track, and the interface says
 * so rather than inventing either.
 */
export interface FleetRow {
  id: string;
  name: string;
  intendedPortCode: string | null;
  intendedPortName?: string | null;
  recommendedPortCode: string | null;
  recommendedPortName?: string | null;
  reroute: boolean;
  bestArrivalDay: number | null;
  intendedArrivalDay?: number | null;
  /** The window the operator declared for this vessel, in horizon days. */
  earliestDay?: number | null;
  latestDay?: number | null;
  candidatePortCodes?: string[];
  etaDeltaHours: number | null;
  riskDelta: number | null;
  portWaitDeltaHours: number | null;
  intendedWaitHours?: number | null;
  alternativeWaitHours?: number | null;
  intendedCongestionProbability?: number | null;
  alternativeCongestionProbability?: number | null;
  /** Optimizer cost: predicted delay + congestion penalty + travel penalty. */
  intendedCost?: number | null;
  alternativeCost?: number | null;
  extraSteamingHours?: number | null;
  bufferHours: number | null;
  diversionKm: number | null;
  recommendation: string;
  originDate: string | null;
  source: string;
}

/* ----------------------------------------------------------- scenarios ---- */

export interface ScenarioDefinition {
  key: string;
  name: string;
  desc: string;
  shockType: string;
  scope: "chokepoint" | "coast" | "national";
  defaultSeverity: number;
  chokepoint: string | null;
  affectedCoasts: string[];
  durationDays: number;
  question: string;
  analogue: string;
}

export interface ScenarioPortImpact {
  portCode: string;
  modelId: string;
  name: string;
  coast: Coast | null;
  exposure: number;
  baselineCongestion: number;
  shockCongestion: number;
  congestionDelta: number;
  baselineDelayHours: number | null;
  shockDelayHours: number | null;
  delayDeltaHours: number | null;
  throughputDeltaPct: number | null;
  baselineCongestionProbability: number;
  shockCongestionProbability: number;
  probabilityDelta: number;
  extraSteamingDays: number;
  riskLevel: OperationalRiskLevel;
  impactScore: number;
  confidence: number;
  modelDisagreement: number;
}

export interface ScenarioRecommendation {
  available: boolean;
  reason?: string;
  id?: string;
  portCode?: string | null;
  severity?: string;
  action?: string;
  title?: string;
  target?: string;
  instruction?: string;
  rationale?: string;
  topDrivers?: string;
  expectedImpact?: string;
  expectedDelaySavedHours?: number;
  alternativeAction?: string;
  confidence?: number;
  uncertainty?: number;
  changedFromBaseline?: boolean;
  baselineAction?: string | null;
  actionMix?: Record<string, number>;
}

export interface PropagationStep {
  step: string;
  label: string;
  detail: string;
  value: string;
}

export interface ScenarioResult {
  scenarioKey: string;
  scenarioName: string;
  description: string;
  question: string;
  analogue: string;
  shockType: string;
  scope: string;
  chokepoint: string | null;
  intensity: number;
  severity: number;
  durationDays: number;
  runId: number;
  forecastOrigin: string | null;
  baselineModel: string;
  horizonDays: number;
  congestionDelta: number;
  delayDeltaHours: number;
  throughputDelta: number;
  freightDelta: number;
  oilDelta: number;
  riskLevel: OperationalRiskLevel;
  confidence: number;
  affectedPorts: ScenarioPortImpact[];
  routeImpacts: Array<{
    name: string;
    coast: string;
    ports: string[];
    delayDeltaHours: number | null;
    congestionDelta: number;
    riskLevel: OperationalRiskLevel;
    inScope: boolean;
  }>;
  chokepointImpacts: Array<{
    code: string;
    name: string;
    location: GeoPoint;
    riskLevel: string;
    isShocked: boolean;
    rerouteDays: number;
    hasAlternative: boolean;
  }>;
  recommendation: ScenarioRecommendation;
  propagation: PropagationStep[];
  method: string;
  summary?: string;
}

export interface PortRegistryEntry {
  modelId: string;
  code: string;
  name: string;
  short: string;
  authority: string;
  location: GeoPoint;
  coast: Coast;
  capacityIndex: number;
  berthCount: number;
  connectivityScore: number;
}
