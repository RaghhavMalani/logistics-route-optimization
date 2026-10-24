import fs from "node:fs";
import type { BrowserContext, Page } from "@playwright/test";
import { ACCOUNTS, expect, settle, test } from "../harness";
import type { CreateDecisionPayload } from "@/services/decisions";
import type { DecisionProblem } from "@/types/decisions";
import type {
  CurrentEnvironment,
  FrozenEnvironment,
} from "@/services/current-inputs";

// Presentation fixtures only. No fixture enters the weather ledger or claims a
// live provider measurement, simulated sailing result, or operational saving.
const at = (offsetHours: number) =>
  new Date(
    Math.ceil(Date.now() / 3600000) * 3600000 + offsetHours * 3600000,
  ).toISOString();

async function companyCurrentInputs(context: BrowserContext, page: Page) {
  const now = Date.now();
  // Demo adapters prefix the original contracts. Replay those same retained
  // presentation fixtures as well as the harness's unprefixed API paths.
  await context.route("**/api/demo/terminal/**", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const relative = new URL(route.request().url()).pathname.split(
      "/demo/terminal/",
    )[1];
    const fixture = new URL(
      `../fixtures/${relative?.replaceAll("/", "_")}.json`,
      import.meta.url,
    );
    if (!fs.existsSync(fixture)) return route.fallback();
    return route.fulfill({
      contentType: "application/json",
      body: fs.readFileSync(fixture, "utf8"),
    });
  });
  await context.route("**/api/demo/session", (route) =>
    route.fulfill({
      json: {
        user: ACCOUNTS.SHIPPING_COMPANY,
        mode: "demo",
        accessToken: "qa-passage-fixture",
        issuedAt: new Date(now).toISOString(),
        expiresAt: new Date(now + 3600000).toISOString(),
      },
    }),
  );
  const fleet = JSON.parse(
    fs.readFileSync(
      new URL("../fixtures/company_fleet.json", import.meta.url),
      "utf8",
    ),
  );
  fleet.vessels = fleet.vessels
    .slice(0, 2)
    .map((v: Record<string, unknown>, index: number) => ({
      ...v,
      eta: at(12 + index),
      destination_port: "INNSA",
    }));
  await context.route(
    (url) => url.pathname.endsWith("/api/demo/terminal/company/fleet"),
    (route) => route.fulfill({ json: fleet }),
  );
  const environment: CurrentEnvironment = {
    portCode: "INNSA",
    sources: {
      surface: {
        status: "CURRENT",
        availableAt: at(-1),
        issuedAt: null,
        source: "SIMULATED presentation fixture",
      },
    },
    hourly: Array.from({ length: 36 }, (_, index) => ({
      validAt: at(index),
      wind_speed_10m: 8,
      wind_gusts_10m: index < 16 ? 20 : 10,
      precipitation: 0,
      visibility: 10000,
      wave_height: null,
    })),
    daily: [],
    regionalHazards: [],
  };
  await context.route("**/api/demo/terminal/intelligence/current?*", (route) =>
    route.fulfill({ json: environment }),
  );
  await context.route("**/api/demo/terminal/decisions/problems?*", (route) =>
    route.fulfill({ json: { problems: [], total: 0 } }),
  );
  await page.goto("/login");
  await page.getByRole("button", { name: "Company demo", exact: true }).click();
  await page.waitForURL("**/company/overview");
  await page.goto("/company/global-eye");
  await settle(page);
  await page
    .getByRole("button", { name: "Current weather decision", exact: true })
    .click();
  return page.getByRole("dialog", {
    name: "Current inputs for voyage planning",
  });
}

