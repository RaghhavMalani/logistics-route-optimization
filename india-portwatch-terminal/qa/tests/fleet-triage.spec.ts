import fs from "node:fs";
import type { BrowserContext, Page } from "@playwright/test";
import { ACCOUNTS, expect, mockApi, settle, test } from "../harness";
import type {
  FleetDecisionRow,
  FleetDecisionTriage,
} from "@/services/rolling-intelligence";
import type { DecisionProblem, Measure } from "@/types/decisions";

// Deliberately fictional presentation contracts. No fixture is written to a
// source/visitor ledger or scored as an operational observation.
const at = (hours = 0) => new Date(Date.now() + hours * 3600000).toISOString();
// Construct request URLs independently of the Vite API module. The queue's
// own generated links are exercised by clicking them in the navigation case.
const FLEET_TRIAGE_CATEGORIES = [
  "CURRENT_CONDITIONAL_FAILURE",
  "REASSESSMENT",
  "COMPANY_ACTION",
  "WAITING_OTHER_ROLE",
  "INCOMPLETE_ASSESSMENT",
  "MONITORED",
] as const;
const fleetReviewHash = (input: {
  kind: "SAVED_COMPARISON" | "CURRENT_INPUTS";
  vesselId: string;
  decisionId?: string;
  optionId?: string;
  episodeId?: string;
}) => {
  const { kind, ...query } = input;
  return `${kind === "SAVED_COMPARISON" ? "fleet-review" : "current-inputs"}?${new URLSearchParams(query)}`;
};
const reason = (code: string, text: string) => ({
  code,
  text,
  basis: "SIMULATED retained presentation contract",
});

test("source changes retain exact revisions and keep Company source responsibility separate from Vessel workflow", async ({
  browser,
  context,
  page,
}, info) => {
  const item = row(1, "REASSESSMENT");
  item.workflow.stage = "AWAITING_VESSEL";
  item.workflow.nextRole = "VESSEL_OPERATOR";
  item.reasons = [
    reason(
      "INDIAN_SOURCE_REVISION_CHANGED",
      "Consumed navigation-aid context changed; explicitly review a successor.",
    ),
  ];
  item.freshness = {
    status: "REASSESSMENT",
    reasons: item.reasons,
    sourceChanges: [
      {
        code: "INDIAN_SOURCE_REVISION_CHANGED",
        text: "Review the changed source interpretation.",
        noticeId: "NHO_NAVAREA_VIII:609/25",
        consumedRevisionId: "synthetic-consumed-v1",
        currentRevisionId: "synthetic-retained-v2",
        consumedAvailableAt: at(-2),
        currentAvailableAt: at(-1),
        changes: [
          {
            field: "status",
            before: "REVIEW_CONTEXT",
            after: "SOURCE_NOTICE_CANCELLED",
          },
        ],
        unknown: "Actual navigation-aid restoration remains unverified.",
        nextAction:
          "Explicit successor review is required; earlier approval remains saved.",
      },
    ],
  };
  item.sourceReviews = [
    {
      noticeId: "NHO_NAVAREA_VIII:610/25",
      revisionId: "synthetic-other-v1",
      title: "Synthetic additional aid notice",
      sourceStatus: "CURRENT_PRODUCT_DATE",
      responsibleRole: "SHIPPING_COMPANY",
      passageAt: at(24),
      reason:
        "Declared current-call passage; this additional identity has not been consumed.",
      action: "Inspect source",
    },
  ];
  const data = projection([item]);
  const baseline = process.env.QA_REFERENCE_BASELINE;
  if (baseline) {
    if (new URL(baseline).hostname !== "127.0.0.1")
      throw new Error("Reference baseline must be an owned local application");
    const before = await browser.newContext({
      baseURL: baseline,
      viewport: page.viewportSize() ?? undefined,
    });
    await mockApi(before);
    const old = await before.newPage();
    await company(before, old, data);
    await old.getByRole("button", { name: /Fleet review queue/ }).click();
    await old
      .getByText("Reasons and retained plan basis", { exact: true })
      .click();
    await old.screenshot({
      path: info.outputPath("ui-before-source-change.png"),
    });
    await before.close();
  }
  const state = await company(context, page, data);
  await page.getByRole("button", { name: /Fleet review queue/ }).click();
  const dialog = page.getByTestId("company-fleet-triage");
  await expect(dialog).toContainText("AWAITING VESSEL · Next: Vessel");
  await expect(dialog).toContainText("Separate source review · Company");
  const source = dialog.getByRole("link", {
    name: "Inspect Synthetic additional aid notice",
  });
  await expect(source).toHaveAttribute(
    "href",
    "/company/global-eye#intelligence-review?noticeId=NHO_NAVAREA_VIII%3A610%2F25&vesselId=PWD-001",
  );
  await dialog
    .getByText("Reasons and retained plan basis", { exact: true })
    .click();
  const changes = dialog.getByRole("region", {
    name: "Consumed source changes",
  });
  await expect(changes).toContainText(
    "synthetic-consumed-v1 → retained revision synthetic-retained-v2",
  );
  await expect(changes).toContainText('Consumed: "REVIEW_CONTEXT"');
  await expect(changes).toContainText('Retained: "SOURCE_NOTICE_CANCELLED"');
  await changes.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("ui-after-source-change.png"),
  });
  await page.setViewportSize({ width: 844, height: 390 });
  await expect(changes).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: /Fleet review queue/ }),
  ).toBeFocused();
  expect(state.mutations).toEqual([]);
  expect(state.refreshingListings).toEqual([]);
});

