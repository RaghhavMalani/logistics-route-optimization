import fs from "node:fs";
import type { BrowserContext, Page } from "@playwright/test";
import { expect, settle, test } from "../harness";
import { parseSourceQuality } from "@/types/source-quality";

// Producer-export presentation fixtures. They never enter a retained source or
// weather ledger, and do not establish provider correctness or real outcomes.
const ARCHIVE = "Weather history (Open-Meteo ERA5 archive)";
const ADDITIONAL = "Current surface forecast / INNSA";
const HASH = "b".repeat(64);

function producerQuality() {
  return {
    schemaVersion: 1,
    metadataVersion: "weather-source-quality-v1",
    temporalRole: "HISTORICAL",
    valueKinds: ["DERIVED"],
    operationalUse: "CONTEXT_ONLY",
    receipt: {
      lastFetchedAt: null,
      lastCheckedAt: "2026-10-22T09:40:00Z",
      status: "CACHED_LIVE",
      fallback: "Legacy parsed response; original receipt unavailable",
    },
    coverage: {
      portCodes: ["INNSA"],
      variables: ["wind_gust"],
      observedFrom: "2025-04-26",
      observedThrough: "2026-06-07",
      observationAgeSeconds: null,
      observationFreshnessBudgetSeconds: null,
      forecastOriginAt: null,
      targetFrom: null,
      targetThrough: null,
      datePrecision: "DATE_ONLY",
    },
    requestedCoverage: {
      portCodes: ["INNSA", "INMAA"],
      variables: ["wind_gust", "visibility", "wave_height"],
      from: "2025-04-26",
      through: "2026-06-07",
      meaning: "Configured request only; finite parsed coverage is separate.",
    },
    provenance: {
      provider: "Open-Meteo",
      sourceProductId: "open-meteo:era5:daily-history-v1",
      sourceReceiptId: null,
      originalRef: null,
      originalHash: null,
      derivationVersion: "open-meteo-daily-flatten-v1",
    },
    quality: {
      rowCount: 1,
      confidence: null,
      completeness: null,
      missingFields: ["visibility", "wave_height"],
      issues: [],
    },
    semantics: {
      dataKind: "REANALYSIS",
      consumerRole:
        "Training feature history; never current hourly approach weather or station outcomes.",
      stationObservation: false,
      firstAvailableAt: null,
      providerPublicationAt: null,
      providerIssueAt: null,
      parserVersion: "open-meteo-daily-flatten-v1",
    },
    units: [
      {
        variable: "wind_gust",
        sourceVariable: "wind_gusts_10m_max",
        sourceUnit: "km/h",
        outputUnit: "kn",
        statistic: "MAX",
        aggregation: "UTC daily provider statistic",
        aggregationWindow:
          "Calendar date in the requested UTC timezone; date-only source precision.",
        derivation: "source × 0.539957",
        parserVersion: "open-meteo-daily-flatten-v1",
        rawOrDerived: "DERIVED",
      },
    ],
    sourceReceipts: [],
    unknownReasons: [
      "Legacy cache has no retained original response or first application receipt; filesystem time is not evidence.",
      "Confidence is unavailable; status weights are heuristic readiness, not calibrated accuracy.",
    ],
  };
}

function currentQuality() {
  const quality = producerQuality();
  return {
    ...quality,
    temporalRole: "FORECAST",
    valueKinds: ["FORECAST"],
    operationalUse: "CALCULATION_INPUT",
    receipt: {
      lastFetchedAt: "2026-10-22T09:35:00Z",
      lastCheckedAt: "2026-10-22T09:40:00Z",
      status: "STALE",
      fallback: "Previous original retained",
    },
    coverage: {
      ...quality.coverage,
      observedFrom: null,
      observedThrough: null,
      forecastOriginAt: null,
      targetFrom: "2026-10-22T10:00:00Z",
      targetThrough: "2026-10-23T10:00:00Z",
      datePrecision: "INSTANT",
    },
    provenance: {
      ...quality.provenance,
      sourceProductId: "open-meteo:surface:hourly-v1",
      sourceReceiptId: "receipt-fixture-original-1",
      originalRef: "https://api.open-meteo.com/v1/forecast",
      originalHash: HASH,
    },
    semantics: {
      ...quality.semantics,
      dataKind: "FORECAST",
      consumerRole:
        "Hourly gust and visibility under explicit operator limits.",
      firstAvailableAt: "2026-10-22T09:35:00Z",
    },
    sourceReceipts: [
      {
        schemaVersion: 1,
        sourceProductId: "open-meteo:surface:hourly-v1",
        sourceReceiptId: "receipt-fixture-original-1",
        provider: "Open-Meteo",
        fetchedAt: "2026-10-22T09:35:00Z",
        checkedAt: "2026-10-22T09:40:00Z",
        firstAvailableAt: "2026-10-22T09:35:00Z",
        originalRef: "https://api.open-meteo.com/v1/forecast",
        originalHash: HASH,
        parserVersion: "hourly-response-fixture-v1",
        parseStatus: "ACCEPTED",
        issues: [],
      },
    ],
  };
}

