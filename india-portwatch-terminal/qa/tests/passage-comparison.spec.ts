import fs from "node:fs";
import type { BrowserContext, Locator, Page } from "@playwright/test";
import { ACCOUNTS, expect, settle, test } from "../harness";
import type { CreateDecisionPayload } from "@/services/decisions";
import type {
  DecisionOption,
  DecisionProblem,
  FinancialEvaluation,
} from "@/types/decisions";
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

async function companyCurrentInputs(
  context: BrowserContext,
  page: Page,
  savedProblems: () => DecisionProblem[] = () => [],
) {
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
    route.fulfill({
      json: { problems: savedProblems(), total: savedProblems().length },
    }),
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

// Typed presentation fixtures exercise the real inspector and shared selection.
// Values below are intentionally synthetic; none are persisted to a provider or
// learning ledger. Backend arithmetic/recovery suites verify the actual engine.
function passageFixture(
  mode: "supported" | "deadline" | "missing" | "unpriced" = "supported",
): DecisionProblem {
  const rejected = mode === "deadline";
  const missing = mode === "missing";
  const unpriced = missing || mode === "unpriced";
  const alternativeLabel = "Slower declared passage";
  const reason =
    "Declared clear-approach deadline missed; lower modeled fuel does not override the deadline.";
  const finance = (tonnes: number): FinancialEvaluation => ({
    currency: "USD",
    complete: false,
    total: null,
    partialTotal: unpriced ? null : { amount: tonnes * 600, currency: "USD" },
    components: [
      {
        key: "fuel",
        label: "Modeled fuel component",
        state: unpriced ? "UNKNOWN" : "KNOWN",
        money: unpriced ? null : { amount: tonnes * 600, currency: "USD" },
        quantity: missing ? null : { value: tonnes, unit: "tonne" },
        rate: null,
        basis: "SIMULATED declared consumption and USD600/tonne assumption",
        reason: missing
          ? "Consumption and price unavailable"
          : unpriced
            ? "Bunker price unavailable; modeled fuel retained"
            : "",
        isAssumption: true,
        sourceType: "USER_ASSUMPTION",
        driver: "fuel",
      },
      {
        key: "port",
        label: "Port and onward charges",
        state: "UNKNOWN",
        money: null,
        quantity: null,
        rate: null,
        basis: "",
        reason: "Port, cargo and onward contract inputs unavailable",
        isAssumption: false,
        sourceType: null,
        driver: null,
      },
    ],
    unknown: [
      ...(unpriced
        ? [
            {
              key: "fuel",
              label: "Modeled fuel component",
              reason: missing
                ? "Consumption and price unavailable"
                : "Bunker price unavailable",
            },
          ]
        : []),
      {
        key: "port",
        label: "Port and onward charges",
        reason: "Port, cargo and onward contract inputs unavailable",
      },
    ],
    assumption: true,
    label: "ASSUMPTION",
    sourceTypes: ["USER_ASSUMPTION"],
    fxUsed: [],
    range: null,
    notes: ["Partial components are not complete voyage savings."],
  });
  const frozen: FrozenEnvironment = {
    evidenceVersion: "current-weather-passage-v3",
    evidenceId: "qa-simulated-immutable-passage-evidence",
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
    consumedForecasts: [
      {
        validAt: at(16),
        wind_speed_10m: 8,
        wind_gusts_10m: 10,
        precipitation: 0,
        visibility: 10000,
        wave_height: null,
      },
    ],
    assumptions: {
      maxGustKn: 15,
      minVisibilityM: 5000,
      scope: "SIMULATED port-approach fixture; no whole-route safety claim",
    },
    meaning:
      "Conditional approach, not clearance, berth confirmation or measured benefit.",
    passageComparison: {
      version: "declared-passage-v1",
      inputVersion: "b".repeat(64),
      referenceAt: at(0),
      requestedApproachAt: at(12),
      baselineArrivalAt: at(12),
      distanceNm: 144,
      distanceBasis: "SIMULATED declared scalar distance; not observed AIS",
      geometryBasis: "Geometry unavailable; no observed route is established",
      limitations: [
        "Unknown costs are not zero; no total savings or cheapest-plan claim.",
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
          requestedWindowWaitHours: 0,
          forecastGateWaitHours: 4,
          totalElapsedHours: 16,
          scheduleShiftHours: 0,
          deadlineAt: at(17),
          deadlineMet: true,
        },
        {
          optionId: "slower",
          label: alternativeLabel,
          status: rejected ? "REJECTED" : "FEASIBLE",
          reason: rejected ? reason : undefined,
          speedKn: rejected ? 8 : 9,
          departureAt: at(0),
          arrivalAt: at(rejected ? 18 : 16),
          approachClearAt: at(rejected ? 18 : 16),
          sailingHours: rejected ? 18 : 16,
          departureHoldHours: 0,
          anchorageWaitHours: 0,
          requestedWindowWaitHours: 0,
          forecastGateWaitHours: 0,
          totalElapsedHours: rejected ? 18 : 16,
          scheduleShiftHours: rejected ? 2 : 0,
          deadlineAt: at(17),
          deadlineMet: !rejected,
        },
      ],
    },
  };
  const totals = [
    13.333333333333334,
    rejected ? 6.833333333333333 : 8.083333333333334,
  ];
  const options: DecisionOption[] = frozen.passageComparison!.options.map(
    (item, index) => {
      if (!missing) {
        item.fuel = {
          version: "qa-simulated-consumption-v1",
          available: true,
          totalTonnes: totals[index],
          unit: "tonne",
          modes: {},
          formula:
            "[24 t/day × (speed / 12 kn)^3 + 2 t/day] × sailing hours / 24; anchorage 2 t/day separately",
          consumption: {
            source: "SIMULATED operator declaration",
            declaredAt: at(0),
            loadCondition: "SIMULATED load",
          },
          missingInputs: [],
          meaning:
            "Modeled fuel under declared assumptions; not measured fuel.",
          assumptions: [
            "SIMULATED consumption; scalar distance has no geometry.",
          ],
        };
      }
      item.finance = finance(totals[index]);
      return {
        optionId: item.optionId,
        action: index === 0 ? "KEEP_PLAN" : "SLOW_STEAM",
        label: item.label,
        actor: "SHIPPING_COMPANY",
        params: { speedKn: item.speedKn },
        availability: {
          status: "AVAILABLE",
          reason: "SIMULATED presentation fixture",
        },
        constraints: [],
        rejectedBy:
          index === 1 && rejected
            ? [
                {
                  key: "declared_deadline",
                  label: "Declared deadline",
                  passed: false,
                  hard: true,
                  detail: reason,
                  basis: "Frozen fixture deadline",
                },
              ]
            : [],
        status: index === 1 && rejected ? "REJECTED" : "FEASIBLE",
        feasible: !(index === 1 && rejected),
        isBaseline: index === 0,
        evaluation: {
          objectives: {},
          consequences: [],
          derived: {},
          financial: item.finance,
          branchId: null,
          notes: ["SIMULATED presentation fixture only"],
          computedAt: at(0),
          weakestConfidence: null,
        },
        assumptions: [],
        provenance: {},
        critic: {
          verdict: "PASS_WITH_WARNINGS",
          checks: [],
          failed: [],
          reasons: [],
          warnings: [],
          blocking: [],
          ranAt: at(0),
        },
        geometry: null,
        timeline: [
          {
            kind: "position",
            subject: "Declared scalar reference",
            hours: 0,
            at: at(0),
          },
          {
            kind: "arrival",
            subject: "Physical approach arrival",
            hours: item.sailingHours!,
            at: item.arrivalAt!,
          },
          {
            kind: "arrival",
            subject: "Conditional clear approach",
            hours: item.totalElapsedHours!,
            at: item.approachClearAt!,
          },
        ],
      };
    },
  );
  return {
    decisionId: `qa-simulated-passage-${mode}`,
    createdAt: at(0),
    domain: "VESSEL_ROUTING",
    worldRevision: {},
    worldStateId: "qa-fixture",
    subject: {
      type: "VESSEL",
      id: "PWD-001",
      label:
        "SIMULATED passage fixture with a long operator voyage name for wrapping",
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
    baselineOptionId: "keep",
    options,
    frontier: null,
    recommendation: {
      optionId: rejected || missing ? "keep" : "slower",
      actor: "SHIPPING_COMPANY",
      kind: rejected || missing ? "KEEP_CURRENT_PLAN" : "ACT",
      policy: "balanced-v1",
      provisionalOptionId: null,
      rankingBasis: {},
      againstBaseline: {},
      critic: null,
      expectedAvoidableCost: {
        available: false,
        reason: "Incomplete voyage cost",
      },
      robustness: null,
      why: "SIMULATED frozen constraints and declared consumption",
      // Retained legacy text deliberately has floating-point noise. The new
      // structured summary must be readable while this text stays inspectable.
      statement: rejected
        ? "KEEP CURRENT PLAN: alternative misses declared deadline by 1.0000000000000002 hours."
        : missing
          ? "KEEP CURRENT PLAN: consumption is unavailable; fuel is not zero."
          : "Slower passage has 8.083333333333334 modeled tonnes and 0.0000000000000000 hours schedule shift.",
    },
    evidence: {
      currentEnvironment: frozen,
      execution: { by: "PORT_AUTHORITY", mechanism: "ISSUE_ADVISORY" },
    },
    headline: "SIMULATED fixture · inspect conditional approach consequences",
    doNothingStatement:
      "Fixture current plan remains subject to declared hourly approach assumptions.",
    workflow: "COMPUTED",
    workflowHistory: [],
    humanChoice: null,
    notes: [],
    counts: {
      options: 2,
      feasible: rejected ? 1 : 2,
      rejected: rejected ? 1 : 0,
    },
  };
}

async function decisionStore(
  context: BrowserContext,
  problem: DecisionProblem,
) {
  let current = structuredClone(problem);
  const writes: Array<Record<string, unknown>> = [];
  let refreshFailure = false;
  await context.route("**/api/demo/terminal/decisions/problems", (route) => {
    writes.push(route.request().postDataJSON());
    return route.fulfill({ json: current });
  });
  await context.route(
    `**/api/demo/terminal/decisions/problems/${problem.decisionId}`,
    (route) => route.fulfill({ json: current }),
  );
  await context.route(
    `**/api/demo/terminal/decisions/problems/${problem.decisionId}/transition`,
    (route) => {
      const body = route.request().postDataJSON();
      writes.push(body);
      current = {
        ...current,
        workflow: body.target,
        humanChoice: body.optionId ?? current.humanChoice,
        workflowHistory: [
          ...current.workflowHistory,
          {
            at: at(0),
            state: body.target,
            actor: "SIMULATED QA",
            optionId: body.optionId,
          },
        ],
      };
      return route.fulfill({ json: current });
    },
  );
  await context.route(
    `**/api/demo/terminal/decisions/problems/${problem.decisionId}/refresh`,
    (route) => {
      writes.push(route.request().postDataJSON());
      return route.fulfill(
        refreshFailure
          ? {
              status: 409,
              json: {
                detail:
                  "Retained evidence expired. Enter an updated passage declaration before creating a linked successor; archived forecasts are never re-dated.",
              },
            }
          : {
              json: {
                ...current,
                decisionId: `${current.decisionId}-successor`,
              },
            },
      );
    },
  );
  return {
    get current() {
      return current;
    },
    writes,
    failRefresh() {
      refreshFailure = true;
    },
  };
}

async function openFixture(
  context: BrowserContext,
  page: Page,
  problem: DecisionProblem,
) {
  const store = await decisionStore(context, problem);
  const dialog = await companyCurrentInputs(context, page);
  await dialog
    .getByRole("button", {
      name: "Compare in the original decision panel",
      exact: true,
    })
    .click();
  const panel = page.getByTestId("decision-panel");
  await expect(panel).toBeVisible();
  return {
    store,
    panel,
    summary: panel.getByTestId("passage-decision-summary"),
  };
}

async function noHorizontalOverflow(locator: Locator) {
  const dimensions = await locator.evaluate((element) => ({
    content: element.scrollWidth,
    width: element.clientWidth,
  }));
  expect(dimensions.width).toBeGreaterThan(0);
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.width + 1);
}

