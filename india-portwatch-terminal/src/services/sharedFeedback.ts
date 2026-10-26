export interface FeedbackClaim {
  id: string;
  kind: string;
  wording: string;
  value?: number | boolean | null;
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
    predicate?: string;
    precision?: string;
    reportedPeriod?:
      string | { from?: string; through?: string; precision?: string };
  };
  inputs: Record<string, unknown>[];
  sourceQuality?: {
    sourceProductRetained: boolean;
    articleBodyRetained: boolean;
    closureInference: string;
    timestampMeaning: string;
    originalAccess?: string;
    redistributionPolicy?: string;
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
  publishedAt?: string | null;
  publishedDate?: string | null;
  publicationPrecision?: string;
  newsIdentity?: {
    targetId?: string | null;
    eventFamilyId?: string | null;
    lineageId?: string | null;
    reportId?: string | null;
    revisionId?: string | null;
    [key: string]: unknown;
  };
  economicInspection?: EconomicInspection;
  newsInspection?: {
    currentAssessment: FeedbackAssessment | null;
    evidence: FeedbackEvidence[];
    exclusionReasons: string[];
    assessmentHistory: FeedbackAssessment[];
    asOf: string;
  };
}
export interface FeedbackEvidence {
  id?: string;
  source?: string;
  responseSha256?: string;
  firstAvailableAt?: string | null;
  publishedAt?: string | null;
  publishedDate?: string | null;
  publicationPrecision?: string;
  sourceLineageId?: string;
  recordKind?: string;
  sourceRole?: string;
  [key: string]: unknown;
}
export interface EconomicInspection {
  status: string;
  reason: string;
  predicted: number | null;
  inputQuote: {
    value: number | null;
    observationDate: string | null;
    ageDays: number | null;
    firstAvailableAt: string | null;
    responseSha256?: string;
  } | null;
  targetDate: string | null;
  issuedAt: string;
  matchedObservation: {
    value: number | null;
    observationDate: string | null;
    firstAvailableAt: string | null;
    evidenceId?: string;
    responseSha256?: string;
  } | null;
  error: number | null;
  absoluteError: number | null;
  assessmentAvailableAt?: string | null;
  scoringVintage?: string | null;
  revisionState?: string;
  exclusions?: Array<string | { reason?: string; [key: string]: unknown }>;
  exclusionReasons?: string[];
  selectionPolicy?: string;
  expectedRelease?: string | Record<string, unknown> | null;
  revisions?: unknown[];
  legacyStoredScore?: unknown;
  eligibleForReliability?: boolean;
}
export interface FeedbackAssessment {
  id?: string;
  verdict: string;
  applicability: string;
  reason: string;
  evidenceIds?: string[];
  availableAt?: string | null;
  createdAt?: string;
  assessedAt?: string;
  verificationMode?: string;
  decisiveEvidence?: FeedbackEvidence[];
  exclusions?: string[];
  exclusionReasons?: string[];
  independentReportingConfirmations?: number;
  [key: string]: unknown;
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
  dataset?: {
    scope: string;
    asOf: string;
    totalClaims: number;
    filteredClaims: number;
    offset: number;
    limit: number;
    returnedClaims: number;
    hasMore: boolean;
    filter: string;
    selectedClaimId?: string | null;
  };
  economicSummary?: {
    retainedObservations: number;
    independentForecastTargets: number;
    forecastVintages: number;
    eligibleMatches: number;
    unresolvedTargets: number;
    excludedTargets: number;
    retrospectiveObservations?: number;
    historyOnlyObservationDates?: number;
    independentObservationDates?: number;
    collector?: {
      lastCheck?: { status: string; checkedAt: string; reason?: string } | null;
      lastSuccessfulReceiptAt?: string | null;
      lastSuccessfulFetchAt?: string | null;
      latestObservationDate?: string | null;
      observationAgeCalendarDays?: number | null;
    };
    metrics?: Array<{
      context: string[] | string;
      independentTargets: number;
      bias: number | null;
      meanAbsoluteError: number | null;
      targetFrom?: string | null;
      targetThrough?: string | null;
      status: string;
      unit: string;
      [key: string]: unknown;
    }>;
    [key: string]: unknown;
  };
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
    [key: string]: unknown;
  };
}
