import { expect, settle, test } from "../harness";
import fs from "node:fs";
import type { BrowserContext, Page } from "@playwright/test";

// Presentation fixtures only; these do not enter the retained weather ledger.
async function verifyArchive(
  { context, page }: { context: BrowserContext; page: Page },
  workspace: "Admin" | "Port",
) {
  const now = new Date().toISOString();
  await context.route("**/api/demo/terminal/**", (route) => {
    const path = new URL(route.request().url()).pathname.split(
      "/demo/terminal/",
    )[1];
    const fixture = new URL(
      `../fixtures/${path.replaceAll("/", "_")}.json`,
      import.meta.url,
    );
    return fs.existsSync(fixture)
      ? route.fulfill({
          contentType: "application/json",
          body: fs.readFileSync(fixture, "utf8"),
        })
      : route.fallback();
  });
  await context.route("**/api/demo/session", (route) =>
    route.fulfill({
      json: {
        user: {
          id: "qa-weather-admin",
          email: "weather@portwatch.demo",
          displayName: "QA weather",
          role: workspace === "Port" ? "PORT_AUTHORITY" : "NATIONAL_ADMIN",
          organisation: "QA",
          portCode: workspace === "Port" ? "INNSA" : null,
          companyId: null,
          vesselIds: [],
        },
        mode: "demo",
        issuedAt: now,
        expiresAt: new Date(Date.now() + 3600000).toISOString(),
        accessToken: "qa-weather-token",
      },
    }),
  );
  await context.route("**/api/demo/terminal/weather/feedback?**", (route) => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get("portCode")).not.toBeNull();
    return route.fulfill({
      json: {
        forecasts: [],
        total: 2,
        resolved: 2,
        pending: 0,
        scores: [],
        note: "Presentation fixture",
      },
    });
  });
  await context.route(
    "**/api/demo/terminal/weather/verification?**",
    (route) => {
      const url = new URL(route.request().url());
      const portCode = url.searchParams.get("portCode")!;
      const variable = url.searchParams.get("variable")!;
      const evidence = {
        responseSha256: `${portCode}-${variable}`,
        requestLocation: { lat: 13, lon: 80 },
        location: { lat: 13, lon: 80 },
        statistic: "maximum",
        completeHours: 24,
      };
      return route.fulfill({
        json: {
          independentTargets: 2,
          independentResolvedTargets: 2,
          reconciliation: { status: "COLLECTING" },
          originalFiveDayCase: null,
          retainedFiveDayCase: null,
          latestMatchedCase: {
            id: `${portCode}-${variable}`,
            portCode,
            variable,
            provider: "Open-Meteo surface",
            horizonDays: 1,
            targetDate: "2026-10-11",
            statistic: "maximum",
            unit: "kn",
            original: 12,
            observed: 14,
            rawError: -2,
            issuedAt: "2026-10-10T18:00:00Z",
            observedAt: "2026-10-18T10:00:00Z",
            correction: { status: "COLLECTING" },
            forecastEvidence: evidence,
            outcomeEvidence: evidence,
          },
          matchedContextCounts: {
            independentTargets: 2,
            forecastSnapshots: 6,
          },
          currentCandidate: {
            status: "COLLECTING",
            sampleCount: 2,
            reason: "Insufficient presentation fixture targets",
          },
          subsequentRecommendation: {
            correctionConsumed: false,
            reason: "Shadow only",
            hourlyApproachEffect:
              "Daily results never alter hourly approach inputs",
          },
        },
      });
    },
  );
  await context.route("**/api/demo/terminal/weather/evidence/*", (route) =>
    route.fulfill({
      json: {
        sourceContext: decodeURIComponent(
          new URL(route.request().url()).pathname.split("/").at(-1)!,
        ),
      },
    }),
  );
  const contexts = ["INNSA", "INMAA"].flatMap((portCode) =>
    ["wind_speed", "wind_gust"].map((variable) => ({
      id: `${portCode}-${variable}`,
      portCode,
      variable,
      provider: "Open-Meteo surface",
      horizonDays: 1,
      outcomeSource: "reanalysis: Open-Meteo ERA5 archive",
      outcomeKind: "reanalysis",
      season: "post_monsoon",
      unit: "kn",
      statistic: "maximum",
      aggregation: "daily UTC",
      requestedLocation: { lat: 13, lon: 80 },
      forecastLocation: { lat: 13, lon: 80 },
      outcomeLocation: { lat: 13, lon: 80 },
      independentTargets: 2,
      forecastSnapshots: 6,
      metrics: {
        bias: -2,
        mae: 2,
        rmse: 2,
        underpredictions: 2,
        overpredictions: 0,
        exact: 0,
      },
      systematicMiss: {
        direction: "UNDERPREDICTION",
        share: 1,
        descriptiveOnly: true,
      },
      readiness: {
        status: "COLLECTING",
        minimumIndependentTargets: 32,
        minimumPerPartition: 8,
        partitions: {
          fitting: 0,
          validation: 0,
          calibration: 0,
          evaluation: 2,
        },
        purged: 0,
        shortfalls: {
          fitting: 8,
          validation: 8,
          calibration: 8,
          evaluation: 6,
        },
        reasons: ["Insufficient evidence"],
      },
      shadow: {
        status: "COLLECTING",
        decisionEligible: false,
        biasAdjustment: null,
        correctionId: null,
        adoptionCriteria: {},
        adoptionCriteriaText: ["No adoption in this fixture"],
        validation: null,
        evaluation: null,
      },
      targets: [],
    })),
  );
  await context.route("**/api/demo/terminal/weather/shadow", (route) =>
    route.fulfill({
      json: {
        asOf: now,
        mode: "SHADOW_ONLY",
        decisionEligible: false,
        errorConvention: "forecast minus outcome",
        horizonDefinition: "Receipt-calendar horizon",
        selectionPolicy: "Latest prospective receipt",
        analysisVersion: "fixture-v1",
        reportId: "fixture-shadow-report",
        summary: {
          resolvedSnapshots: 24,
          qualifiedSnapshots: 24,
          independentTargets: 8,
          duplicateSnapshots: 16,
          excludedSnapshots: 0,
          contexts: 4,
          targetDates: 2,
          cohortMemberships: 8,
        },
        contexts,
        exclusions: [],
      },
    }),
  );
  await page.goto("/login");
  await page
    .getByRole("button", { name: `${workspace} demo`, exact: true })
    .click();
  await page.waitForURL(
    workspace === "Port" ? "**/port/overview" : "**/admin/radar",
  );
  await page.goto(workspace === "Port" ? "/port/weather" : "/admin/learning");
  await settle(page);
  const archive = page.getByTestId("weather-verification-chain");
  await expect(archive).toBeVisible();
  if (workspace === "Port") {
    const learning = archive.locator(
      "xpath=ancestor::section[contains(@class, 'panel')]",
    );
    expect(
      await learning.evaluate((element) => element.clientHeight),
    ).toBeGreaterThan(100);
    await archive
      .getByRole("combobox", {
        name: "Weather verification location",
        exact: true,
      })
      .scrollIntoViewIfNeeded();
    await expect(
      archive.getByRole("combobox", {
        name: "Weather verification location",
        exact: true,
      }),
    ).toBeInViewport();
  }
  await archive
    .getByRole("combobox", {
      name: "Weather verification location",
      exact: true,
    })
    .selectOption("INMAA");
  await expect(
    archive.getByRole("combobox", {
      name: "Weather verification location",
      exact: true,
    }),
  ).toHaveValue("INMAA");
  await archive
    .getByText("Inspect a matched forecast and later ERA5 outcome", {
      exact: true,
    })
    .click();
  await expect(page.getByTestId("weather-latest-matched-case")).toContainText(
    "INMAA · wind speed",
  );
  await archive
    .getByRole("button", {
      name: "Inspect matched forecast source response",
      exact: true,
    })
    .click();
  await expect(archive).toContainText('"sourceContext": "INMAA-wind_speed"');
  await page
    .getByRole("combobox", { name: "Weather feedback variable", exact: true })
    .selectOption("wind_gust");
  await expect(
    archive.getByRole("combobox", {
      name: "Weather verification location",
      exact: true,
    }),
  ).toHaveValue("INMAA");
  await expect(archive).not.toContainText(
    '"sourceContext": "INMAA-wind_speed"',
  );
  await archive
    .getByText("Inspect a matched forecast and later ERA5 outcome", {
      exact: true,
    })
    .click();
  await expect(page.getByTestId("weather-latest-matched-case")).toContainText(
    "INMAA · wind gust",
  );
  await archive
    .getByText("Matched error analysis and daily correction shadow readiness", {
      exact: true,
    })
    .click();
  const shadow = page.getByTestId("weather-shadow-analysis");
  await expect(
    shadow.getByRole("combobox", { name: "Port", exact: true }),
  ).toHaveValue("INMAA");
  await expect(
    shadow.getByRole("combobox", { name: "Variable", exact: true }),
  ).toHaveValue("wind_gust");
  await expect(
    shadow.getByRole("region", { name: "Selected shadow context" }),
  ).toContainText("INMAA · wind gust");
  await expect(
    shadow.getByRole("region", { name: "Selected shadow context" }),
  ).not.toContainText("INNSA");
}

test("archive location survives variable changes without mixing matched or shadow context", async ({
  context,
  page,
}) => {
  await verifyArchive({ context, page }, "Admin");
});

test("Port Weather learning is reachable inside the original sidebar", async ({
  context,
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name === "mobile390",
    "The preserved Port Weather sidebar uses its desktop layout; mobile inspector is checked separately.",
  );
  await verifyArchive({ context, page }, "Port");
});
