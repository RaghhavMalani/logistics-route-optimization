/** Origin, availability and execution are independent dimensions. */
export type ValueOrigin =
  | "OFFICIAL_REPORT"
  | "REPORTED_EVENT"
  | "TRANSPONDER_OBSERVATION"
  | "PROVIDER_FORECAST"
  | "REANALYSIS"
  | "DERIVED_METRIC"
  | "OPERATOR_DECLARATION"
  | "SIMULATION"
  | "REFERENCE"
  | "UNKNOWN";
export type DataAvailability =
  | "CURRENT"
  | "LATEST_AVAILABLE"
  | "CACHED"
  | "STALE"
  | "HISTORICAL"
  | "CONNECTING"
  | "UNAVAILABLE"
  | "UNKNOWN";
export type ExecutionKind =
  | "DEMO_WORKFLOW"
  | "SIMULATED_OUTCOME"
  | "REPORTED_CONTEXT"
  | "CONFIRMED_SCOPED_OUTCOME"
  | "COLLECTING"
  | "SHADOW"
  | "REJECTED"
  | "UNKNOWN";
export interface DataTruth {
  origin: ValueOrigin;
  freshness: DataAvailability;
  execution?: ExecutionKind;
  provider?: string;
  product?: string;
  source?: string;
  firstAvailableAt?: string | null;
  lastSuccessfulCheckAt?: string | null;
  publishedAt?: string | null;
  timePrecision?: string | null;
  sha256?: string | null;
  unit?: string;
  geography?: string;
  limit?: string;
}
