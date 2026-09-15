/**
 * The decision intelligence engine's payloads.
 *
 * Mirrors `src/portwatch_os/decision/model.py` field for field. Nothing on
 * the client computes a consequence: every objective is a `Measure` the
 * engine produced, with its unit, confidence and basis -- or the reason it
 * could not be produced. `available: false` is a first-class state and is
 * rendered as such; it is never coerced to zero.
 */

export type DecisionDomain =
  "VESSEL_ROUTING" | "PORT_BERTHING" | "CARGO_CONNECTION";

export type DecisionActorRole =
  | "SHIPPING_COMPANY"
  | "PORT_AUTHORITY"
  | "VESSEL_OPERATOR"
  | "TERMINAL_OPERATOR"
  | "NATIONAL_ADMIN";

export type AvailabilityStatus =
  "AVAILABLE" | "UNAVAILABLE" | "UNSUPPORTED" | "INSUFFICIENT_DATA";
export type OptionStatus = "FEASIBLE" | "REJECTED" | "NOT_EVALUATED";
export type CriticVerdict = "PASS" | "PASS_WITH_WARNINGS" | "REJECT";
export type WorkflowState =
  | "COMPUTED"
  | "REVIEWED"
  | "APPROVED"
  | "PROPOSED"
  | "ISSUED"
  | "ACCEPTED"
  | "DECLINED"
  | "OBSERVED";

export interface Measure {
  value: number | null;
  unit: string;
  confidence: number | null;
  basis: string;
  available: boolean;
  unknownBecause: string | null;
  attrs: Record<string, unknown>;
}

export interface DecisionObjective {
  key: string;
  label: string;
  unit: string;
  direction: "min" | "max";
  description: string;
}

export interface ConstraintResult {
  key: string;
  label: string;
  passed: boolean;
  hard: boolean;
  detail: string;
  basis: string;
}

export interface CriticCheck {
  name: string;
  passed: boolean;
  severity: "blocking" | "warning";
  detail: string;
  basis: string;
  remedy: string | null;
}

export interface CriticReport {
  verdict: CriticVerdict;
  checks: CriticCheck[];
  failed: string[];
  reasons: string[];
  warnings: CriticCheck[];
  blocking: CriticCheck[];
  ranAt: string;
}

export interface MoneyValue {
  amount: number;
  currency: string;
}

export interface CostComponent {
  key: string;
  label: string;
  state: "KNOWN" | "ZERO" | "UNKNOWN";
  money: MoneyValue | null;
  quantity: { value: number; unit: string } | null;
  rate: Record<string, unknown> | null;
  basis: string;
  reason: string;
  isAssumption: boolean;
  sourceType: string | null;
  driver: string | null;
}

export interface FinancialEvaluation {
  currency: string;
  components: CostComponent[];
  total: MoneyValue | null;
  partialTotal: MoneyValue | null;
  complete: boolean;
  unknown: Array<{ key: string; label: string; reason: string }>;
  assumption: boolean;
  label: "ASSUMPTION" | "PUBLIC_TARIFF" | null;
  sourceTypes: string[];
  fxUsed: unknown[];
  range: Record<string, unknown> | null;
  notes: string[];
}

export interface DecisionConsequence {
  node: string;
  kind: string;
  label: string;
  quantities?: Record<
    string,
    {
      value: number;
      unit: string;
      confidence: number;
      attrs: Record<string, unknown>;
    }
  >;
  steps?: unknown[];
  notes?: string[];
  metrics?: Record<string, unknown>;
  connection?: Record<string, unknown>;
}

export interface DecisionEvaluation {
  objectives: Record<string, Measure>;
  consequences: DecisionConsequence[];
  derived: Record<string, unknown>;
  financial: FinancialEvaluation | null;
  branchId: string | null;
  notes: string[];
  computedAt: string | null;
  weakestConfidence: number | null;
}

export interface TimelineMark {
  kind:
    | "arrival"
    | "chokepoint"
    | "deadline"
    | "claim_lapses"
    | "weather"
    | "ready"
    | "sailing";
  subject: string;
  hours: number;
  waveM?: number | null;
}

export interface DecisionOption {
  optionId: string;
  action: string;
  label: string;
  actor: DecisionActorRole;
  params: Record<string, unknown>;
  availability: { status: AvailabilityStatus; reason: string };
  constraints: ConstraintResult[];
  rejectedBy: ConstraintResult[];
  status: OptionStatus;
  feasible: boolean;
  isBaseline: boolean;
  evaluation: DecisionEvaluation | null;
  assumptions: Array<Record<string, unknown>>;
  provenance: Record<string, unknown> & {
    closesInHours?: number | null;
    branchId?: string;
  };
  critic: CriticReport | null;
  /** [lat, lon] pairs; non-navigational. */
  geometry: Array<[number, number]> | null;
  timeline: TimelineMark[];
}