test("passage assumptions require deliberate selection; vessel changes reset them and default request stays bounded", async ({
  context,
  page,
}) => {
  const sent: CreateDecisionPayload[] = [];
  await context.route(
    "**/api/demo/terminal/decisions/problems",
    async (route) => {
      sent.push(route.request().postDataJSON());
      await route.fulfill({
        status: 422,
        json: { detail: "SIMULATED request captured; no decision persisted" },
      });
    },
  );
  const dialog = await companyCurrentInputs(context, page);
  await expect(dialog.getByTestId("passage-plan-inputs")).toContainText(
    "default compares arrival windows only",
  );
  await dialog
    .getByRole("button", {
      name: "Compare in the original decision panel",
      exact: true,
    })
    .click();
  await expect.poll(() => sent.length).toBe(1);
  expect(sent[0].currentArrival).not.toHaveProperty("passagePlan");
  await dialog
    .getByRole("checkbox", {
      name: "Include a declared remaining passage",
      exact: true,
    })
    .check();
  await dialog
    .getByRole("button", {
      name: "Use named simulated passage scenario",
      exact: true,
    })
    .click();
  await expect(
    dialog.getByRole("spinbutton", {
      name: "Baseline sailing speed (kn)",
      exact: true,
    }),
  ).toHaveValue("12");
  await expect(
    dialog.getByText("Delay original departure: unavailable", { exact: false }),
  ).toBeVisible();
  await dialog
    .getByRole("button", {
      name: "Compare in the original decision panel",
      exact: true,
    })
    .click();
  await expect.poll(() => sent.length).toBe(2);
  expect(sent[1].currentArrival?.passagePlan).toMatchObject({
    referenceKind: "AT_SEA",
    baselineSpeedKn: 12,
    minSpeedKn: 8,
    maxSpeedKn: 16,
  });
  expect(sent[1].currentArrival?.passagePlan).not.toHaveProperty("finance");
  const plan = sent[1].currentArrival!.passagePlan!;
  expect(plan.remainingDistanceNm / plan.baselineSpeedKn).toBeCloseTo(
    (Date.parse(plan.baselineArrivalAt!) - Date.parse(plan.referenceAt)) /
      3600000,
    4,
  );
  await dialog
    .getByText("Declare consumption and relevant rates (optional)", {
      exact: true,
    })
    .click();
  await dialog
    .getByRole("button", {
      name: "Use named illustrative consumption and price scenario",
      exact: true,
    })
    .click();
  await dialog
    .getByRole("spinbutton", { name: "Bunker price amount", exact: true })
    .fill("650");
  await dialog
    .getByRole("button", {
      name: "Compare in the original decision panel",
      exact: true,
    })
    .click();
  await expect.poll(() => sent.length).toBe(3);
  expect(sent[2].currentArrival?.passagePlan?.finance?.fuelPrice?.amount).toBe(
    650,
  );
  expect(
    sent[2].currentArrival?.passagePlan?.finance?.consumption
      ?.referencePropulsionTonnesPerDay,
  ).toBe(24);
  await dialog
    .getByRole("combobox", { name: "Current input voyage", exact: true })
    .selectOption("PWD-002");
  await expect(
    dialog.getByRole("checkbox", {
      name: "Include a declared remaining passage",
      exact: true,
    }),
  ).not.toBeChecked();
  await expect(
    dialog.getByRole("spinbutton", {
      name: "Bunker price amount",
      exact: true,
    }),
  ).toHaveCount(0);
});

