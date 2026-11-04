import { expect, test } from "@playwright/test";
import {
  FORECAST_PREDICTION_IDENTITY_VERSION,
  ForecastClaimSchema,
  QualityBatchSchema,
  forecastPredictionIdentity,
  parseQualityBatch,
  type ForecastClaimDTO,
} from "../../src/types/source-quality";

// Pure contract regressions: no browser fixture, network or weather ledger.
function claim(overrides: Partial<ForecastClaimDTO> = {}): ForecastClaimDTO {
  return {
    schemaVersion: 1,
    targetId: "INNSA:wind_gust:2026-10-20",
    portCode: "INNSA",
    variable: "wind_gust",
    value: 12,
    unit: "kn",
    originAt: "2026-10-18T08:00:00Z",
    targetFrom: "2026-10-20T00:00:00Z",
    targetThrough: "2026-10-21T00:00:00Z",
    firstAvailableAt: "2026-10-18T08:00:00Z",
    modelVersion: "forecast-v1",
    sourceReceiptIds: ["receipt-1"],
    unknownReason: null,
    ...overrides,
  };
}

function batch(forecasts: unknown[]) {
  return {
    schemaVersion: 1,
    observations: [],
    forecasts,
    events: [],
    outcomes: [],
    coordinates: [],
    rejected: [],
  };
}

function normalize(forecasts: unknown[]) {
  const result = parseQualityBatch(batch(forecasts));
  expect(result.ok).toBe(true);
  if (!result.ok) throw new Error(result.reason);
  return result.value;
}

test("two legacy origins for one outcome survive both strict and normalized batches", () => {
  const first = claim();
  const later = claim({
    originAt: "2026-10-19T08:00:00Z",
    firstAvailableAt: "2026-10-19T08:00:00Z",
    value: 14,
    sourceReceiptIds: ["receipt-2"],
  });
  expect(ForecastClaimSchema.safeParse(first).success).toBe(true);
  const strict = QualityBatchSchema.parse(batch([first, later]));
  const normalized = normalize([first, later]);
  expect(strict.forecasts).toHaveLength(2);
  expect(normalized.forecasts).toEqual(strict.forecasts);
  expect(new Set(normalized.forecasts.map((row) => row.targetId)).size).toBe(1);
  expect(normalized.rejected).toHaveLength(0);
});

test("known providers, products, models and source revisions remain distinct", () => {
  const first = claim({ provider: "provider-a", sourceProductId: "surface" });
  const rows = [
    first,
    { ...first, provider: "provider-b" },
    { ...first, sourceProductId: "marine" },
    { ...first, modelVersion: "forecast-v2" },
    { ...first, sourceVersion: "revision-2" },
  ];
  expect(normalize(rows).forecasts).toHaveLength(5);
  expect(QualityBatchSchema.parse(batch(rows)).forecasts).toHaveLength(5);
});

test("reversing input retains the same deterministically ordered forecast set", () => {
  const rows = [
    claim({ originAt: "2026-10-19T08:00:00Z", value: 14 }),
    claim({ provider: "provider-b", value: 15 }),
    claim(),
  ];
  expect(normalize(rows)).toEqual(normalize([...rows].reverse()));
});

test("exact retries coalesce with receipt-set and object-key canonicalization", () => {
  const first = claim({ sourceReceiptIds: ["receipt-2", "receipt-1"] });
  const retry = Object.fromEntries(Object.entries(first).reverse());
  retry.sourceReceiptIds = ["receipt-1", "receipt-2", "receipt-1"];
  const result = normalize([first, retry, first]);
  expect(result.forecasts).toHaveLength(1);
  expect(result.forecasts[0].sourceReceiptIds).toEqual([
    "receipt-1",
    "receipt-2",
  ]);
  expect(result.rejected).toHaveLength(0);
  expect(QualityBatchSchema.parse(batch([retry, first])).forecasts).toEqual(
    result.forecasts,
  );
});

test("explicit prediction IDs are authoritative and preserve different predictions", () => {
  const first = claim({
    predictionId: "ledger-prediction-a",
    modelVersion: null,
  });
  const other = { ...first, predictionId: "ledger-prediction-b" };
  const identity = forecastPredictionIdentity(first);
  expect(identity).toEqual({
    ok: true,
    basis: "EXPLICIT",
    identity: JSON.stringify([
      FORECAST_PREDICTION_IDENTITY_VERSION,
      "explicit",
      "ledger-prediction-a",
    ]),
  });
  expect(normalize([first, other]).forecasts).toHaveLength(2);
});

test("conflicting explicit IDs quarantine every original payload regardless of order", () => {
  const first = claim({ predictionId: "prediction-1" });
  const conflicting = claim({
    predictionId: "prediction-1",
    provider: "different-provider",
    value: 14,
  });
  const result = normalize([first, conflicting, first]);
  expect(result.forecasts).toHaveLength(0);
  expect(result.rejected).toHaveLength(3);
  expect(
    result.rejected.every((row) => row.reason.includes("all versions")),
  ).toBe(true);
  expect(result.rejected.map((row) => row.raw)).toEqual(
    expect.arrayContaining([first, conflicting]),
  );
  expect(result).toEqual(normalize([first, conflicting, first].reverse()));
  expect(
    QualityBatchSchema.safeParse(batch([first, conflicting])).success,
  ).toBe(false);
});

test("value, later error and receipt references cannot manufacture another identity", () => {
  const first = claim();
  const conflict = { ...first, value: 14, error: 9 };
  expect(forecastPredictionIdentity(first)).toEqual(
    forecastPredictionIdentity(conflict),
  );
  const result = normalize([first, conflict]);
  expect(result.forecasts).toHaveLength(0);
  expect(result.rejected).toHaveLength(2);
  const changedReceipt = { ...first, sourceReceiptIds: ["receipt-new"] };
  expect(forecastPredictionIdentity(first)).toEqual(
    forecastPredictionIdentity(changedReceipt),
  );
  expect(normalize([first, changedReceipt]).forecasts).toHaveLength(0);
});

test("insufficient identity remains legacy-schema compatible but is quarantined", () => {
  const rows = [
    claim({ modelVersion: null }),
    claim({ originAt: null }),
    claim({ originAt: "2026-10-18" }),
    claim({ modelVersion: "   " }),
  ];
  for (const row of rows) {
    expect(ForecastClaimSchema.safeParse(row).success).toBe(true);
    expect(forecastPredictionIdentity(row).ok).toBe(false);
  }
  const result = normalize(rows);
  expect(result.forecasts).toHaveLength(0);
  expect(result.rejected).toHaveLength(rows.length);
  expect(result.rejected.every((row) => row.reason.includes("unknown"))).toBe(
    true,
  );
  expect(QualityBatchSchema.safeParse(batch(rows)).success).toBe(false);
});

test("known source version can identify a legacy vintage without guessing a model", () => {
  const forecast = claim({ modelVersion: null, sourceVersion: "operator-v1" });
  expect(forecastPredictionIdentity(forecast).ok).toBe(true);
  expect(normalize([forecast]).forecasts[0].modelVersion).toBeNull();
});

test("non-JSON metadata cannot hide a conflict behind a valid first row", () => {
  const first = claim({ predictionId: "prediction-1" });
  const conflict = { ...first, unsupportedMetadata: () => "not JSON" };
  const result = normalize([first, conflict]);
  expect(result.forecasts).toHaveLength(0);
  expect(result.rejected).toHaveLength(2);
  expect(result.rejected.every((row) => row.reason.includes("non-JSON"))).toBe(
    true,
  );
});