function row(
  index = 1,
  category: FleetDecisionRow["primaryCategory"] = "COMPANY_ACTION",
): FleetDecisionRow {
  const vesselId = `PWD-${String(index).padStart(3, "0")}`;
  return {
    id: `triage-${index}`,
    vessel: { id: vesselId, name: `Fictional vessel ${index}` },
    destinationPort: "INNSA",
    episode: { id: `call-${index}`, voyageLegId: `leg-${index}` },
    currentPlan: {
      basis: "APPROVED",
      decisionId: `decision-${index}`,
      optionId: "keep",
      approvalStatus: "APPROVED",
    },
    recommendation: {
      decisionId: `decision-${index}`,
      optionId: "alternative",
    },
    workflow: {
      stage:
        category === "WAITING_OTHER_ROLE"
          ? "AWAITING_VESSEL"
          : "COMPANY_REVIEW",
      nextRole:
        category === "WAITING_OTHER_ROLE"
          ? "VESSEL_OPERATOR"
          : "SHIPPING_COMPANY",
      companyDecisionId: `decision-${index}`,
      portDecisionId: null,
      advisoryIds: [],
    },
    primaryCategory: category,
    reasons: [
      reason(
        "COMPANY_REVIEW_REQUIRED",
        `Specific retained review reason ${index}`,
      ),
    ],
    freshness: { status: "CURRENT", reasons: [] },
    deadline: null,
    cargo: null,
    navigation: {
      kind: "SAVED_COMPARISON",
      vesselId,
      decisionId: `decision-${index}`,
      optionId: "keep",
      episodeId: `call-${index}`,
    },
    candidateComparisons: [],
    missingCoverage: ["Terminal access is not established"],
    asOf: at(),
  };
}

function projection(rows: FleetDecisionRow[]): FleetDecisionTriage {
  return {
    policyVersion: "fleet-triage-v1",
    asOf: at(),
    counts: Object.fromEntries(
      FLEET_TRIAGE_CATEGORIES.map((category) => [
        category,
        rows.filter((item) => item.primaryCategory === category).length,
      ]),
    ),
    coverage: {
      ownedVoyages: rows.length,
      currentCalls: rows.length,
      assessedCurrentPlans: rows.length,
      retainedComparisons: 27,
      legacyComparisons: 0,
      snapshotConsistent: true,
    },
    rows,
    sourceLeads: [],
    sourceLeadCoverage: {
      status: "MISSING",
      checkedAt: null,
      reason: "No retained source lead; this is not evidence of a clear route.",
    },
  };
}