async function notCovered(locator: Locator) {
  await locator.scrollIntoViewIfNeeded();
  expect(
    await locator.evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      const hit = document.elementFromPoint(
        bounds.left + bounds.width / 2,
        bounds.top + bounds.height / 2,
      );
      return hit === element || (hit !== null && element.contains(hit));
    }),
  ).toBe(true);
}

test("supported passage is result-first, selection stays connected and each tab/action is promptly accessible", async ({
  context,
  page,
}) => {
  const { panel, summary, store } = await openFixture(
    context,
    page,
    passageFixture(),
  );
  await expect(summary).toBeVisible();
  const core = summary.getByTestId("passage-core-comparison");
  await noHorizontalOverflow(core);
  await noHorizontalOverflow(summary);
  const summaryWidth = await summary.evaluate((element) => element.clientWidth);
  expect((await core.boundingBox())!.width).toBeLessThanOrEqual(
    summaryWidth + 1,
  );
  await expect(
    core.getByRole("row", { name: /conditional clear approach/i }),
  ).toBeInViewport();
  for (const measure of [/anchorage waiting/i, /modeled fuel/i]) {
    const row = core.getByRole("row", { name: measure });
    await row.scrollIntoViewIfNeeded();
    await expect(row).toBeInViewport();
  }
  await expect(summary).toContainText(/same conditional clear.approach time/i);
  await expect(summary).toContainText(/13\.33/);
  await expect(summary).toContainText(/8\.08/);
  await expect(summary).toContainText(/partial/i);
  await expect(summary).not.toContainText("8.083333333333334");
  await expect(
    page.getByRole("button", { name: "Current weather decision", exact: true }),
  ).toHaveCount(0);
  const current = summary.getByRole("button", {
    name: "Select current plan",
    exact: true,
  });
  const slower = summary.getByRole("button", {
    name: "Select Slower declared passage",
    exact: true,
  });
  await notCovered(current);
  await current.click();
  await expect(current).toHaveAttribute("aria-pressed", "true");
  await expect(summary).toHaveAttribute("data-selected-option", "keep");
  await slower.click();
  await expect(slower).toHaveAttribute("aria-pressed", "true");
  await expect(summary).toHaveAttribute("data-selected-option", "slower");

  const edit = panel.getByRole("button", {
    name: "Edit inputs / saved comparisons",
    exact: true,
  });
  await notCovered(edit);
  await edit.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", {
    name: "Current inputs for voyage planning",
  });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Tab");
  expect(
    await dialog.evaluate((element) =>
      element.contains(document.activeElement),
    ),
  ).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(edit).toBeFocused();

  const archive = panel.getByText("Full passage schedule and evidence", {
    exact: true,
  });
  await expect(panel.getByTestId("passage-schedule-table")).toBeHidden();
  await archive.focus();
  await page.keyboard.press("Enter");
  const schedule = panel.getByTestId("passage-schedule-table");
  await expect(schedule).toBeVisible();
  const scroller = schedule.locator("..");
  await expect(scroller).toHaveAttribute("tabindex", "0");
  await expect(scroller).toHaveAttribute("aria-label", /.+/);
  await scroller.focus();
  await page.keyboard.press("ArrowRight");
  await expect
    .poll(() => scroller.evaluate((element) => element.scrollLeft))
    .toBeGreaterThan(0);
  await archive.focus();
  await page.keyboard.press("Enter");
  await expect(schedule).toBeHidden();

  await panel.getByRole("tab", { name: "Timeline", exact: true }).click();
  await expect(panel.getByTestId("decision-timeline")).toBeVisible();
  await expect(panel.getByTestId("frozen-weather-basis")).toHaveCount(0);
  await panel
    .getByTestId("timeline-row")
    .filter({ has: page.locator('[data-mark="arrival"]') })
    .first()
    .click();
  await panel.getByRole("tab", { name: /^Options/, exact: false }).click();
  await expect(summary).toHaveAttribute("data-selected-option", "keep");
  await slower.click();

  await panel.getByRole("tab", { name: "Money", exact: true }).click();
  const money = panel.getByTestId("financial-evidence");
  await expect(money).toBeVisible();
  await expect(money).toContainText("Total unknown");
  await expect(panel.getByTestId("frozen-weather-basis")).toHaveCount(0);
  await panel.getByRole("tab", { name: "Why", exact: true }).click();
  const evidence = panel.getByText("Frozen weather and passage evidence", {
    exact: true,
  });
  await expect(evidence).toBeVisible();
  await expect(panel.getByTestId("frozen-weather-basis")).toBeHidden();
  await panel.getByRole("tab", { name: "Robust", exact: true }).click();
  await expect(panel.getByTestId("passage-policy-explanation")).toContainText(
    "Closure-duration stress horizons are not used",
  );

  await panel.getByRole("tab", { name: "Options", exact: false }).click();
  await summary
    .getByRole("button", { name: "Continue to Decide", exact: true })
    .click();
  const review = panel.getByTestId("decision-review");
  await expect(review).toBeVisible();
  await notCovered(review);
  await review.click();
  const approve = panel.getByTestId("decision-approve");
  await expect(approve).toContainText("Slower declared passage");
  await notCovered(approve);
  await approve.click();
  expect(
    store.writes.find((write) => write.target === "APPROVED")?.optionId,
  ).toBe("slower");
  await expect(panel.getByTestId("decision-workflow")).toContainText(
    "Approved: Slower declared passage",
  );

  await panel.getByRole("tab", { name: "Options", exact: false }).click();
  // Text enlargement is confined to the test page, preserving the actual
  // inspector width. Vertical growth is allowed; core horizontal scrolling is not.
  await page.addStyleTag({
    content:
      '[data-testid="passage-decision-summary"], [data-testid="passage-decision-summary"] * { font-size: 24px !important; line-height: 1.4 !important; }',
  });
  await noHorizontalOverflow(core);
  await noHorizontalOverflow(summary);
});

