import { z } from "zod";

/** Semantic role of a product's time coverage, separate from fetch freshness. */
export const SourceTemporalRoleSchema = z.enum([
  "CURRENT",
  "HISTORICAL",
  "FORECAST",
  "MIXED",
  "UNKNOWN",
]);
export type SourceTemporalRole = z.infer<typeof SourceTemporalRoleSchema>;

export const SourceValueKindSchema = z.enum([
  "OBSERVED",
  "FORECAST",
  "DERIVED",
  "ASSUMED",
  "SIMULATED",
  "UNKNOWN",
]);
export type SourceValueKind = z.infer<typeof SourceValueKindSchema>;

export const SourceOperationalUseSchema = z.enum([
  "CONTEXT_ONLY",
  "CALCULATION_INPUT",
  "SCENARIO_ASSUMPTION",
  "REVIEWED_OUTCOME",
  "UNKNOWN",
]);
export type SourceOperationalUse = z.infer<typeof SourceOperationalUseSchema>;

function validDatePart(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return false;
  const [, yearText, monthText, dayText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

const dateValue = z.string().refine((value) => {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return validDatePart(value);
  return (
    validDatePart(value) &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(
      value,
    ) &&
    Number.isFinite(Date.parse(value))
  );
}, "Expected an ISO timestamp with timezone or a valid date-only value.");
const nullableDate = dateValue.nullable();
const nullableNonNegative = z.number().finite().nonnegative().nullable();

const NonEmptyId = z.string().trim().min(1);
const nullableId = NonEmptyId.nullable();

/** Records remain separate so a successful receipt cannot masquerade as a new observation. */
export const SourceReceiptSchema = z
  .object({
    schemaVersion: z.literal(1),
    sourceProductId: nullableId,
    sourceReceiptId: nullableId,
    provider: z.string().nullable(),
    fetchedAt: nullableDate,
    checkedAt: nullableDate,
    firstAvailableAt: nullableDate,
    originalRef: z.string().nullable(),
    originalHash: z.string().nullable(),
    parserVersion: z.string().nullable(),
    parseStatus: z.enum(["ACCEPTED", "PARTIAL", "REJECTED", "UNKNOWN"]),
    issues: z.array(z.string()),
  })
  .passthrough()
  .superRefine((receipt, context) => {
    if (
      receipt.firstAvailableAt &&
      receipt.fetchedAt &&
      Date.parse(receipt.firstAvailableAt) > Date.parse(receipt.fetchedAt)
    ) {
      context.addIssue({
        code: "custom",
        path: ["firstAvailableAt"],
        message: "Cannot be later than the fetch receipt.",
      });
    }
  });
export type SourceReceiptDTO = z.infer<typeof SourceReceiptSchema>;

export const ObservationSchema = z
  .object({
    schemaVersion: z.literal(1),
    observationId: NonEmptyId,
    entityId: NonEmptyId,
    sourceReceiptId: nullableId,
    portCode: nullableId,
    variable: NonEmptyId,
    value: z.number().finite().nullable(),
    unit: z.string().nullable(),
    aggregation: z.enum([
      "INSTANT",
      "MEAN",
      "SUM",
      "MIN",
      "MAX",
      "DAILY",
      "UNKNOWN",
    ]),
    observedFrom: nullableDate,
    observedThrough: nullableDate,
    firstAvailableAt: nullableDate,
    valueKind: SourceValueKindSchema,
    quality: z.array(z.string()),
    unknownReason: z.string().nullable(),
  })
  .passthrough()
  .superRefine((observation, context) => {
    if (
      observation.observedFrom &&
      observation.observedThrough &&
      Date.parse(observation.observedFrom) >
        Date.parse(observation.observedThrough)
    ) {
      context.addIssue({
        code: "custom",
        path: ["observedFrom"],
        message: "Must not follow observedThrough.",
      });
    }
  });
export type ObservationDTO = z.infer<typeof ObservationSchema>;

export const ForecastClaimSchema = z
  .object({
    schemaVersion: z.literal(1),
    // Additive fields: targetId continues to identify the outcome being forecast.
    predictionId: nullableId.optional(),
    provider: nullableId.optional(),
    sourceProductId: nullableId.optional(),
    sourceVersion: nullableId.optional(),
    targetId: NonEmptyId,
    portCode: nullableId,
    variable: NonEmptyId,
    value: z.number().finite().nullable(),
    unit: z.string().nullable(),
    originAt: nullableDate,
    targetFrom: nullableDate,
    targetThrough: nullableDate,
    firstAvailableAt: nullableDate,
    modelVersion: z.string().nullable(),
    sourceReceiptIds: z.array(NonEmptyId),
    unknownReason: z.string().nullable(),
  })
  .passthrough()
  .superRefine((forecast, context) => {
    if (
      forecast.targetFrom &&
      forecast.targetThrough &&
      Date.parse(forecast.targetFrom) > Date.parse(forecast.targetThrough)
    ) {
      context.addIssue({
        code: "custom",
        path: ["targetFrom"],
        message: "Must not follow targetThrough.",
      });
    }
    if (
      forecast.originAt &&
      forecast.targetFrom &&
      Date.parse(forecast.originAt) > Date.parse(forecast.targetFrom)
    ) {
      context.addIssue({
        code: "custom",
        path: ["targetFrom"],
        message: "Must not precede the forecast origin.",
      });
    }
  });
export type ForecastClaimDTO = z.infer<typeof ForecastClaimSchema>;

export const FORECAST_PREDICTION_IDENTITY_VERSION = "forecast-prediction-v1";

type ForecastPredictionIdentity =
  | { ok: true; identity: string; basis: "EXPLICIT" | "COMPATIBILITY" }
  | { ok: false; reason: string };

/**
 * This presentation identity never changes existing ledger IDs. An explicit
 * predictionId is authoritative. Compatibility records need an origin instant
 * and known model/source version. Optional provider/product are retained exactly
 * as known or null; null does not infer a provider. This legacy namespace cannot
 * distinguish unreported providers and therefore quarantines conflicting claims.
 * Receipt IDs identify supporting fetches, not predictions; targetId identifies
 * the outcome. Neither the forecast value nor a later error enters identity.
 * The full versioned tuple is retained rather than a collision-prone short hash.
 */
export function forecastPredictionIdentity(
  forecast: ForecastClaimDTO,
): ForecastPredictionIdentity {
  if (forecast.predictionId) {
    return {
      ok: true,
      basis: "EXPLICIT",
      identity: JSON.stringify([
        FORECAST_PREDICTION_IDENTITY_VERSION,
        "explicit",
        forecast.predictionId,
      ]),
    };
  }
  const modelVersion = forecast.modelVersion?.trim() || null;
  const sourceVersion = forecast.sourceVersion?.trim() || null;
  const originAt = forecast.originAt;
  if (
    !originAt?.includes("T") ||
    !Number.isFinite(Date.parse(originAt)) ||
    (!modelVersion && !sourceVersion)
  ) {
    return {
      ok: false,
      reason:
        "Forecast identity is unknown: provide predictionId or an origin instant and modelVersion/sourceVersion. A target or receipt alone cannot identify a prediction.",
    };
  }
  return {
    ok: true,
    basis: "COMPATIBILITY",
    identity: JSON.stringify([
      FORECAST_PREDICTION_IDENTITY_VERSION,
      "compatibility",
      forecast.targetId,
      new Date(originAt).toISOString(),
      forecast.provider?.trim() || null,
      forecast.sourceProductId?.trim() || null,
      modelVersion,
      sourceVersion,
    ]),
  };
}

/** Canonical JSON preserves unknown input metadata without relying on key order. */
function canonicalJson(value: unknown, ancestors = new Set<object>()): string {
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "boolean")
    return JSON.stringify(value);
  if (typeof value === "number" && Number.isFinite(value))
    return JSON.stringify(value);
  if (typeof value !== "object" || ancestors.has(value))
    throw new Error("Forecast payload must be acyclic JSON data.");
  ancestors.add(value);
  try {
    if (Array.isArray(value))
      return `[${value.map((item) => canonicalJson(item, ancestors)).join(",")}]`;
    if (Object.getPrototypeOf(value) !== Object.prototype)
      throw new Error("Forecast payload must contain plain JSON objects.");
    return `{${Object.keys(value)
      .sort()
      .map(
        (key) =>
          `${JSON.stringify(key)}:${canonicalJson((value as Record<string, unknown>)[key], ancestors)}`,
      )
      .join(",")}}`;
  } finally {
    ancestors.delete(value);
  }
}

type ForecastBatchRow = {
  row: ForecastClaimDTO;
  raw: unknown;
  index: number;
};

/**
 * Receipt references form an unordered evidence set. Only their order and
 * repeated identical references are normalized. Different evidence sets or any
 * other payload difference under one prediction identity are conflicts: every
 * version is quarantined with its original payload, never first-row selected.
 */
function groupForecastRows(rows: ForecastBatchRow[]) {
  const groups = new Map<
    string,
    Array<
      ForecastBatchRow & {
        canonical: string | null;
        normalized: ForecastClaimDTO;
      }
    >
  >();
  const rejected: Array<{
    index: number;
    recordId: string;
    reason: string;
    raw: unknown;
  }> = [];
  for (const item of rows) {
    const identity = forecastPredictionIdentity(item.row);
    const id = item.row.predictionId ?? item.row.targetId;
    if (!identity.ok) {
      rejected.push({
        index: item.index,
        recordId: id,
        reason: identity.reason,
        raw: item.raw,
      });
      continue;
    }
    const normalized = {
      ...item.row,
      sourceReceiptIds: [...new Set(item.row.sourceReceiptIds)].sort(),
    };
    let canonical: string | null;
    try {
      canonical = canonicalJson(normalized);
    } catch {
      canonical = null;
    }
    const group = groups.get(identity.identity) ?? [];
    group.push({ ...item, canonical, normalized });
    groups.set(identity.identity, group);
  }
  const accepted: ForecastClaimDTO[] = [];
  for (const [identity, group] of [...groups].sort(([a], [b]) =>
    a < b ? -1 : a > b ? 1 : 0,
  )) {
    if (
      group.every((item) => item.canonical !== null) &&
      new Set(group.map((item) => item.canonical)).size === 1
    ) {
      accepted.push(group[0].normalized);
      continue;
    }
    for (const item of group.sort((a, b) =>
      (a.canonical ?? "") < (b.canonical ?? "")
        ? -1
        : (a.canonical ?? "") > (b.canonical ?? "")
          ? 1
          : 0,
    )) {
      rejected.push({
        index: item.index,
        recordId: item.row.predictionId ?? item.row.targetId,
        reason: group.some((version) => version.canonical === null)
          ? `Forecast: prediction identity ${identity} has a non-JSON payload; all versions quarantined.`
          : `Forecast: conflicting payloads for prediction identity ${identity}; all versions quarantined.`,
        raw: item.raw,
      });
    }
  }
  // Audit ordering does not decide acceptance; it too is stable on replay.
  rejected.sort((a, b) => {
    const left = `${a.recordId}\u0000${a.reason}`;
    const right = `${b.recordId}\u0000${b.reason}`;
    if (left !== right) return left < right ? -1 : 1;
    try {
      const leftRaw = canonicalJson(a.raw);
      const rightRaw = canonicalJson(b.raw);
      return leftRaw < rightRaw ? -1 : leftRaw > rightRaw ? 1 : 0;
    } catch {
      return 0;
    }
  });
  return { accepted, rejected };
}

export const EventRestrictionSchema = z
  .object({
    schemaVersion: z.literal(1),
    eventId: NonEmptyId,
    revisionId: nullableId,
    effectiveFrom: nullableDate,
    effectiveThrough: nullableDate,
    firstAvailableAt: nullableDate,
    affectedPortCodes: z.array(NonEmptyId).nullable(),
    affectedAssetIds: z.array(NonEmptyId).nullable(),
    applicability: z.enum([
      "APPLIES",
      "DOES_NOT_APPLY",
      "CONDITIONAL",
      "UNKNOWN",
    ]),
    sourceReceiptIds: z.array(NonEmptyId),
    exceptions: z.array(z.string()),
    unknownReason: z.string().nullable(),
  })
  .passthrough()
  .superRefine((event, context) => {
    if (
      event.effectiveFrom &&
      event.effectiveThrough &&
      Date.parse(event.effectiveThrough) < Date.parse(event.effectiveFrom)
    ) {
      context.addIssue({
        code: "custom",
        path: ["effectiveThrough"],
        message: "Must not precede effectiveFrom.",
      });
    }
    if (event.applicability === "UNKNOWN" && !event.unknownReason?.trim()) {
      context.addIssue({
        code: "custom",
        path: ["unknownReason"],
        message: "Unknown applicability requires an explanation.",
      });
    }
  });
export type EventRestrictionDTO = z.infer<typeof EventRestrictionSchema>;

export const DecisionBasisSchema = z
  .object({
    schemaVersion: z.literal(1),
    decisionId: NonEmptyId,
    sourceReceiptIds: z.array(NonEmptyId),
    observationEntityIds: z.array(NonEmptyId),
    forecastTargetIds: z.array(NonEmptyId),
    eventIds: z.array(NonEmptyId),
    inputVersions: z.array(
      z.object({
        recordType: z.enum([
          "RECEIPT",
          "OBSERVATION",
          "FORECAST",
          "EVENT",
          "OUTCOME",
        ]),
        recordId: NonEmptyId,
        versionId: NonEmptyId,
      }),
    ),
    declaredAssumptions: z.array(
      z.object({
        name: NonEmptyId,
        value: z.unknown(),
        unit: z.string().nullable(),
      }),
    ),
    unknownReasons: z.array(z.string()),
  })
  .passthrough();
export type DecisionBasisDTO = z.infer<typeof DecisionBasisSchema>;

export const OutcomeSchema = z
  .object({
    schemaVersion: z.literal(1),
    outcomeId: NonEmptyId,
    targetId: NonEmptyId,
    targetAvailableAt: nullableDate,
    measuredAt: nullableDate,
    value: z.number().finite().nullable(),
    unit: z.string().nullable(),
    kind: z.enum(["OBSERVED", "REVIEWED", "SIMULATED", "UNKNOWN"]),
    sourceReceiptIds: z.array(NonEmptyId),
    unknownReason: z.string().nullable(),
  })
  .passthrough();
export type OutcomeDTO = z.infer<typeof OutcomeSchema>;

export const GeoCoordinateSchema = z.object({
  lat: z.number().finite().min(-90).max(90),
  lon: z.number().finite().min(-180).max(180),
});

export const PortRegistryQualityEntrySchema = z
  .object({
    modelId: NonEmptyId,
    code: NonEmptyId,
    name: NonEmptyId,
    short: NonEmptyId,
    authority: NonEmptyId,
    location: GeoCoordinateSchema,
    coast: z.enum(["west", "east", "south"]),
    capacityIndex: z.number().finite().nonnegative(),
    berthCount: z.number().int().nonnegative(),
    connectivityScore: z.number().finite().nonnegative(),
  })
  .passthrough();

export const PortRegistryQualityResponseSchema = z.array(
  PortRegistryQualityEntrySchema,
);

export const QualityBatchSchema = z
  .object({
    schemaVersion: z.literal(1),
    observations: z.array(ObservationSchema),
    forecasts: z.array(ForecastClaimSchema),
    events: z.array(EventRestrictionSchema),
    outcomes: z.array(OutcomeSchema),
    coordinates: z.array(
      z.object({
        recordId: z.string().nullable(),
        coordinate: GeoCoordinateSchema,
      }),
    ),
    rejected: z.array(
      z.object({
        recordId: z.string().nullable(),
        reason: z.string(),
        raw: z.unknown(),
      }),
    ),
  })
  .passthrough()
  .superRefine((batch, context) => {
    const checkUnique = (values: string[], path: string[]) => {
      const seen = new Set<string>();
      values.forEach((value, index) => {
        if (seen.has(value))
          context.addIssue({
            code: "custom",
            path: [...path, index],
            message: `Duplicate identifier: ${value}`,
          });
        seen.add(value);
      });
    };
    checkUnique(
      batch.observations.map((row) => row.observationId),
      ["observations"],
    );
    for (const issue of groupForecastRows(
      batch.forecasts.map((row, index) => ({ row, raw: row, index })),
    ).rejected) {
      context.addIssue({
        code: "custom",
        path: ["forecasts", issue.index],
        message: issue.reason,
      });
    }
    checkUnique(
      batch.events.map((row) => row.eventId),
      ["events"],
    );
    checkUnique(
      batch.outcomes.map((row) => row.outcomeId),
      ["outcomes"],
    );
  })
  .transform((batch) => ({
    ...batch,
    forecasts: groupForecastRows(
      batch.forecasts.map((row, index) => ({ row, raw: row, index })),
    ).accepted,
  }));
export type QualityBatchDTO = z.infer<typeof QualityBatchSchema>;

/**
 * Additive presentation contract for source quality. Missing facts stay null
 * with an explanation; this shape does not infer quality from row counts.
 */
export const SourceQualitySchema = z
  .object({
    schemaVersion: z.literal(1),
    temporalRole: SourceTemporalRoleSchema,
    valueKinds: z.array(SourceValueKindSchema).min(1),
    operationalUse: SourceOperationalUseSchema,
    receipt: z.object({
      lastFetchedAt: nullableDate,
      lastCheckedAt: nullableDate,
      status: z.enum([
        "LIVE",
        "CACHED_LIVE",
        "STALE",
        "SYNTHETIC",
        "UNAVAILABLE",
      ]),
      fallback: z.string().nullable(),
    }),
    coverage: z.object({
      portCodes: z.array(z.string()).nullable(),
      variables: z.array(z.string()).nullable(),
      observedFrom: nullableDate,
      observedThrough: nullableDate,
      observationAgeSeconds: nullableNonNegative,
      observationFreshnessBudgetSeconds: nullableNonNegative,
      forecastOriginAt: nullableDate,
      targetFrom: nullableDate,
      targetThrough: nullableDate,
      datePrecision: z.enum(["INSTANT", "DATE_ONLY", "UNKNOWN"]),
    }),
    provenance: z.object({
      provider: z.string().nullable(),
      sourceProductId: z.string().nullable(),
      sourceReceiptId: z.string().nullable(),
      originalRef: z.string().nullable(),
      originalHash: z.string().nullable(),
      derivationVersion: z.string().nullable(),
    }),
    quality: z.object({
      rowCount: nullableNonNegative,
      confidence: z.number().finite().min(0).max(1).nullable(),
      completeness: z.number().finite().min(0).max(1).nullable(),
      missingFields: z.array(z.string()),
      issues: z.array(z.string()),
    }),
    unknownReasons: z.array(z.string()),
    metadataVersion: z.string().optional(),
    projectionVersion: z.string().optional(),
    firstAvailableAt: nullableDate.optional(),
    semantics: z
      .object({
        dataKind: z.string().optional(),
        measurementKind: z.string().optional(),
        consumerRole: z.string().optional(),
        meaning: z.string().optional(),
        firstAvailableAt: nullableDate.optional(),
        publishedAt: nullableDate.optional(),
        providerPublicationAt: nullableDate.optional(),
        providerIssueAt: nullableDate.optional(),
        parserVersion: z.string().optional(),
        stationObservation: z.boolean().optional(),
        sourceUnits: z.record(z.string(), z.string().nullable()).optional(),
        outputUnits: z.record(z.string(), z.string().nullable()).optional(),
      })
      .passthrough()
      .optional(),
    requestedCoverage: z
      .object({
        portCodes: z.array(z.string()).nullable(),
        variables: z.array(z.string()).nullable(),
        from: nullableDate.optional(),
        through: nullableDate.optional(),
        meaning: z.string().optional(),
      })
      .passthrough()
      .optional(),
    units: z
      .array(
        z
          .object({
            variable: z.string(),
            sourceVariable: z.string(),
            sourceUnit: z.string().nullable(),
            outputUnit: z.string(),
            statistic: z.string(),
            aggregation: z.string(),
            derivation: z.string(),
            parserVersion: z.string(),
          })
          .passthrough(),
      )
      .optional(),
    sourceReceipts: z.array(SourceReceiptSchema).optional(),
    components: z.array(z.record(z.string(), z.unknown())).optional(),
  })
  .passthrough();

export type SourceQualityDTO = z.infer<typeof SourceQualitySchema>;

export type SourceQualityParseResult =
  { ok: true; value: SourceQualityDTO } | { ok: false; reason: string };

export function parseSourceQuality(value: unknown): SourceQualityParseResult {
  const parsed = SourceQualitySchema.safeParse(value);
  if (parsed.success) return { ok: true, value: parsed.data };
  const firstIssue = parsed.error.issues[0];
  return {
    ok: false,
    reason: firstIssue
      ? `${firstIssue.path.join(".") || "source quality"}: ${firstIssue.message}`
      : "Source quality metadata is malformed.",
  };
}

/** The canonical registry identifiers already exposed by /ports/registry. */
export interface SourcePortRegistryEntry {
  code: string;
  modelId: string;
  short: string;
  name: string;
}

/**
 * Resolve only identifiers represented by the existing port registry.
 * Unresolved values are retained for review; this helper never guesses an
 * alias or silently drops a source-provided port code.
 */
export function canonicalizePortCodes(
  values: readonly string[] | null,
  registry: readonly SourcePortRegistryEntry[],
): { canonical: string[]; unresolved: string[] } {
  if (!values) return { canonical: [], unresolved: [] };
  const byIdentifier = new Map<string, string>();
  for (const port of registry) {
    for (const identifier of [port.code, port.modelId, port.short, port.name]) {
      const key = identifier.trim().toLocaleUpperCase();
      if (key) byIdentifier.set(key, port.code);
    }
  }
  const canonical = new Set<string>();
  const unresolved = new Set<string>();
  for (const value of values) {
    const key = value.trim().toLocaleUpperCase();
    const code = byIdentifier.get(key);
    if (code) canonical.add(code);
    else if (value.trim()) unresolved.add(value.trim());
  }
  return { canonical: [...canonical], unresolved: [...unresolved] };
}

const unitFamily = (unit: string | null): string | null => {
  if (!unit) return null;
  const normalized = unit.trim().toLocaleLowerCase().replaceAll(" ", "");
  const families: Record<string, string> = {
    m: "length",
    km: "length",
    nm: "length",
    "m/s": "speed",
    "km/h": "speed",
    kn: "speed",
    kt: "speed",
    mm: "precipitation",
    "mm/h": "precipitation-rate",
    c: "temperature",
    "°c": "temperature",
    degc: "temperature",
    h: "duration",
    hr: "duration",
    hour: "duration",
    hours: "duration",
    count: "count",
    vessel: "count",
    vessels: "count",
    usd: "currency:usd",
    inr: "currency:inr",
  };
  return families[normalized] ?? null;
};

const RejectedQualityRecordSchema = z.object({
  recordId: z.string().nullable(),
  reason: z.string().trim().min(1),
  raw: z.unknown(),
});

const QualityBatchEnvelopeSchema = z
  .object({
    schemaVersion: z.literal(1),
    observations: z.array(z.unknown()).default([]),
    forecasts: z.array(z.unknown()).default([]),
    events: z.array(z.unknown()).default([]),
    outcomes: z.array(z.unknown()).default([]),
    coordinates: z.array(z.unknown()).default([]),
    rejected: z.array(RejectedQualityRecordSchema).default([]),
  })
  .passthrough();

function recordId(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  for (const key of [
    "observationId",
    "predictionId",
    "targetId",
    "eventId",
    "outcomeId",
    "recordId",
  ]) {
    if (typeof item[key] === "string" && item[key].trim()) return item[key];
  }
  return null;
}

type QualityBatchParseResult =
  { ok: true; value: QualityBatchDTO } | { ok: false; reason: string };

/**
 * Parse a mixed quality batch without discarding bad rows. Valid rows are
 * retained; malformed, duplicate, incompatible or invalid-coordinate rows
 * are moved to the audit list with their original payload and a reason.
 */
export function parseQualityBatch(value: unknown): QualityBatchParseResult {
  const envelope = QualityBatchEnvelopeSchema.safeParse(value);
  if (!envelope.success) {
    const issue = envelope.error.issues[0];
    return {
      ok: false,
      reason: issue
        ? `${issue.path.join(".") || "quality batch"}: ${issue.message}`
        : "Quality batch envelope is malformed.",
    };
  }

  const rejected = [...envelope.data.rejected];
  const acceptRows = <T>(
    rows: unknown[],
    schema: z.ZodType<T>,
    idOf: (row: T) => string,
    label: string,
  ): T[] => {
    const accepted: T[] = [];
    const ids = new Set<string>();
    for (const raw of rows) {
      const parsed = schema.safeParse(raw);
      if (!parsed.success) {
        const issue = parsed.error.issues[0];
        rejected.push({
          recordId: recordId(raw),
          reason: `${label}: ${issue?.path.join(".") || "record"}: ${issue?.message ?? "invalid record"}`,
          raw,
        });
        continue;
      }
      const id = idOf(parsed.data);
      if (ids.has(id)) {
        rejected.push({
          recordId: id,
          reason: `${label}: duplicate identifier ${id}.`,
          raw,
        });
        continue;
      }
      ids.add(id);
      accepted.push(parsed.data);
    }
    return accepted;
  };

  const observations = acceptRows(
    envelope.data.observations,
    ObservationSchema,
    (row) => row.observationId,
    "Observation",
  );
  const forecastRows: ForecastBatchRow[] = [];
  envelope.data.forecasts.forEach((raw, index) => {
    const parsed = ForecastClaimSchema.safeParse(raw);
    if (parsed.success) {
      forecastRows.push({ row: parsed.data, raw, index });
      return;
    }
    const issue = parsed.error.issues[0];
    rejected.push({
      recordId: recordId(raw),
      reason: `Forecast: ${issue?.path.join(".") || "record"}: ${issue?.message ?? "invalid record"}`,
      raw,
    });
  });
  const forecastGroups = groupForecastRows(forecastRows);
  const forecasts = forecastGroups.accepted;
  rejected.push(
    ...forecastGroups.rejected.map(({ recordId, reason, raw }) => ({
      recordId,
      reason,
      raw,
    })),
  );
  const events = acceptRows(
    envelope.data.events,
    EventRestrictionSchema,
    (row) => row.eventId,
    "Event",
  );
  const outcomes = acceptRows(
    envelope.data.outcomes,
    OutcomeSchema,
    (row) => row.outcomeId,
    "Outcome",
  );
  const seenUnits = new Map<string, string>();
  const compatibleObservations = observations.filter((row) => {
    const family = unitFamily(row.unit);
    if (!family) return true;
    const key = `${row.portCode ?? row.entityId}\u0000${row.variable}`;
    const previous = seenUnits.get(key);
    if (!previous) {
      seenUnits.set(key, family);
      return true;
    }
    if (previous === family) return true;
    rejected.push({
      recordId: row.observationId,
      reason: `Observation: unit ${row.unit} is incompatible with another unit for ${row.variable}.`,
      raw: row,
    });
    return false;
  });
  const coordinates: Array<{
    recordId: string | null;
    coordinate: z.infer<typeof GeoCoordinateSchema>;
  }> = [];
  for (const raw of envelope.data.coordinates) {
    if (!raw || typeof raw !== "object") {
      rejected.push({
        recordId: null,
        reason:
          "Coordinate: expected an object with a recordId and coordinate.",
        raw,
      });
      continue;
    }
    const item = raw as Record<string, unknown>;
    const parsed = GeoCoordinateSchema.safeParse(item.coordinate);
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      rejected.push({
        recordId: typeof item.recordId === "string" ? item.recordId : null,
        reason: `Coordinate: ${issue?.path.join(".") || "value"}: ${issue?.message ?? "invalid coordinate"}`,
        raw,
      });
      continue;
    }
    coordinates.push({
      recordId: typeof item.recordId === "string" ? item.recordId : null,
      coordinate: parsed.data,
    });
  }

  const parsed = QualityBatchSchema.safeParse({
    ...envelope.data,
    observations: compatibleObservations,
    forecasts,
    events,
    outcomes,
    coordinates,
    rejected,
  });
  if (parsed.success) return { ok: true, value: parsed.data };
  const issue = parsed.error.issues[0];
  return {
    ok: false,
    reason: issue
      ? `${issue.path.join(".") || "quality batch"}: ${issue.message}`
      : "Quality batch could not be normalized.",
  };
}