export interface DecisionFrontier {
  objectives: string[];
  nondominated: string[];
  dominated: Record<string, string>;
  incomparable: Record<string, string[]>;
  picks: Record<string, string>;
}

export type RecommendationKind =
  "ACT" | "KEEP_CURRENT_PLAN" | "WAIT_FOR_MORE_INFORMATION";

export type ReversibilityClass =
  "OPEN" | "HIGH" | "UNTIL_BRANCH" | "PARTIAL" | "IRREVERSIBLE";

export interface StressScenario {
  label: "FIZZLE" | "SHORT" | "BASE" | "LONG";
  multiplier: number | null;
  description: string;
  queueModel: string;
  closureFromNowHours: number | null;
  window: {
    blockedFrom: string;
    reopenedAt: string;
    clearedAt: string;
    closureHours: number;
    drainHours: number;
  };
}

export interface RobustCell {
  delay: number;
  regret: number;
  how: string;
}

export interface BreakEven {
  available: boolean;
  reason?: string;
  winsFromHours?: number | null;
  winsUntilHours?: number | null;
  winningShare?: number;
  gridSpanHours?: number;
  gridStepHours?: number;
  statement?: string;
  curve?: Array<{
    closureFromNowHours: number;
    option: number;
    baseline: number;
  }>;
}

export interface RobustSummary {
  worstCaseRegret: number;
  worstCaseScenario: string;
  meanRegret: number;
  meanRegretBasis: string;
  wins: number;
  winningScenarios: string[];
  scenarios: number;
  baselineAdvantageHours: Record<string, number>;
  meanBaselineAdvantageHours: number | null;
  robustnessMargin: number | null;
  reversibility: {
    class: ReversibilityClass;
    closesInHours: number | null;
    detail: string;
  };
  breakEven: BreakEven | null;
}

export interface GateCheck {
  name: string;
  passed: boolean;
  blocking: boolean;
  detail: string;
  basis: string;
}

/**
 * The robust assessment: every candidate under every stress horizon, the
 * minimax pick, the gate the intervention had to clear, and what the operator
 * is told to do next. `applicable: false` means the domain has no
 * duration-uncertainty model (port, cargo) and the expected ranking decided.
 */
export interface RobustAssessment {
  applicable: boolean;
  policy: string;
  kind: RecommendationKind;
  optionId: string | null;
  contenderId: string | null;
  provisionalOptionId: string | null;
  scenarios: StressScenario[];
  table: Record<string, Record<string, RobustCell>>;
  summary: Record<string, RobustSummary>;
  picks: {
    EXPECTED_BEST: string | null;
    ROBUST_BEST: string | null;
    LOWEST_WORST_CASE_REGRET: string | null;
  };
  checks: GateCheck[];
  failedBlocking: string[];
  durationConfidence: {
    label: string;
    basis: string;
    claimProbabilityCalibrated?: boolean;
    claimConfidence?: number | null;
  };
  information: {
    scenarioSensitive?: boolean;
    bestByScenario?: Record<string, string>;
    nextObservationHours?: number;
    nextObservationBasis?: string;
    informationValueHoursUpperBound?: number;
    informationValueBasis?: string;
    reevaluateInHours?: number;
    branchPointInHours?: number | null;
  };
  queueModel: { name: string; drainFraction: number; basis: string } & Record<
    string,
    unknown
  >;
  notModelled: Record<string, string>;
  why: string;
  statement: string;
  notes: string[];
  tolerance: { hours: number; basis: string };
}

export interface DecisionRecommendation {
  optionId: string;
  actor: DecisionActorRole;
  /** ACT names an intervention; the other two keep the plan for now. */
  kind: RecommendationKind;
  /** The policy that produced it: `balanced-v1` or `robust-v1`. */
  policy: string;
  /** For WAIT: the option to take if the claim still stands at re-evaluation. */
  provisionalOptionId: string | null;
  rankingBasis: {
    method?: string;
    weights?: Record<string, number>;
    objectivesUsed?: string[];
    objectivesDropped?: Record<string, string>;
    score?: { score: number; terms: Record<string, number> } | null;
    order?: string[];
    expectedBest?: string | null;
  };
  againstBaseline: Record<
    string,
    {
      unit: string;
      option: number | null;
      baseline: number | null;
      delta: number | null;
      better: boolean | null;
      unknownBecause?: string | null;
    }
  >;
  critic: CriticReport | null;
  expectedAvoidableCost: Record<string, unknown> & {
    available: boolean;
    reason?: string;
  };
  robustness: RobustAssessment | null;
  why: string;
  statement: string;
}