test("lower modeled fuel cannot hide a declared deadline rejection", async ({
  context,
  page,
}) => {
  const { summary, panel } = await openFixture(
    context,
    page,
    passageFixture("deadline"),
  );
  await expect(summary).toContainText(/KEEP CURRENT PLAN/i);
  await expect(summary).toContainText(/miss.*deadline/i);
  await expect(summary).toContainText(
    "lower modeled fuel does not override the deadline",
  );
  await expect(summary).toContainText("6.83");
  await expect(
    summary.getByRole("button", {
      name: "Select Slower declared passage",
      exact: true,
    }),
  ).toBeDisabled();
  const current = summary.getByRole("button", {
    name: "Select current plan",
    exact: true,
  });
  await expect(current).toBeEnabled();
  await current.click();
  await summary
    .getByRole("button", { name: "Continue to Decide", exact: true })
    .click();
  await panel.getByTestId("decision-review").click();
  await expect(panel.getByTestId("decision-approve")).toHaveText(
    "Approve current plan",
  );
});

test("insufficient approach coverage cannot invent a recommendation or enable approval", async ({
  context,
  page,
}) => {
  const problem = passageFixture("deadline");
  const frozen = problem.evidence.currentEnvironment as FrozenEnvironment;
  const reason =
    "Hourly approach coverage is unavailable for this option; fresh evidence is required.";
  problem.recommendation = null;
  problem.counts = { options: 2, feasible: 0, rejected: 2 };
  frozen.firstClearApproach = "";
  frozen.passageComparison!.options.forEach((option) => {
    option.status = "REJECTED";
    option.reason = reason;
    option.approachClearAt = null;
    option.anchorageWaitHours = null;
    option.scheduleShiftHours = null;
    option.deadlineMet = null;
    delete option.fuel;
    option.finance = null;
  });
  problem.options.forEach((option) => {
    option.status = "REJECTED";
    option.feasible = false;
    option.evaluation = null;
    option.timeline = [];
    option.rejectedBy = [
      {
        key: "hourly_coverage",
        label: "Hourly coverage",
        passed: false,
        hard: true,
        detail: reason,
        basis: "SIMULATED missing forecast hours",
      },
    ];
  });
  const { panel, summary } = await openFixture(context, page, problem);
  await expect(summary).toContainText(/insufficient basis/i);
  await expect(summary).toContainText(reason);
  await expect(
    summary.getByRole("button", { name: "Select current plan", exact: true }),
  ).toBeDisabled();
  await expect(
    summary.getByRole("button", {
      name: "Select Slower declared passage",
      exact: true,
    }),
  ).toBeDisabled();
  await summary
    .getByRole("button", { name: "Continue to Decide", exact: true })
    .click();
  await panel.getByTestId("decision-review").click();
  await expect(panel.getByTestId("decision-approve")).toBeDisabled();
});