function savedProblem(
  vesselId = "PWD-001",
  episode = "call-1",
): DecisionProblem {
  const measure: Measure = {
    available: true,
    value: 0,
    unit: "hours",
    confidence: null,
    basis: "SIMULATED schedule",
    unknownBecause: null,
    attrs: {},
  };
  return {
    decisionId: "decision-1",
    createdAt: at(),
    domain: "VESSEL_ROUTING",
    worldRevision: { mode: "DEMO" },
    worldStateId: "fixture-world",
    subject: { type: "vessel", id: vesselId, label: "Fictional vessel 1" },
    actor: {
      role: "SHIPPING_COMPANY",
      organisation: "PortWatch Demo Shipping",
      portCode: null,
      vesselIds: [],
    },
    attentionItemId: null,
    cascadeId: null,
    decisionDeadline: null,
    decisionWindowHours: null,
    at: at(),
    objectives: [
      {
        key: "eta",
        label: "Clear approach",
        unit: "hours",
        direction: "min",
        description: "SIMULATED forecast gate",
      },
    ],
    hardConstraints: [],
    softConstraints: [],
    availableActions: [],
    baselineOptionId: "keep",
    options: ["keep", "alternative"].map((optionId, index) => ({
      optionId,
      action: index ? "DELAY_ARRIVAL" : "KEEP_PLAN",
      label: index
        ? "Unapproved recommended alternative"
        : "Frozen current plan",
      actor: "SHIPPING_COMPANY",
      params: { arrivalAt: at(24) },
      availability: { status: "AVAILABLE", reason: "SIMULATED contract" },
      constraints: [],
      rejectedBy: [],
      status: "FEASIBLE",
      feasible: true,
      isBaseline: index === 0,
      evaluation: {
        objectives: { eta: measure, port_wait: measure },
        consequences: [],
        derived: {
          approachClearAt: at(24),
          destinationPort: "INNSA",
          arrivalAt: at(24),
        },
        financial: null,
        branchId: null,
        notes: [],
        computedAt: at(),
        weakestConfidence: null,
      },
      assumptions: [],
      provenance: {},
      critic: null,
      geometry: null,
      timeline: [
        {
          kind: "arrival",
          hours: 24,
          at: at(24),
          subject: vesselId,
          label: "SIMULATED approach",
        },
      ],
    })),
    frontier: null,
    recommendation: {
      optionId: "alternative",
      actor: "SHIPPING_COMPANY",
      kind: "ACT",
      policy: "fixture",
      provisionalOptionId: null,
      rankingBasis: {},
      againstBaseline: {},
      critic: null,
      expectedAvoidableCost: { available: false },
      robustness: null,
      why: "SIMULATED candidate only",
      statement: "SIMULATED candidate only",
    },
    evidence: {
      currentEnvironment: {
        evidenceId: "fixture-evidence",
        snapshotId: "fixture-hourly",
        responseSha256: "a".repeat(64),
        portCode: "INNSA",
        voyageId: vesselId,
        issuedAt: null,
        observedAt: null,
        availableAt: at(),
        earliestVoyageArrival: at(24),
        plannedArrival: at(24),
        firstClearApproach: at(24),
        forecastGateWaitHours: 0,
        noWeatherGateWaitHours: 0,
        consumedForecasts: [],
        assumptions: {
          maxGustKn: 15,
          minVisibilityM: 5000,
          scope: "SIMULATED assumptions",
        },
        operationalEpisode: { id: episode, voyageLegId: "leg-1" },
        meaning: "SIMULATED presentation evidence; not an operational result",
      },
    },
    headline: "Fictional vessel 1 · retained forecast gate",
    doNothingStatement: "Retained current plan",
    workflow: "APPROVED",
    workflowHistory: [],
    humanChoice: "keep",
    notes: [],
    counts: { options: 2, feasible: 2, rejected: 0 },
  };
}

async function company(
  context: BrowserContext,
  page: Page,
  initial: FleetDecisionTriage,
) {
  let current = initial;
  let fail = false;
  let triageReads = 0;
  const decisionReads: string[] = [];
  const mutations: string[] = [];
  const refreshingListings: string[] = [];
  const now = Date.now();
  await context.route("**/api/demo/terminal/**", async (route) => {
    const relative = new URL(route.request().url()).pathname.split(
      "/demo/terminal/",
    )[1];
    if (route.request().method() !== "GET") {
      mutations.push(relative ?? "");
      return route.fallback();
    }
    if (relative === "intelligence/navigation-restrictions")
      refreshingListings.push(relative);
    const fixture = new URL(
      `../fixtures/${relative?.replaceAll("/", "_")}.json`,
      import.meta.url,
    );
    if (fs.existsSync(fixture))
      return route.fulfill({
        contentType: "application/json",
        body: fs.readFileSync(fixture, "utf8"),
      });
    return route.fallback();
  });
  await context.route("**/api/demo/session", (route) =>
    route.fulfill({
      json: {
        user: ACCOUNTS.SHIPPING_COMPANY,
        mode: "demo",
        demoId: "fixture-visitor-fleet",
        accessToken: "qa-fleet-fixture",
        issuedAt: new Date(now).toISOString(),
        expiresAt: new Date(now + 3600000).toISOString(),
      },
    }),
  );
  await context.route(
    "**/api/demo/terminal/company/decision-triage",
    (route) => {
      triageReads += 1;
      return route.fulfill(
        fail
          ? {
              status: 503,
              json: { detail: "SIMULATED projection unavailable" },
            }
          : { json: current },
      );
    },
  );
  await context.route("**/api/demo/terminal/decisions/problems/*", (route) => {
    const id = decodeURIComponent(
      new URL(route.request().url()).pathname.split("/").pop() ?? "",
    );
    decisionReads.push(id);
    return route.fulfill(
      id === "decision-1"
        ? { json: savedProblem() }
        : {
            status: 404,
            json: { detail: "No saved comparison in this visitor's records" },
          },
    );
  });
  await context.route("**/api/demo/terminal/decisions/problems?*", (route) =>
    route.fulfill({ json: { problems: [], total: 0 } }),
  );
  await context.route("**/api/demo/terminal/intelligence/current?*", (route) =>
    route.fulfill({
      json: {
        portCode: "INNSA",
        sources: {},
        hourly: [],
        daily: [],
        regionalHazards: [],
      },
    }),
  );
  await page.goto("/login");
  await page.getByRole("button", { name: "Company demo", exact: true }).click();
  await page.waitForURL("**/company/overview");
  await settle(page);
  return {
    get current() {
      return current;
    },
    replace(next: FleetDecisionTriage) {
      current = next;
    },
    fail() {
      fail = true;
    },
    decisionReads,
    mutations,
    refreshingListings,
    get triageReads() {
      return triageReads;
    },
  };
}

