export interface FeedbackClaim {
  id: string;
  kind: string;
  wording: string;
  value?: number | boolean;
  unit?: string;
  entity: string;
  geography: string;
  originAt: string;
  firstAvailableAt: string;
  source: string;
  sourceVersion: string;
  responseSha256?: string;
  baselineAgeDays?: number;
  baselineStatus?: string;
  eventKey: string;
  target: {
    kind: string;
    at?: string;
    date?: string;
    from?: string;
    through?: string;
    series?: string;
    reportedPeriod?:
      string | { from?: string; through?: string; precision?: string };
  };
  inputs: Record<string, unknown>[];
  sourceQuality?: {
    sourceProductRetained: boolean;
    articleBodyRetained: boolean;
    closureInference: string;
    timestampMeaning: string;
  } | null;
  verification?: FeedbackAssessment | null;
  score?: {
    status: string;
    observed: number | null;
    error: number | null;
    absoluteError: number | null;
    availableAt: string | null;
  } | null;
  outcomes?: unknown[];
}
export interface FeedbackAssessment {
  id: string;
  verdict: string;
  applicability: string;
  reason: string;
}
export interface FeedbackVersion {
  id: string;
  status: string;
  consumedWeight: number;
  errorConvention: string;
  slices: {
    context: string[];
    independentTargets: number;
    bias: number;
    meanAbsoluteError: number;
    status: string;
  }[];
}
export interface FeedbackConsumption {
  id: string;
  contractVersion: string;
  inputs: { claim: FeedbackClaim; assessment: FeedbackAssessment | null }[];
  reliabilityVersion: FeedbackVersion;
  effect: string;
}
export interface FeedbackInspection {
  contractVersion: string;
  claims: FeedbackClaim[];
  reliability: FeedbackVersion;
  newsIndependentEvents: number;
  newsSourceReports: number;
  note: string;
  newsAggregation?: {
    contractVersion: string;
    policy: string;
    asOf: string;
    summary: {
      eventCount: number;
      independentTargets: number;
      eligibleIndependentTargets: number;
      resolvedIndependentTargets: number;
      pendingIndependentTargets: number;
      reportCount: number;
      revisionCount: number;
      excludedTargetCount: number;
      ambiguousClaimCount: number;
    };
    targets: {
      eventId: string;
      targetId: string;
      lineageId: string;
      entity: string;
      kind: string;
      status: string;
      verdict: string;
      applicability: string;
      reportCount: number;
      revisionCount: number;
      activeClaimIds: string[];
      supersededClaimIds: string[];
      exclusionReasons: string[];
    }[];
    exclusions: {
      claimIds: string[];
      targetId: string | null;
      reason: string;
    }[];
  };
  collector?: {
    status: string;
    ranAt?: string;
    failures: { source: string; reason: string }[];
  };
}
