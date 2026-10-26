import fs from "node:fs";
import { createHash } from "node:crypto";
import type { BrowserContext, Locator, Page } from "@playwright/test";
import { ACCOUNTS, expect, settle, test } from "../harness";
import type {
  FeedbackClaim,
  FeedbackInspection,
} from "@/services/sharedFeedback";

// Synthetic presentation contracts only. These records never enter a source,
// visitor ledger or training cohort, and are not provider/operational evidence.
const AS_OF = "2026-10-25T12:00:00Z";
const QUOTE =
  "SIMULATED input fixture\nobservation_date,DEXINUS\n2026-10-13,83\n";
const OUTCOME =
  "SIMULATED outcome fixture\nobservation_date,DEXINUS\n2026-10-15,83.4\n";
const hash = (text: string) => createHash("sha256").update(text).digest("hex");
const QUOTE_HASH = hash(QUOTE),
  OUTCOME_HASH = hash(OUTCOME);
const ECONOMIC: FeedbackClaim = {
  id: "qa-fx-forecast",
  kind: "FORECAST",
  wording: "SIMULATED persistence forecast for DEXINUS on 2026-10-15",
  value: 83,
  unit: "INR/USD",
  entity: "DEXINUS",
  geography: "India / US reference rate",
  originAt: "2026-10-14T12:00:00Z",
  firstAvailableAt: "2026-10-14T12:00:00Z",
  source: "https://example.org/qa-dexinus",
  sourceVersion: "qa-v1",
  responseSha256: QUOTE_HASH,
  eventKey: "qa-dexinus-2026-10-15",
  target: {
    kind: "ECONOMIC_OBSERVATION",
    series: "DEXINUS",
    date: "2026-10-15",
  },
  inputs: [
    {
      value: 83,
      observationDate: "2026-10-13",
      firstAvailableAt: "2026-10-14T11:00:00Z",
      responseSha256: QUOTE_HASH,
    },
  ],
  economicInspection: {
    status: "MATCHED",
    reason:
      "Compatible later date-only observation; first retained scoring vintage.",
    predicted: 83,
    inputQuote: {
      value: 83,
      observationDate: "2026-10-13",
      ageDays: 1,
      firstAvailableAt: "2026-10-14T11:00:00Z",
      responseSha256: QUOTE_HASH,
    },
    targetDate: "2026-10-15",
    issuedAt: "2026-10-14T12:00:00Z",
    matchedObservation: {
      value: 83.4,
      observationDate: "2026-10-15",
      firstAvailableAt: "2026-10-19T20:30:00Z",
      evidenceId: "qa-outcome",
      responseSha256: OUTCOME_HASH,
    },
    error: 0.4,
    absoluteError: 0.4,
    scoringVintage: "qa-first-retained",
    revisionState: "FIRST_RETAINED_SCORING_VINTAGE",
    exclusions: [],
    selectionPolicy: "FIRST_RETAINED_COMPATIBLE_OUTCOME_V1",
    expectedRelease:
      "H.10 weekly release, with holidays and possible delays; fixture schedule only.",
    eligibleForReliability: true,
  },
};
const NEWS: FeedbackClaim = {
  id: "qa-news-report",
  kind: "REPORTED_FACT",
  wording:
    "SIMULATED attributed report: an authority announced a lock restriction",
  value: true,
  unit: "boolean",
  entity: "QA_LOCK",
  geography: "SIMULATED lock area",
  originAt: "2026-10-22T10:00:00Z",
  firstAvailableAt: "2026-10-22T10:00:00Z",
  source: "https://example.org/qa-report",
  sourceVersion: "qa-report-v1",
  responseSha256: hash("SIMULATED authority announcement fixture"),
  eventKey: "qa-lock-announcement",
  target: {
    kind: "ANNOUNCEMENT",
    predicate: "AUTHORITY_NOTICE_ANNOUNCED_LOCK_CLOSURE",
    reportedPeriod: {
      from: "2026-10-27",
      through: "2026-10-28",
      precision: "DATE_ONLY",
    },
  },
  inputs: [],
  sourceQuality: {
    articleBodyRetained: true,
    sourceProductRetained: true,
    closureInference: "Announcement does not establish actual closure",
    timestampMeaning: "Application receipt, separate from publication",
    originalAccess: "LOCAL_RESEARCH_ARCHIVE",
    redistributionPolicy: "Public redistribution is not qualified",
  },
  newsIdentity: {
    targetId: "qa-exact-target",
    eventFamilyId: "qa-lock",
    lineageId: "qa-authority",
    reportId: "qa-report",
    revisionId: "qa-report-v1",
  },
  verification: {
    id: "qa-assessment",
    verdict: "CORROBORATED",
    applicability: "SUPERSEDED",
    reason:
      "Primary document verifies the exact attributed announcement; later cancellation changes applicability.",
    availableAt: "2026-10-23T14:00:00Z",
    verificationMode: "PRIMARY_DOCUMENT_ATTESTS_ATTRIBUTED_ANNOUNCEMENT",
    independentReportingConfirmations: 0,
    evidenceIds: ["qa-primary"],
  },
  newsInspection: {
    currentAssessment: null,
    evidence: [
      {
        id: "qa-primary",
        source: "https://example.org/qa-authority",
        responseSha256: hash("SIMULATED authority announcement fixture"),
        firstAvailableAt: "2026-10-23T14:00:00Z",
        publishedDate: "2026-10-12",
        publicationPrecision: "DATE_ONLY",
        sourceLineageId: "qa-authority",
        sourceRole: "PRIMARY_AUTHORITY_NOTICE",
      },
    ],
    exclusionReasons: [],
    assessmentHistory: [],
    asOf: AS_OF,
  },
};
NEWS.newsInspection!.currentAssessment = NEWS.verification!;
const RELIABILITY = {
  id: "qa-neutral",
  status: "COLLECTING",
  consumedWeight: 1,
  errorConvention: "observed minus predicted",
  slices: [],
};