function producerRegister() {
  const fixture = JSON.parse(
    fs.readFileSync(
      new URL("../fixtures/provenance.json", import.meta.url),
      "utf8",
    ),
  );
  const legacy = fixture.sources[ARCHIVE];
  fixture.sources = {
    [ARCHIVE]: {
      ...legacy,
      // These legacy clocks must not fill explicit null normalized clocks.
      fetched_at: "1999-01-01T12:00:00Z",
      observed_at: "1999-01-01T00:00:00Z",
      sourceQuality: producerQuality(),
    },
  };
  fixture.sourceQualityProducts = {
    [ADDITIONAL]: {
      ...legacy,
      source: ADDITIONAL,
      provider: "Open-Meteo",
      status: "STALE",
      confidence: null,
      detail:
        "Retained current surface forecast product; provider outage leaves its original unchanged.",
      sourceQuality: currentQuality(),
    },
  };
  fixture.sourceQualityProjection = {
    version: "retained-public-source-quality-v1",
    readOnly: true,
    unavailableProjections: [],
  };
  return fixture;
}

async function signInAdmin(
  context: BrowserContext,
  page: Page,
  register: ReturnType<typeof producerRegister>,
) {
  const now = Date.now();
  await context.route("**/api/demo/session", (route) =>
    route.fulfill({
      json: {
        user: {
          id: "qa-producer-admin",
          email: "producer@portwatch.demo",
          displayName: "QA Admin",
          role: "NATIONAL_ADMIN",
          organisation: "QA",
          portCode: null,
          companyId: null,
          vesselIds: [],
        },
        mode: "demo",
        issuedAt: new Date(now).toISOString(),
        expiresAt: new Date(now + 3600000).toISOString(),
        accessToken: "qa-producer-token",
      },
    }),
  );
  await context.route("**/api/demo/terminal/health", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: fs.readFileSync(
        new URL("../fixtures/health.json", import.meta.url),
        "utf8",
      ),
    }),
  );
  await context.route("**/api/demo/terminal/provenance", (route) =>
    route.fulfill({ json: register }),
  );
  await page.goto("/login");
  await page.getByRole("button", { name: "Admin demo", exact: true }).click();
  await page.waitForURL("**/admin/radar");
  await page.goto("/admin/data");
  await settle(page);
}

test("additive producer DTO preserves date-only coverage, derivations and original receipt clocks", () => {
  const history = parseSourceQuality(producerQuality());
  expect(history.ok).toBe(true);
  if (!history.ok) throw new Error(history.reason);
  expect(history.value).toEqual(producerQuality());
  expect(history.value.coverage.observedThrough).toBe("2026-06-07");
  expect(history.value.coverage.targetThrough).toBeNull();
  expect(history.value.coverage.portCodes).toEqual(["INNSA"]);
  expect(history.value.requestedCoverage?.portCodes).toEqual([
    "INNSA",
    "INMAA",
  ]);
  const current = parseSourceQuality(currentQuality());
  expect(current.ok).toBe(true);
  if (!current.ok) throw new Error(current.reason);
  expect(current.value.sourceReceipts?.[0]).toMatchObject({
    sourceReceiptId: "receipt-fixture-original-1",
    fetchedAt: "2026-10-22T09:35:00Z",
    checkedAt: "2026-10-22T09:40:00Z",
    firstAvailableAt: "2026-10-22T09:35:00Z",
    originalHash: HASH,
  });
});