test("a rejected departure option keeps its decisive reason visible while another alternative is selected", async ({
  context,
  page,
}) => {
  const problem = passageFixture();
  const frozen = problem.evidence.currentEnvironment as FrozenEnvironment;
  const comparison = frozen.passageComparison!;
  frozen.earliestVoyageArrival = frozen.plannedArrival = at(13);
  frozen.firstClearApproach = at(17);
  frozen.passagePlan = {
    schemaVersion: 1,
    referenceKind: "NOT_DEPARTED",
    referenceAt: at(1),
    referenceLabel: "SIMULATED future declared departure",
    declaredAt: at(0),
    remainingDistanceNm: 144,
    distanceBasis: "SIMULATED declared scalar distance; not observed AIS",
    baselineSpeedKn: 12,
    minSpeedKn: 8,
    maxSpeedKn: 16,
    alternativeSpeedKn: 9,
    baselineArrivalAt: at(13),
    deadlineAt: at(18),
    departureDelayHours: 8,
    departureHoldPermitted: true,
    departureHoldLocation: "SIMULATED explicitly permitted holding location",
  };
  comparison.referenceAt = at(1);
  comparison.requestedApproachAt = at(13);
  comparison.baselineArrivalAt = at(13);
  comparison.options.forEach((option, index) => {
    option.departureAt = at(1);
    option.arrivalAt = at(index === 0 ? 13 : 17);
    option.approachClearAt = at(17);
    option.deadlineAt = at(18);
  });
  const rejection =
    "Permitted departure holding misses the declared clear-approach deadline; choose a fresh plan instead.";
  comparison.options.push({
    ...structuredClone(comparison.options[0]),
    optionId: "departure-hold",
    label: "Delayed departure beyond deadline",
    status: "REJECTED",
    reason: rejection,
    departureAt: at(9),
    arrivalAt: at(21),
    approachClearAt: at(21),
    departureHoldHours: 8,
    anchorageWaitHours: 0,
    totalElapsedHours: 20,
    scheduleShiftHours: 4,
    deadlineMet: false,
  });
  problem.options.push({
    ...structuredClone(problem.options[0]),
    optionId: "departure-hold",
    action: "DELAY_DEPARTURE",
    label: "Delayed departure beyond deadline",
    params: { departureDelayHours: 8 },
    isBaseline: false,
    status: "REJECTED",
    feasible: false,
    rejectedBy: [
      {
        key: "declared_deadline",
        label: "Declared deadline",
        passed: false,
        hard: true,
        detail: rejection,
        basis: "SIMULATED frozen deadline",
      },
    ],
  });
  problem.counts = { options: 3, feasible: 2, rejected: 1 };
  const { summary } = await openFixture(context, page, problem);
  await expect(summary).toHaveAttribute("data-selected-option", "slower");
  await expect(summary).toContainText(rejection);
  await expect(
    summary.getByRole("button", {
      name: "Select Delayed departure beyond deadline",
      exact: true,
    }),
  ).toBeDisabled();
  await summary
    .getByRole("button", { name: "Select current plan", exact: true })
    .click();
  await expect(summary).toContainText(rejection);
  await summary
    .getByRole("button", {
      name: "Select Slower declared passage",
      exact: true,
    })
    .click();
  await expect(summary).toContainText(rejection);
  await noHorizontalOverflow(summary.getByTestId("passage-core-comparison"));
});

