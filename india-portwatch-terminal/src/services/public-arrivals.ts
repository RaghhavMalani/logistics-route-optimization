export interface PublicRecord {
  recordId: string;
  kind: string;
  vesselName: string;
  loa: number | null;
  beam: number | null;
  draft: number | null;
  berthRef: string | null;
  etaAt: string | null;
  arrivalAt: string | null;
  berthAt: string | null;
  rawTimestamps: Record<string, string>;
  flags: string[];
  page: number;
}
export interface PublicCase extends PublicRecord {
  caseId: string;
  snapshotId: string;
  frozenAt: string;
  status: string;
  exclusions: string[];
  berthEvidence?: Array<{
    snapshotId: string;
    recordId: string;
    berthAt: string;
    berthRef: string | null;
    availableAt: string;
    rawTimestamps: Record<string, string>;
    page: number;
  }>;
  outcome: null | {
    arrivalAt: string;
    arrivalAvailableAt: string;
    arrivalSnapshotId: string;
    arrivalErrorHours: number;
    berthAt: string | null;
    berthAvailableAt: string | null;
    berthSnapshotId: string | null;
    berthRef: string | null;
    waitingHours: number | null;
  };
}
export interface PublicWorkspace {
  portCode: string;
  asOf: string;
  timezoneNote: string;
  collection: {
    schedulerRunning: boolean | null;
    lastSuccessfulCollectionAt: string | null;
    lastRun: null | { startedAt: string; finishedAt: string; errors: string[] };
    backendJob: null | {
      expiresAt: string | null;
      state: string;
      job: {
        state: string;
        nextAttemptAt: string | null;
        eligibility: string | null;
      };
    };
  };
  structuredVessels: {
    enabled: boolean;
    configurationReason: string | null;
    coverage: string;
    statement: string;
    lastCheckAt: string | null;
    lastErrors: string[];
    records: Array<{
      recordId: string;
      kind: string;
      vesselName: string | null;
      mmsi: string | null;
      imo: string | null;
      event: string;
      eventAt: string | null;
      aisEtaAt: string | null;
      flags: string[];
    }>;
    snapshots: Array<{
      snapshotId: string;
      kind: string;
      firstSeenAt: string;
      sha256: string;
    }>;
  };
  counts: Record<string, number>;
  freshness: {
    lastCollectionAt: string | null;
    latestReportDate: string | null;
    lastCheckAt: string | null;
    lastCheck: { errors: string[] } | null;
  };
  cases: PublicCase[];
  unassignedCases: number;
  cohorts: Array<{
    cohortId: string;
    createdAt: string;
    createdBy: string;
    enrollmentStartAt: string;
    enrollmentEndAt: string;
    status: "ENROLLING" | "CLOSED";
    caseIds: string[];
    protocol: string;
  }>;
  snapshots: Array<{
    snapshotId: string;
    sha256: string;
    sourceUrl: string;
    firstSeenAt: string;
    reportDate: string | null;
    kind: string;
    parserVersion: string;
    records: PublicRecord[];
  }>;
  issues: Array<{
    snapshotId: string;
    code: string;
    raw: string;
    page?: number;
  }>;
  excludedRecords: Array<{
    recordId: string;
    vesselName: string;
    flags: string[];
  }>;
  evaluationReason: string;
  benchmarks: Array<{
    cohortId: string;
    statement: string;
    targets: Record<string, unknown>;
  }>;
}