test("malformed optional producer extensions are rejected instead of silently stripped", () => {
  const invalids = [
    { ...producerQuality(), semantics: { firstAvailableAt: "2026-02-30" } },
    {
      ...producerQuality(),
      requestedCoverage: { portCodes: "INNSA", variables: [] },
    },
    {
      ...producerQuality(),
      units: [{ ...producerQuality().units[0], sourceUnit: 123 }],
    },
    {
      ...currentQuality(),
      sourceReceipts: [
        {
          ...currentQuality().sourceReceipts[0],
          firstAvailableAt: "2026-10-22T10:00:00Z",
        },
      ],
    },
  ];
  for (const value of invalids) {
    const result = parseSourceQuality(value);
    expect(result.ok).toBe(false);
    if (result.ok)
      throw new Error("Malformed optional producer metadata was accepted");
    expect(result.reason).toMatch(
      /semantics|requestedCoverage|units|sourceReceipts/,
    );
  }
});

test("existing inspector shows supported producer facts and added product; download retains exact DTOs", async ({
  context,
  page,
}) => {
  const register = producerRegister();
  await signInAdmin(context, page, register);
  await page
    .getByRole("button", {
      name: `Inspect evidence for ${ARCHIVE}`,
      exact: true,
    })
    .click();
  const inspector = page.getByTestId("source-quality-inspector");
  await expect(inspector).toContainText("REANALYSIS");
  await expect(inspector).toContainText("HISTORICAL");
  await expect(inspector).toContainText("Training feature history");
  await expect(inspector).toContainText("2026-06-07 (date only)");
  await expect(inspector).toContainText("DATE_ONLY");
  await expect(inspector).not.toContainText("1999");
  await expect(
    inspector.getByText("Last fetched", { exact: true }).locator(".."),
  ).toContainText("Unknown");
  await expect(
    inspector
      .getByText("First application receipt", { exact: true })
      .locator(".."),
  ).toContainText("Unknown");
  const actual = inspector.getByText("Coverage", { exact: true }).locator("..");
  await expect(actual).toContainText("INNSA");
  await expect(actual).toContainText("wind_gust");
  await expect(actual).not.toContainText("INMAA");
  await expect(actual).not.toContainText("visibility");
  await inspector
    .getByText("Requested coverage (separate from actual coverage)", {
      exact: true,
    })
    .click();
  await expect(
    inspector.locator("details").filter({
      hasText: "Requested coverage (separate from actual coverage)",
    }),
  ).toContainText("INMAA");
  await inspector
    .getByText("Units, daily statistics and derivations", { exact: true })
    .click();
  await expect(inspector).toContainText("source × 0.539957");
  await expect(inspector).toContainText("km/h");
  await expect(inspector).toContainText("open-meteo-daily-flatten-v1");
  await expect(inspector).toContainText("filesystem time is not evidence");
  await inspector
    .getByRole("button", { name: "Close source evidence inspector" })
    .click();
  await page
    .getByRole("button", {
      name: `Inspect evidence for ${ADDITIONAL}`,
      exact: true,
    })
    .click();
  await expect(inspector).toContainText("FORECAST");
  await expect(inspector).toContainText("CALCULATION_INPUT");
  await expect(inspector).toContainText("receipt-fixture-original-1");
  await expect(inspector).toContainText(HASH);
  await expect(inspector).toContainText(
    "https://api.open-meteo.com/v1/forecast",
  );
  await expect(inspector).toContainText("weather-source-quality-v1");
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download source quality report as JSON" })
    .click();
  const download = await downloadPromise;
  const path = await download.path();
  expect(path).not.toBeNull();
  const report = JSON.parse(fs.readFileSync(path!, "utf8"));
  expect(report.reportType).toBe("source-quality-diagnostics");
  expect(report.sources).toHaveLength(2);
  expect(
    report.sources.find((row: { source: string }) => row.source === ARCHIVE)
      .sourceQuality,
  ).toEqual(producerQuality());
  expect(
    report.sources.find((row: { source: string }) => row.source === ADDITIONAL)
      .sourceQuality,
  ).toEqual(currentQuality());
});

test("bad optional added-product metadata retains useful legacy source fields", async ({
  context,
  page,
}) => {
  const register = producerRegister();
  register.sourceQualityProducts[
    ADDITIONAL
  ].sourceQuality.semantics.firstAvailableAt = "bad-time";
  await signInAdmin(context, page, register);
  await page
    .getByRole("button", {
      name: `Inspect evidence for ${ADDITIONAL}`,
      exact: true,
    })
    .click();
  const inspector = page.getByTestId("source-quality-inspector");
  await expect(inspector.getByRole("alert")).toContainText(
    "semantics.firstAvailableAt",
  );
  await expect(inspector.getByRole("alert")).toContainText(
    "Raw legacy provenance remains available",
  );
  await expect(inspector).toContainText("Open-Meteo");
  await expect(inspector).toContainText(ADDITIONAL);
});