test("missing consumption and price retain useful schedule values without invented zero fuel or savings", async ({
  context,
  page,
}) => {
  const { panel, summary } = await openFixture(
    context,
    page,
    passageFixture("missing"),
  );
  await expect(summary).toContainText(/same conditional clear.approach time/i);
  await expect(summary).toContainText(/unavailable/i);
  const table = summary.getByTestId("passage-core-comparison");
  await expect(table.getByRole("row", { name: /modeled fuel/i })).toContainText(
    /unavailable/i,
  );
  await expect(table).not.toContainText("0.00 t");
  await noHorizontalOverflow(table);
  await panel.getByRole("tab", { name: "Money", exact: true }).click();
  await expect(panel.getByTestId("financial-evidence")).toContainText(
    "Total unknown",
  );
  await expect(panel.getByTestId("financial-evidence")).toContainText(
    "Consumption and price unavailable",
  );
});

test("missing price preserves modeled fuel while component money remains unavailable", async ({
  context,
  page,
}) => {
  const { panel, summary } = await openFixture(
    context,
    page,
    passageFixture("unpriced"),
  );
  const table = summary.getByTestId("passage-core-comparison");
  await expect(table.getByRole("row", { name: /modeled fuel/i })).toContainText(
    "8.08",
  );
  await expect(
    table.getByRole("row", { name: /component costs/i }),
  ).toContainText(/unavailable/i);
  await panel.getByRole("tab", { name: "Money", exact: true }).click();
  await expect(panel.getByTestId("financial-evidence")).toContainText(
    "Bunker price unavailable",
  );
  await expect(panel.getByTestId("financial-evidence")).toContainText(
    "Total unknown",
  );
});