function inspection(params: URLSearchParams): FeedbackInspection {
  const asOf = params.get("asOf") ?? AS_OF;
  const beforeOutcome = Date.parse(asOf) < Date.parse("2026-10-19T20:30:00Z");
  const beforeNews = Date.parse(asOf) < Date.parse(NEWS.firstAvailableAt);
  const selected = params.get("claimId"),
    kind = params.get("kind") ?? "ALL";
  const offset = Number(params.get("offset") ?? 0),
    limit = Number(params.get("limit") ?? 25);
  const economic = structuredClone(ECONOMIC),
    news = structuredClone(NEWS);
  if (beforeOutcome)
    Object.assign(economic.economicInspection!, {
      status: "PENDING_UNRELEASED",
      reason:
        "Matching daily observation not released in this retained weekly product.",
      matchedObservation: null,
      error: null,
      absoluteError: null,
      eligibleForReliability: false,
    });
  if (Date.parse(asOf) < Date.parse("2026-10-23T14:00:00Z")) {
    news.verification = {
      verdict: "UNRESOLVED",
      applicability: "AS_REPORTED",
      reason:
        "Independent/primary original unavailable as of this time; absence is not contradiction.",
    };
    news.newsInspection = {
      currentAssessment: news.verification,
      evidence: [],
      exclusionReasons: [
        "Suitable original not available at the requested time",
      ],
      assessmentHistory: [],
      asOf,
    };
  }
  const claims = [
    economic,
    ...(!beforeNews ? [news] : []),
    ...Array.from({ length: 28 }, (_, index) => ({
      ...structuredClone(economic),
      id: `qa-fx-copy-${index}`,
      wording: `SIMULATED retained forecast representation ${index}`,
    })),
  ];
  const filtered = claims.filter(
    (item) =>
      kind === "ALL" ||
      (kind === "NEWS"
        ? item.kind === "REPORTED_FACT"
        : item.kind === "FORECAST"),
  );
  const visible = selected
    ? filtered.filter((item) => item.id === selected)
    : filtered.slice(offset, offset + limit);
  return {
    contractVersion: "shared-feedback-v1",
    claims: visible,
    reliability: RELIABILITY,
    newsIndependentEvents: beforeNews ? 0 : 1,
    newsSourceReports: beforeNews ? 0 : 3,
    note: "SIMULATED software fixture, not real forecast or shipping evidence.",
    dataset: {
      scope: "ALL_RETAINED_PUBLIC_CLAIMS_AS_OF",
      asOf,
      totalClaims: claims.length,
      filteredClaims: filtered.length,
      offset,
      limit,
      returnedClaims: visible.length,
      hasMore: !selected && offset + limit < filtered.length,
      filter: kind,
      selectedClaimId: selected,
    },
    economicSummary: {
      retainedObservations: 6,
      independentForecastTargets: 1,
      forecastVintages: 29,
      eligibleMatches: beforeOutcome ? 0 : 1,
      unresolvedTargets: beforeOutcome ? 1 : 0,
      excludedTargets: 0,
      retrospectiveObservations: 5,
      metrics: beforeOutcome
        ? []
        : [
            {
              context: ["DEXINUS", "PERSISTENCE_V1", "+1d"],
              independentTargets: 1,
              bias: 0.4,
              meanAbsoluteError: 0.4,
              targetFrom: "2026-10-15",
              targetThrough: "2026-10-15",
              status: "COLLECTING",
              unit: "INR/USD",
            },
          ],
    },
    newsAggregation: {
      contractVersion: "news-as-of-v1",
      policy: "EXPLICIT_SUPERSESSION_AS_OF_V1",
      asOf,
      summary: {
        eventCount: beforeNews ? 0 : 1,
        independentTargets: beforeNews ? 0 : 1,
        eligibleIndependentTargets: beforeNews ? 0 : 1,
        resolvedIndependentTargets: beforeNews
          ? 0
          : news.verification?.verdict === "CORROBORATED"
            ? 1
            : 0,
        pendingIndependentTargets:
          !beforeNews && news.verification?.verdict === "UNRESOLVED" ? 1 : 0,
        reportCount: beforeNews ? 0 : 3,
        revisionCount: beforeNews ? 0 : 4,
        excludedTargetCount: 0,
        ambiguousClaimCount: 0,
      },
      targets: [],
      exclusions: [],
    },
    collector: { status: "COLLECTING", ranAt: asOf, failures: [] },
  };
}