test("original decision panel shows frozen passage timeline, deadline miss and unavailable cost without the legacy same-time claim", async ({
  context,
  page,
}) => {
  const frozen: FrozenEnvironment = {
    evidenceVersion: "current-weather-approach-v3",
    evidenceId: "qa-simulated-passage-evidence",
    snapshotId: "qa-fixture-snapshot",
    responseSha256: "a".repeat(64),
    portCode: "INNSA",
    voyageId: "PWD-001",
    issuedAt: null,
    observedAt: null,
    availableAt: at(-1),
    earliestVoyageArrival: at(12),
    plannedArrival: at(12),
    firstClearApproach: at(16),
    forecastGateWaitHours: 4,
    noWeatherGateWaitHours: 0,
    consumedForecasts: [],
    assumptions: {
      maxGustKn: 15,
      minVisibilityM: 5000,
      scope: "SIMULATED presentation fixture only",
    },
    meaning: "No measured shipping benefit.",
    passageComparison: {
      version: "declared-passage-v1",
      referenceAt: at(0),
      requestedApproachAt: at(12),
      baselineArrivalAt: at(12),
      distanceNm: 144,
      distanceBasis: "SIMULATED declared distance; not surveyed geometry",
      geometryBasis: "Geometry unavailable; original map remains",
      limitations: [
        "Unknown costs are not zero; no total or cheapest-plan claim.",
      ],
      options: [
        {
          optionId: "keep",
          label: "Continue declared passage",
          status: "FEASIBLE",
          speedKn: 12,
          departureAt: at(0),
          arrivalAt: at(12),
          approachClearAt: at(16),
          sailingHours: 12,
          departureHoldHours: 0,
          anchorageWaitHours: 4,
          totalElapsedHours: 16,
          scheduleShiftHours: 0,
          deadlineAt: at(17),
          deadlineMet: true,
        },
        {
          optionId: "slower",
          label: "Slower passage beyond deadline",
          status: "REJECTED",
          reason: "Declared onward deadline missed",
          speedKn: 8,
          departureAt: at(0),
          arrivalAt: at(18),
          approachClearAt: at(18),
          sailingHours: 18,
          departureHoldHours: 0,
          anchorageWaitHours: 0,
          totalElapsedHours: 18,
          scheduleShiftHours: 2,
          deadlineAt: at(17),
          deadlineMet: false,
        },
      ],
    },
  };
  const problem: DecisionProblem = {
    decisionId: "qa-simulated-passage",
    createdAt: at(0),
    domain: "VESSEL_ROUTING",
    worldRevision: {},
    worldStateId: "qa-fixture",
    subject: {
      type: "VESSEL",
      id: "PWD-001",
      label: "SIMULATED passage fixture",
    },
    actor: {
      role: "SHIPPING_COMPANY",
      organisation: "QA",
      portCode: null,
      vesselIds: ["PWD-001"],
    },
    attentionItemId: null,
    cascadeId: null,
    decisionDeadline: null,
    decisionWindowHours: null,
    at: at(0),
    objectives: [],
    hardConstraints: [],
    softConstraints: [],
    availableActions: [],
    baselineOptionId: null,
    options: [],
    frontier: null,
    recommendation: null,
    evidence: { currentEnvironment: frozen },
    headline: "SIMULATED fixture · inspect frozen consequences",
    doNothingStatement: "Fixture-only current plan",
    workflow: "COMPUTED",
    workflowHistory: [],
    humanChoice: null,
    notes: [],
    counts: { options: 0, feasible: 0, rejected: 0 },
  };
  await context.route("**/api/demo/terminal/decisions/problems", (route) =>
    route.fulfill({ json: problem }),
  );
  const dialog = await companyCurrentInputs(context, page);
  await dialog
    .getByRole("button", {
      name: "Compare in the original decision panel",
      exact: true,
    })
    .click();
  const panel = page.getByTestId("decision-panel");
  const comparison = panel.getByTestId("frozen-passage-comparison");
  await expect(comparison).toContainText("144.000 nm");
  await expect(comparison).toContainText("MISSES DECLARED DEADLINE");
  await expect(comparison).toContainText("+2.00 h");
  await expect(panel).not.toContainText(
    "both options reach the same clear approach time",
  );
  await expect(panel).not.toContainText("Overall approach timing is unchanged");
  await comparison
    .getByText(
      "Slower passage beyond deadline · inspect fuel, component costs and forecast hours",
      { exact: true },
    )
    .click();
  await expect(comparison).toContainText("Fuel unavailable");
  await expect(comparison).toContainText("Cost unavailable");
  // The broad table scrolls inside the original panel rather than widening it.
  const dimensions = await comparison
    .getByTestId("passage-schedule-table")
    .evaluate((table) => ({
      scroll: table.parentElement!.scrollWidth,
      width: table.parentElement!.clientWidth,
    }));
  expect(dimensions.scroll).toBeGreaterThanOrEqual(dimensions.width);
  await panel.getByRole("tab", { name: "Robust", exact: true }).click();
  const policy = panel.getByTestId("passage-policy-explanation");
  await expect(policy).toContainText("Insufficient basis");
  await expect(policy).toContainText(
    "Closure-duration stress horizons are not used",
  );
  await expect(policy).not.toContainText(
    "Both options reach the same forecast-clear",
  );
});