test("saved approved comparison resumes immutable evidence and chosen option after reload", async ({
  context,
  page,
}) => {
  const problem = passageFixture();
  problem.workflow = "APPROVED";
  problem.humanChoice = "keep";
  problem.workflowHistory = [
    {
      at: at(0),
      state: "APPROVED",
      actor: "SIMULATED reviewer",
      optionId: "keep",
    },
  ];
  const originalEvidence = JSON.stringify(problem.evidence);
  const store = await decisionStore(context, problem);
  const dialog = await companyCurrentInputs(context, page, () => [
    store.current,
  ]);
  await dialog
    .getByRole("button", { name: "Resume saved comparison", exact: true })
    .click();
  const panel = page.getByTestId("decision-panel");
  await expect(panel.getByTestId("passage-decision-summary")).toHaveAttribute(
    "data-selected-option",
    "keep",
  );
  await panel.getByRole("tab", { name: "Decide", exact: true }).click();
  await expect(panel.getByTestId("decision-workflow")).toContainText(
    "Approved: Continue declared passage",
  );
  await page.reload();
  await settle(page);
  // World selection is local and may reset on a complete reload. Resume via
  // the durable saved-comparison action rather than manufacture a new decision.
  const existingEdit = page.getByRole("button", {
    name: "Edit inputs / saved comparisons",
    exact: true,
  });
  if (await existingEdit.isVisible()) await existingEdit.click();
  else
    await page
      .getByRole("button", { name: "Current weather decision", exact: true })
      .click();
  await page
    .getByRole("dialog", { name: "Current inputs for voyage planning" })
    .getByRole("button", { name: "Resume saved comparison", exact: true })
    .click();
  await expect(panel.getByTestId("passage-decision-summary")).toHaveAttribute(
    "data-selected-option",
    "keep",
  );
  expect(JSON.stringify(store.current.evidence)).toBe(originalEvidence);
  expect(store.current.humanChoice).toBe("keep");
  expect(store.writes).toHaveLength(0);
});