export interface CatalogueRow {
  kind: string;
  label: string;
  domain: DecisionDomain;
  actors: DecisionActorRole[];
  requires: string[];
  simulator: string | null;
  description: string;
  baseline: boolean;
  availability: { status: AvailabilityStatus; reason: string };
  evaluatedFor?: DecisionActorRole;
  requiresAdvisory?: boolean;
  mechanism?: string;
}

export interface WorkflowStep {
  at: string;
  state: WorkflowState;
  actor: string;
  note?: string;
  optionId?: string | null;
  actualAction?: string;
  observed?: Record<string, unknown>;
}

/** The evidence block, with the fields the client reads named and the rest open. */
export interface DecisionEvidence {
  position?: { lat: number; lon: number; basis: string; observed: boolean };
  exposure?: { attrs?: Record<string, unknown> } & Record<string, unknown>;
  routes?: {
    laneCode?: string;
    portCode?: string;
    detourNm?: number | null;
  } & Record<string, unknown>;
  frontierObjectives?: string[];
  replay?: { missionId: string; clock: string } & Record<string, unknown>;
  execution?: { by?: string; requestedBy?: string; mechanism?: string };
  ranking?: Record<string, unknown>;
  marine?: Record<string, unknown>;
  outcome?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface DecisionProblem {
  decisionId: string;
  createdAt: string;
  domain: DecisionDomain;
  worldRevision: Record<string, unknown>;
  worldStateId: string;
  subject: { type: string; id: string; label: string };
  actor: {
    role: DecisionActorRole;
    organisation: string | null;
    portCode: string | null;
    vesselIds: string[];
  };
  attentionItemId: string | null;
  cascadeId: string | null;
  decisionDeadline: string | null;
  decisionWindowHours: number | null;
  at: string | null;
  objectives: DecisionObjective[];
  hardConstraints: string[];
  softConstraints: string[];
  availableActions: CatalogueRow[];
  baselineOptionId: string | null;
  options: DecisionOption[];
  frontier: DecisionFrontier | null;
  recommendation: DecisionRecommendation | null;
  evidence: DecisionEvidence;
  headline: string;
  doNothingStatement: string;
  workflow: WorkflowState;
  workflowHistory: WorkflowStep[];
  humanChoice: string | null;
  notes: string[];
  counts: { options: number; feasible: number; rejected: number };
}

export interface DecisionSummary extends Omit<DecisionProblem, "options"> {
  options?: DecisionOption[];
}

export interface DecisionList {
  problems: DecisionSummary[];
  total: number;
}

export interface DecisionHandoff {
  decision: DecisionSummary;
  advisories: Array<
    Record<string, unknown> & {
      advisoryId: string;
      state: string;
      kind: string;
    }
  >;
}

export interface DecisionLearning {
  available: boolean;
  count: number;
  resolved: number;
  agreementRate?: number | null;
  rankingAccuracy?: number | null;
  meanRegret?: number | null;
  meanReward?: number | null;
  constraintViolations?: number;
  predictionError?: Record<
    string,
    { meanAbsoluteError: number; bias: number; count: number; unit: string }
  >;
  calibration?: Record<string, { meanAbsoluteError: number; count: number }>;
  problems?: Array<Record<string, unknown>>;
  method?: string;
  note?: string;
}

/* ----------------------------------------------------------------- finance -- */

export interface CostRateView {
  primitive: string;
  label: string;
  value: number;
  currency: string;
  unit: string;
  scope: string;
  vesselStatus: string | null;
  vesselType: string | null;
  tier: {
    minGrt: number | null;
    maxGrt: number | null;
    baseAmount: number | null;
  } | null;
  validFrom: string | null;
  validTo: string | null;
  source: string;
  sourceType: string;
  isAssumption: boolean;
  confidence: number;
  provenance: Record<string, unknown>;
}

export interface CostSchedule {
  scheduleId: string;
  title: string;
  sourceType: string;
  scope: string;
  rates: CostRateView[];
  provenance: Record<string, unknown>;
  reuse: string;
  notes: string[];
  validFrom: string | null;
  validTo: string | null;
}

export interface FinanceBasis {
  rates: CostRateView[];
  schedules: CostSchedule[];
  coverage: Record<
    string,
    {
      label: string;
      per: string;
      available: boolean;
      sourceType: string | null;
      source: string | null;
      isAssumption: boolean;
      reason: string;
    }
  >;
  primitives: Array<{
    key: string;
    label: string;
    per: string;
    description: string;
  }>;
  sourceTypes: string[];
  note: string;
  scope?: string | null;
  currency?: string;
  fx?: { observations: unknown[] };
  investigated?: Array<Record<string, unknown>>;
}

export interface FinanceTariffs {
  schedules: CostSchedule[];
  investigated: Array<Record<string, unknown>>;
  label: string;
  note: string;
}

/* ---------------------------------------------------------------- missions -- */

export interface MissionSummary {
  missionId: string;
  name: string;
  startTimestamp: string;
  /** The strait the event acts on, or null for an event that acts on ports. */
  chokepoint: string | null;
  ports?: string[];
  subjectKind?: "chokepoint" | "port";
  eventCategory?: string;
  description: string;
  sources: number;
  observations: number;
  fleet: number;
  evaluationWindowHours: number;
}

export interface MissionObservation {
  observedAt: string;
  kind: string;
  text: string;
  sourceId: string;
  claim: Record<string, unknown>;
  timeUnstated: boolean;
}

export interface MissionSource {
  sourceId: string;
  name: string;
  url: string;
  kind: string;
  retrievedAt: string;
  note: string;
}

export interface MissionReplayState {
  missionId: string;
  name: string;
  description: string;
  startTimestamp: string;
  chokepoint: string;
  eventCategory: string;
  eventTitle: string;
  claimHorizonHours: number;
  evaluationWindowHours: number;
  sources: MissionSource[];
  clock: string;
  visible: MissionObservation[];
  hiddenCount: number;
  hidden: MissionObservation[] | null;
  fleet: Array<{
    vesselId: string;
    name: string;
    laneCode: string;
    destinationPort: string;
    hoursToChokepointAtStart: Record<string, number>;
    serviceSpeedKn: number;
    illustrative: boolean;
    note: string;
  }>;
  outcome: MissionOutcome | null;
  revealed: boolean;
  disclaimer: string;
  replayId?: string;
  elapsedHours?: number;
  decisions?: Record<string, string>;
  choices?: Record<string, string>;
  /** Where the chart draws the mission at the clock; derived, with its basis. */
  geography?: {
    /** The subject the chart centres on: the strait, or the event's own position for a port mission. */
    chokepoint: { code: string; lat: number | null; lon: number | null };
    subjectKind?: "chokepoint" | "port";
    ports?: Array<{
      code: string;
      name: string;
      lat: number | null;
      lon: number | null;
    }>;
    hulls: Array<{
      vesselId: string;
      name: string;
      lat: number | null;
      lon: number | null;
      basis: string;
      /** The remaining modelled lane, as [lat, lon] pairs. */
      lane: Array<[number, number]>;
      destinationPort: string;
      hoursToChokepoint: Record<string, number>;
      hoursToDestination?: number | null;
    }>;
    disclaimer: string;
  };
}

export interface MissionOutcome {
  reopenedAt: string;
  blockedFrom: string;
  blockedHours: number;
  backlogClearedOn: string;
  backlogClearedBound: string;
  shipsWaitingPeak: number | null;
  shipsWaitingSourceId: string | null;
  summary: string;
  sources: string[];
}

export interface MissionScorecard {
  missionId: string;
  decisionId: string;
  subject: string;
  clock: string;
  knew: Record<string, unknown>;
  predicted: {
    baselineRisk: number | null;
    baselineExpectedShiftHours: number | null;
    options: Record<string, number | null>;
  };
  recommended: {
    optionId: string | null;
    critic: string | null;
    statement: string | null;
  };
  selected: string | null;
  happened: MissionOutcome;
  forecastError: {
    claimHorizonHours: number;
    blockedHours: number;
    persistenceErrorHours: number;
    closedOnArrival: boolean | null;
    brier: number | null;
  };
  realised: Record<
    string,
    {
      hours: number;
      how: string;
      predicted: number | null;
      status: string;
      label: string;
    }
  >;
  realisedBest: string | null;
  regretHours: number | null;
  rankingCorrect: boolean | null;
  wouldAnotherOptionHaveBeenBetter: boolean | null;
  learned: string[];
  realisedModel: string;
}

export interface MissionReveal {
  mission: MissionReplayState;
  scorecards: Record<string, MissionScorecard>;
}