async function openFeedback(context: BrowserContext, page: Page) {
  const writes: Record<string, unknown>[] = [];
  let corrupt = false;
  await context.route("**/api/demo/terminal/**", async (route) => {
    const url = new URL(route.request().url()),
      relative = url.pathname.split("/demo/terminal/")[1];
    if (relative === "intelligence/feedback")
      return route.fulfill({ json: inspection(url.searchParams) });
    if (relative === "intelligence/feedback/audit")
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          inspection(
            new URLSearchParams({
              ...Object.fromEntries(url.searchParams),
              offset: "0",
              limit: "10000",
            }),
          ),
        ),
      });
    if (relative?.startsWith("intelligence/feedback/evidence/"))
      return route.fulfill({
        contentType: "application/octet-stream",
        body: corrupt
          ? "CORRUPT fixture bytes"
          : relative.endsWith(QUOTE_HASH)
            ? QUOTE
            : OUTCOME,
      });
    if (relative === "intelligence/feedback/impacts")
      return route.fulfill({ json: { claims: [] } });
    if (relative === "intelligence/review-tasks") {
      if (route.request().method() === "POST") {
        writes.push(route.request().postDataJSON());
        return route.fulfill({
          json: { id: "qa-task", status: "PENDING_VERIFICATION" },
        });
      }
      return route.fulfill({
        json: {
          tasks: [
            {
              id: "qa-task",
              kind: "SOURCE_EXPOSURE_VERIFICATION_TASK",
              status: "PENDING_VERIFICATION",
              createdAt: "2026-10-22T12:00:00Z",
              reason: "SIMULATED frozen review question",
              missingOperationalInputs: [
                "actual execution and matching operation record",
              ],
              calculatedDelayHours: null,
              createsOperationalTarget: false,
              vesselId: "PWD-001",
              sourceReview: {
                status: "REVIEW_REQUIRED",
                asOf: AS_OF,
                reason:
                  "Consumed applicability changed; original task retained",
                requiresFreshReview: true,
                currentAssessment: NEWS.verification,
                changedFields: ["applicability"],
                realOperationalTargetsAdded: 0,
              },
            },
          ],
        },
      });
    }
    if (route.request().method() !== "GET") return route.fallback();
    const fixture = new URL(
      `../fixtures/${relative?.replaceAll("/", "_")}.json`,
      import.meta.url,
    );
    if (!fs.existsSync(fixture)) return route.fallback();
    const data = JSON.parse(fs.readFileSync(fixture, "utf8"));
    if (relative === "company/fleet") data.vessels = data.vessels.slice(0, 2);
    return route.fulfill({ json: data });
  });
  const now = Date.now();
  await context.route("**/api/demo/session", (route) =>
    route.fulfill({
      json: {
        user: ACCOUNTS.SHIPPING_COMPANY,
        mode: "demo",
        accessToken: "qa-feedback-synthetic",
        issuedAt: new Date(now).toISOString(),
        expiresAt: new Date(now + 3600000).toISOString(),
      },
    }),
  );
  await page.goto("/login");
  await page.getByRole("button", { name: "Company demo", exact: true }).click();
  await page.waitForURL("**/company/overview");
  await page.goto("/company/global-eye");
  await settle(page);
  await page
    .getByRole("button", { name: "Global intelligence", exact: true })
    .click();
  const panel = page.getByTestId("shared-feedback");
  await panel.locator(":scope > summary").click();
  await expect(panel.getByTestId("economic-result")).toBeVisible();
  return {
    panel,
    writes,
    corruptOriginal() {
      corrupt = true;
    },
  };
}
async function noOverflow(locator: Locator) {
  const box = await locator.evaluate((el) => ({
    width: el.clientWidth,
    content: el.scrollWidth,
  }));
  expect(box.width).toBeGreaterThan(0);
  expect(box.content).toBeLessThanOrEqual(box.width + 1);
}