test("fleet worklist shows full counts, pages, overdue signs and scoped filtering without creating decisions or refreshing providers", async ({
  context,
  page,
}) => {
  const rows = Array.from({ length: 12 }, (_, index) =>
    row(
      index + 1,
      index < 2 ? "CURRENT_CONDITIONAL_FAILURE" : "COMPANY_ACTION",
    ),
  );
  rows[0].deadline = {
    at: at(-2),
    kind: "CARGO_LOADING_CUTOFF",
    hoursRemaining: -2,
    basis: "Declared scheduled cutoff, not an observed shipment miss",
  };
  rows[0].cargo = {
    mustMeet: true,
    status: "BLOCKED",
    timingStatus: "MISSES",
    slackHours: -3.5,
    cutoffAt: at(-2),
    unit: "hours",
    basis: "SIMULATED declared cutoff",
  };
  const state = await company(context, page, projection(rows));
  const trigger = page.getByRole("button", { name: /Fleet review queue/ });
  await trigger.click();
  const dialog = page.getByTestId("company-fleet-triage");
  await expect(dialog).toContainText("12 owned voyages");
  await expect(dialog).toContainText("27 retained comparisons inspected");
  await expect(dialog.getByTestId("fleet-triage-row")).toHaveCount(6);
  await expect(dialog).toContainText("-2 h remaining");
  await expect(dialog).toContainText("-3.5 h");
  await dialog.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(dialog).toContainText("Showing 7–12 of 12");
  await expect(dialog).toContainText("Fictional vessel 12");
  await dialog
    .getByRole("combobox", { name: "Fleet review category" })
    .selectOption("CURRENT_CONDITIONAL_FAILURE");
  await expect(dialog.getByTestId("fleet-triage-row")).toHaveCount(2);
  await expect(dialog).toContainText("Showing 1–2 of 2");
  for (const target of [dialog, dialog.getByTestId("fleet-triage-scroll")]) {
    const size = await target.evaluate((element) => ({
      width: element.clientWidth,
      content: element.scrollWidth,
    }));
    expect(size.content).toBeLessThanOrEqual(size.width + 1);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
  expect(state.mutations).toEqual([]);
  expect(state.refreshingListings).toEqual([]);
});

test("exact queue link restores human choice rather than recommendation and survives reload, selection changes and return", async ({
  context,
  page,
}) => {
  const state = await company(context, page, projection([row()]));
  await page.getByRole("button", { name: /Fleet review queue/ }).click();
  const dialog = page.getByTestId("company-fleet-triage");
  await dialog
    .getByRole("combobox", { name: "Fleet review category" })
    .selectOption("COMPANY_ACTION");
  await dialog
    .getByRole("link", { name: "Open saved comparison", exact: true })
    .click();
  const panel = page.getByTestId("decision-panel");
  await expect(panel).toHaveAttribute("data-decision", "decision-1");
  await expect(
    panel.locator('[data-testid="decision-option"][data-option="keep"]'),
  ).toHaveAttribute("data-selected", "true");
  await panel.getByRole("tab", { name: "Timeline", exact: true }).click();
  await expect(
    panel.locator('[data-testid="timeline-row"][data-option="keep"]'),
  ).toHaveAttribute("aria-pressed", "true");
  await panel
    .locator('[data-testid="timeline-row"][data-option="alternative"]')
    .click();
  await page.reload();
  await settle(page);
  await expect(panel).toHaveAttribute("data-decision", "decision-1");
  await expect(
    panel.locator('[data-testid="decision-option"][data-option="keep"]'),
  ).toHaveAttribute("data-selected", "true");
  await page
    .getByRole("link", { name: "Return to fleet review queue", exact: true })
    .click();
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole("combobox", { name: "Fleet review category" }),
  ).toHaveValue("COMPANY_ACTION");
  await expect(dialog.getByTestId("fleet-triage-row")).toHaveAttribute(
    "data-selected",
    "true",
  );
  await expect(dialog).toContainText("Plan: APPROVED · option keep");
  expect(state.decisionReads.every((id) => id === "decision-1")).toBe(true);
  expect(state.mutations).toEqual([]);
});

