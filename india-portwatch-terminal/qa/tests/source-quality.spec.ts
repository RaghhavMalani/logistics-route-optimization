import fs from "node:fs";
import type { BrowserContext, Page } from "@playwright/test";
import { expect, settle, test } from "../harness";
import {
  canonicalizePortCodes,
  parseQualityBatch,
  parseSourceQuality,
} from "@/types/source-quality";

function qualityObservation(overrides: Record<string, unknown> = {}) {
  return {
    schemaVersion: 1,
    observationId: "obs-1",
    entityId: "wind-station-1",
    sourceReceiptId: null,
    portCode: "INNSA",
    variable: "wind_gust",
    value: 0,
    unit: "kn",
    aggregation: "MAX",
    observedFrom: "2026-10-18",
    observedThrough: "2026-10-19T00:00:00Z",
    firstAvailableAt: "2026-10-19T00:10:00Z",
    valueKind: "OBSERVED",
    quality: [],
    unknownReason: null,
    ...overrides,
  };
}

function qualityBatch(overrides: Record<string, unknown> = {}) {
  return {
    schemaVersion: 1,
    observations: [],
    forecasts: [],
    events: [],
    outcomes: [],
    coordinates: [],
    rejected: [],
    ...overrides,
  };
}

test("quality batch preserves zero, date-only precision, and aggregation", () => {
  const result = parseQualityBatch(
    qualityBatch({ observations: [qualityObservation()] }),
  );
  expect(result.ok).toBe(true);
  if (!result.ok) return;
  expect(result.value.observations[0]).toMatchObject({
    value: 0,
    observedFrom: "2026-10-18",
    aggregation: "MAX",
  });
  expect(result.value.rejected).toHaveLength(0);
});

test("quality batch retains malformed rows and invalid coordinates in audit", () => {
  const result = parseQualityBatch(
    qualityBatch({
      observations: [
        qualityObservation(),
        qualityObservation({
          observationId: "bad-date",
          observedFrom: "2026-02-30",
        }),
      ],
      coordinates: [
        { recordId: "bad-location", coordinate: { lat: 91, lon: 72 } },
      ],
    }),
  );
  expect(result.ok).toBe(true);
  if (!result.ok) return;
  expect(result.value.observations).toHaveLength(1);
  expect(result.value.rejected).toHaveLength(2);
  expect(result.value.rejected.map((item) => item.recordId)).toEqual([
    "bad-date",
    "bad-location",
  ]);
  expect(result.value.rejected[0].reason).toContain("observedFrom");
});

test("quality batch audits duplicate identifiers and incompatible units", () => {
  const result = parseQualityBatch(
    qualityBatch({
      observations: [
        qualityObservation(),
        qualityObservation(),
        qualityObservation({ observationId: "bad-unit", unit: "USD" }),
      ],
    }),
  );
  expect(result.ok).toBe(true);
  if (!result.ok) return;
  expect(result.value.observations).toHaveLength(1);
  expect(result.value.rejected.map((item) => item.recordId)).toEqual([
    "obs-1",
    "bad-unit",
  ]);
  expect(result.value.rejected[0].reason).toContain("duplicate identifier");
  expect(result.value.rejected[1].reason).toContain("incompatible");
});

test("unknown event applicability needs a reason and is preserved as rejected", () => {
  const result = parseQualityBatch(
    qualityBatch({
      events: [
        {
          schemaVersion: 1,
          eventId: "event-1",
          revisionId: null,
          effectiveFrom: null,
          effectiveThrough: null,
          firstAvailableAt: null,
          affectedPortCodes: null,
          affectedAssetIds: null,
          applicability: "UNKNOWN",
          sourceReceiptIds: [],
          exceptions: [],
          unknownReason: null,
        },
      ],
    }),
  );
  expect(result.ok).toBe(true);
  if (!result.ok) return;
  expect(result.value.events).toHaveLength(0);
  expect(result.value.rejected[0]).toMatchObject({
    recordId: "event-1",
    reason: expect.stringContaining("requires an explanation"),
  });
});

test("port coverage uses registry identifiers and preserves unresolved codes", () => {
  expect(
    canonicalizePortCodes(
      ["jnpt", "INNSA", "KDL", "legacy-port"],
      [
        {
          modelId: "JNPT",
          code: "INNSA",
          short: "JNP",
          name: "JNPA / Nhava Sheva",
        },
        {
          modelId: "DEENDAYAL",
          code: "INIXY",
          short: "KDL",
          name: "Deendayal (Kandla)",
        },
      ],
    ),
  ).toEqual({
    canonical: ["INNSA", "INIXY"],
    unresolved: ["legacy-port"],
  });
});

test("source quality fixture validates observation age separately from receipt time", () => {
  const provenance = JSON.parse(
    fs.readFileSync(
      new URL("../fixtures/provenance.json", import.meta.url),
      "utf8",
    ),
  ) as { sources: Record<string, { sourceQuality?: unknown }> };
  const quality =
    provenance.sources["Port activity (IMF PortWatch)"].sourceQuality;
  expect(parseSourceQuality(quality).ok).toBe(true);
  expect(quality).toMatchObject({
    receipt: { lastFetchedAt: expect.any(String) },
    coverage: { observationAgeSeconds: expect.any(Number) },
  });
  expect(quality).not.toHaveProperty("receipt.ageSeconds");
});