test("FX result uses independent full-dataset counts, readable errors and hash-exact downloads", async ({
  context,
  page,
}) => {
  const { panel } = await openFeedback(context, page);
  const result = panel.getByTestId("economic-result");
  await expect(result).toContainText("2026-10-15 · date only");
  await expect(result).toContainText("+0.4 INR/USD");
  await expect(panel.getByTestId("economic-feedback-summary")).toContainText(
    "1 independent forecast targets",
  );
  await expect(panel.getByTestId("economic-feedback-summary")).toContainText(
    "29 vintages",
  );
  await expect(panel.getByTestId("feedback-dataset-scope")).toContainText(
    "30 retained claims",
  );
  await noOverflow(result);
  await noOverflow(panel);
  const archive = panel.getByTestId("feedback-claim-evidence");
  await archive.locator(":scope > summary").focus();
  await page.keyboard.press("Enter");
  const downloadWait = page.waitForEvent("download");
  await archive
    .getByRole("button", {
      name: "Download retained original response",
      exact: true,
    })
    .click();
  const download = await downloadWait;
  expect(hash(fs.readFileSync((await download.path())!, "utf8"))).toBe(
    QUOTE_HASH,
  );
  const auditWait = page.waitForEvent("download");
  await panel
    .getByRole("button", { name: "Download full filtered audit", exact: true })
    .click();
  const auditDownload = await auditWait;
  const audit = JSON.parse(
    fs.readFileSync((await auditDownload.path())!, "utf8"),
  );
  expect(audit.claims).toHaveLength(30);
  expect(audit.dataset.asOf).toBe(AS_OF);
  await page.addStyleTag({
    content:
      '[data-testid="shared-feedback"] { font-size:24px!important } [data-testid="feedback-claim-result"], [data-testid="feedback-claim-result"] * { font-size:24px!important }',
  });
  await noOverflow(result);
  await noOverflow(panel);
});