for (const version of ["v1", "v2"] as const) {
  test(`legacy ${version} arrival-only records render without passage assumptions and expired evidence offers explicit refresh guidance`, async ({
    context,
    page,
  }) => {
    const old = passageFixture();
    old.decisionId = `qa-retained-arrival-${version}`;
    const weather = old.evidence.currentEnvironment as FrozenEnvironment;
    delete weather.passageComparison;
    weather.evidenceVersion = `current-weather-approach-${version}`;
    old.recommendation = null;
    const evidenceBefore = JSON.stringify(old.evidence);
    const store = await decisionStore(context, old);
    store.failRefresh();
    const dialog = await companyCurrentInputs(context, page, () => [
      store.current,
    ]);
    await dialog
      .getByRole("button", { name: "Resume saved comparison", exact: true })
      .click();
    const panel = page.getByTestId("decision-panel");
    await expect(panel.getByTestId("passage-decision-summary")).toHaveCount(0);
    await expect(panel).toContainText(/assumed anchorage waiting/i);
    await expect(panel).not.toContainText("144.000 nm");
    await panel
      .getByRole("button", {
        name: "Edit inputs / saved comparisons",
        exact: true,
      })
      .click();
    const editor = page.getByRole("dialog", {
      name: "Current inputs for voyage planning",
    });
    await editor
      .getByRole("button", {
        name: "Refresh to linked comparison",
        exact: true,
      })
      .click();
    await expect(editor.getByRole("alert")).toContainText(
      "Retained evidence expired",
    );
    await expect(editor.getByRole("alert")).toContainText(
      "archived forecasts are never re-dated",
    );
    expect(JSON.stringify(store.current.evidence)).toBe(evidenceBefore);
    await page.keyboard.press("Escape");
    await expect(editor).toBeHidden();
  });
}