test("historical, missing and malformed saved links explain their exact failure without opening a newer case", async ({
  context,
  page,
}) => {
  await company(context, page, projection([row()]));
  await page.goto(
    `/company/global-eye#${fleetReviewHash({ kind: "SAVED_COMPARISON", vesselId: "PWD-001", decisionId: "decision-1", optionId: "keep", episodeId: "prior-call" })}`,
  );
  await expect(page.getByRole("alert")).toContainText(
    "historical or different call",
  );
  await expect(page.getByTestId("decision-panel")).toHaveCount(0);
  await page.goto(
    `/company/global-eye#${fleetReviewHash({ kind: "SAVED_COMPARISON", vesselId: "PWD-001", decisionId: "missing-case", optionId: "keep", episodeId: "call-1" })}`,
  );
  await expect(page.getByRole("alert")).toContainText(
    "No saved comparison in this visitor",
  );
  await expect(page.getByTestId("decision-panel")).toHaveCount(0);
  await page.goto(
    `/company/global-eye#${fleetReviewHash({ kind: "SAVED_COMPARISON", vesselId: "PWD-001", decisionId: "decision-1", optionId: "not-an-option", episodeId: "call-1" })}`,
  );
  await expect(page.getByRole("alert")).toContainText("exact retained option");
  await expect(page.getByTestId("decision-panel")).toHaveCount(0);
});

test("retained projection failure remains explicit and a workflow mutation invalidates the visitor worklist", async ({
  context,
  page,
}) => {
  const state = await company(context, page, projection([row()]));
  await page.getByRole("button", { name: /Fleet review queue/ }).click();
  const dialog = page.getByTestId("company-fleet-triage");
  const waiting = row(1, "WAITING_OTHER_ROLE");
  state.replace(projection([waiting]));
  const before = state.triageReads;
  await page.evaluate(() =>
    window.dispatchEvent(new Event("portwatch:workflow-changed")),
  );
  await expect.poll(() => state.triageReads).toBeGreaterThan(before);
  await expect(dialog).toContainText("Next: Vessel");
  state.fail();
  await dialog
    .getByRole("button", { name: "Refresh retained state", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Retaining the previous results",
  );
  await expect(dialog).toContainText("Fictional vessel 1");
  await expect(dialog).not.toContainText("No retained rows in this filter");
});

test("bound missing assessment opens the existing editor for that exact owned voyage and enlarged worklist text remains readable", async ({
  context,
  page,
}) => {
  const missing = row(2, "INCOMPLETE_ASSESSMENT");
  missing.navigation = {
    kind: "CURRENT_INPUTS",
    vesselId: "PWD-002",
    episodeId: "call-2",
  };
  missing.currentPlan = {
    basis: "MISSING",
    decisionId: null,
    optionId: null,
    approvalStatus: null,
  };
  await company(context, page, projection([missing]));
  await page.getByRole("button", { name: /Fleet review queue/ }).click();
  const dialog = page.getByTestId("company-fleet-triage");
  await dialog.evaluate((element) => {
    element.style.fontSize = "24px";
  });
  const size = await dialog.evaluate((element) => ({
    width: element.clientWidth,
    content: element.scrollWidth,
  }));
  expect(size.content).toBeLessThanOrEqual(size.width + 1);
  await dialog
    .getByRole("link", { name: "Review current inputs", exact: true })
    .click();
  const editor = page.getByRole("dialog", {
    name: "Current inputs for voyage planning",
  });
  await expect(editor).toBeVisible();
  await expect(
    editor.getByRole("combobox", { name: "Current input voyage" }),
  ).toHaveValue("PWD-002");
  await expect(
    editor.getByRole("checkbox", {
      name: "Include a declared remaining passage",
    }),
  ).not.toBeChecked();
});