test("news exact assessment keeps applicability, lineage and owned voyage connected across paging", async ({
  context,
  page,
}) => {
  const { panel, writes } = await openFeedback(context, page);
  await expect(panel.getByTestId("news-feedback-summary")).toContainText(
    "0 excluded target groups",
  );
  await expect(panel.getByTestId("news-feedback-summary")).toContainText(
    "these counts can overlap",
  );
  await panel
    .getByRole("combobox", { name: "Selected feedback claim" })
    .selectOption(NEWS.id);
  const news = panel.getByTestId("feedback-claim-result");
  await expect(news).toContainText("CORROBORATED");
  await expect(news).toContainText("SUPERSEDED");
  await expect(news).toContainText("0 independent reporting confirmations");
  await expect(news).toContainText(
    "does not prove the announced closure occurred",
  );
  await panel
    .getByRole("combobox", { name: "Feedback voyage" })
    .selectOption("PWD-002");
  await panel.getByRole("button", { name: "Next claims", exact: true }).click();
  await expect(news).toHaveAttribute("data-claim-id", NEWS.id);
  await expect(
    panel.getByRole("combobox", { name: "Feedback voyage" }),
  ).toHaveValue("PWD-002");
  await panel
    .getByRole("combobox", { name: "Feedback claim category" })
    .selectOption("NEWS");
  await expect(news).toHaveAttribute("data-claim-id", NEWS.id);
  await panel
    .getByRole("button", {
      name: "Request verification of this report",
      exact: true,
    })
    .click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ claimId: NEWS.id, vesselId: "PWD-002" });
  const tasks = page.getByTestId("intelligence-review-tasks");
  await tasks.locator(":scope > summary").click();
  await tasks.getByText(/PENDING_VERIFICATION ·/).click();
  await expect(tasks.getByTestId("task-source-review")).toContainText(
    "Consumed source changed",
  );
  await expect(tasks).toContainText("zero real operational targets");
  await noOverflow(news);
});

test("earlier as-of views hide later outcomes and confirmation while keeping exact pending reasons", async ({
  context,
  page,
}) => {
  const { panel } = await openFeedback(context, page);
  await panel
    .getByRole("textbox", { name: "Feedback as-of UTC" })
    .fill("2026-10-16T12:00:00Z");
  await panel.getByRole("button", { name: "Apply as-of", exact: true }).click();
  await expect(panel.getByTestId("feedback-claim-result")).toContainText(
    "PENDING_UNRELEASED",
  );
  await expect(panel.getByTestId("economic-result")).not.toContainText("83.4");
  await expect(panel.getByTestId("economic-result")).toContainText(
    "Unavailable INR/USD",
  );
  await panel
    .getByRole("textbox", { name: "Feedback as-of UTC" })
    .fill("2026-10-22T12:00:00Z");
  await panel.getByRole("button", { name: "Apply as-of", exact: true }).click();
  await panel
    .getByRole("combobox", { name: "Selected feedback claim" })
    .selectOption(NEWS.id);
  await expect(panel.getByTestId("news-result")).toContainText("AS_REPORTED");
  await expect(panel.getByTestId("feedback-claim-result")).toContainText(
    "UNRESOLVED",
  );
  await expect(panel.getByTestId("feedback-claim-result")).not.toContainText(
    "CORROBORATED",
  );
});

test("invalid as-of and corrupt originals remain actionable without a misleading download", async ({
  context,
  page,
}) => {
  const { panel, corruptOriginal } = await openFeedback(context, page);
  await panel
    .getByRole("textbox", { name: "Feedback as-of UTC" })
    .fill("2026-10-16T12:00:00");
  await panel.getByRole("button", { name: "Apply as-of", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("explicit UTC offset");
  corruptOriginal();
  await panel
    .getByTestId("feedback-claim-evidence")
    .locator(":scope > summary")
    .click();
  await panel
    .getByRole("button", {
      name: "Download retained original response",
      exact: true,
    })
    .click();
  await expect(
    panel.getByRole("alert").filter({ hasText: "hash does not match" }),
  ).toBeVisible();
});