test("source quality export retains status, observation context, and unknowns", async ({
  context,
  page,
}) => {
  await signInAdmin(context, page);
  await page.goto("/admin/data");
  await settle(page);

  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download source quality report as JSON" })
    .click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(
    /^portwatch-source-quality-.*\.json$/,
  );
  const filePath = await download.path();
  expect(filePath).not.toBeNull();
  const report = JSON.parse(fs.readFileSync(filePath as string, "utf8")) as {
    reportType: string;
    scope: string;
    limitation: string;
    sources: Array<{
      source: string;
      status: string;
      sourceQuality: {
        coverage: { observedThrough: string | null };
        unknownReasons: string[];
      };
    }>;
  };
  expect(report).toMatchObject({
    reportType: "source-quality-diagnostics",
    scope: "Admin Data source register",
  });
  expect(report.limitation).toContain("unknown values remain null");
  expect(report.sources[0].sourceQuality.unknownReasons.length).toBeGreaterThan(
    0,
  );
  expect(report.sources.some((source) => source.status === "STALE")).toBe(true);
});

async function signInAdmin(context: BrowserContext, page: Page) {
  const now = Date.now();
  const fixture = (name: string) =>
    fs.readFileSync(
      new URL(`../fixtures/${name}.json`, import.meta.url),
      "utf8",
    );
  await context.route(
    (url: URL) => url.pathname.endsWith("/api/demo/session"),
    async (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user: {
            id: "qa-admin",
            email: "admin@portwatch.demo",
            displayName: "QA Admin",
            role: "NATIONAL_ADMIN",
            organisation: "QA Demo",
            portCode: null,
            companyId: null,
            vesselIds: [],
          },
          mode: "demo",
          issuedAt: new Date(now).toISOString(),
          expiresAt: new Date(now + 60 * 60_000).toISOString(),
          accessToken: "qa-demo-token",
        }),
      }),
  );
  await context.route("**/api/demo/terminal/health", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: fixture("health"),
    }),
  );
  await context.route("**/api/demo/terminal/provenance", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: fixture("provenance"),
    }),
  );
  await page.goto("/login");
  await page.getByRole("button", { name: "Admin demo" }).click();
  await page.waitForURL("**/admin/radar");
}

test("Admin Data inspector keeps receipt, source time, and unknown coverage separate", async ({
  context,
  page,
}) => {
  await signInAdmin(context, page);
  await page.goto("/admin/data");
  await settle(page);

  await page
    .getByRole("button", {
      name: "Inspect evidence for Weather history (Open-Meteo ERA5 archive)",
    })
    .click();

  const inspector = page.getByTestId("source-quality-inspector");
  await expect(inspector).toContainText("HISTORICAL");
  await expect(inspector).toContainText("CONTEXT_ONLY");
  await expect(inspector).toContainText("Last fetched");
  await expect(inspector).toContainText("Source observation through");
  await expect(inspector).toContainText("2026-06-07");
  await expect(inspector).toContainText("Ports unknown");
  await expect(inspector).toContainText("variables unknown");
  await expect(inspector).toContainText("Exact port-code and variable lists");
  await expect(inspector).not.toContainText("100%");
});

test("source evidence control is keyboard reachable and exposes selection", async ({
  context,
  page,
}) => {
  await signInAdmin(context, page);
  await page.goto("/admin/data");
  await settle(page);

  const inspect = page.getByRole("button", {
    name: "Inspect evidence for Port activity (IMF PortWatch)",
  });
  await inspect.focus();
  await expect(inspect).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(inspect).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("source-quality-inspector")).toContainText(
    "Original receipt hash and derivation version",
  );
  await page
    .getByRole("button", { name: "Close source evidence inspector" })
    .click();
  await expect(page.getByTestId("source-quality-inspector")).not.toBeVisible();
});

test("malformed optional quality metadata is explained without losing legacy receipt data", async ({
  context,
  page,
}) => {
  const provenance = JSON.parse(
    fs.readFileSync(
      new URL("../fixtures/provenance.json", import.meta.url),
      "utf8",
    ),
  ) as { sources: Record<string, { sourceQuality?: unknown }> };
  const malformedQuality = provenance.sources["Port activity (IMF PortWatch)"]
    .sourceQuality as {
    schemaVersion: number;
    receipt: { lastFetchedAt: string };
  };
  malformedQuality.receipt.lastFetchedAt = "2025-02-30";
  await signInAdmin(context, page);
  await context.route(
    (url) => url.pathname.endsWith("/api/demo/terminal/provenance"),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(provenance),
      }),
  );
  await page.goto("/admin/data");
  await settle(page);
  await page
    .getByRole("button", {
      name: "Inspect evidence for Port activity (IMF PortWatch)",
    })
    .click();

  const inspector = page.getByTestId("source-quality-inspector");
  await expect(inspector.getByRole("alert")).toContainText(
    "Quality metadata rejected",
  );
  await expect(inspector.getByRole("alert")).toContainText(
    "receipt.lastFetchedAt",
  );
  await expect(inspector).toContainText("Last fetched");
  await expect(inspector).toContainText("Source observation through");
  await expect(inspector).toContainText("Unknown");
});
