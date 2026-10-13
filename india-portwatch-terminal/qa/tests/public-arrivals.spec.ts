import { expect, test, type Page } from "@playwright/test";

const API = process.env.PW_REAL_API;
test.skip(!API, "Start the isolated backend with PW_QA_PUBLIC_ARRIVALS=1");
test.describe.configure({ mode: "serial" });
test.setTimeout(240_000);

test.beforeAll(async ({ request }) => {
  await expect
    .poll(
      async () => {
        try {
          return (await request.get(`${API}/health`)).status();
        } catch {
          return 0;
        }
      },
      {
        timeout: 60_000,
        message:
          "Wait for the separate QA backend to finish seeding and start HTTP",
      },
    )
    .toBe(200);
});

async function login(page: Page, name: string) {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(`${name}@qa.invalid`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("qa-only-verified-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login/);
  return page.evaluate(
    () =>
      JSON.parse(sessionStorage.getItem("portwatch.session.v1")!)
        .accessToken as string,
  );
}

test.beforeEach(async ({ context }) => {
  await context.route("https://fonts.googleapis.com/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/css", body: "" }),
  );
});

test("Chennai shows frozen originals, reported error, ambiguity, missing timestamps and evidence downloads", async ({
  page,
}) => {
  await login(page, "other");
  await page.goto("/port/operations");
  await expect(
    page.getByText("Published ETA → reported arrival → reported berth.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(page.getByTestId("public-pilot-collection")).toContainText(
    "Backend collection:",
  );
  await page.getByText(/Optional structured vessel source/).click();
  await expect(page.getByTestId("structured-vessel-source")).toContainText(
    "adapter is disabled",
  );
  const complete = page
    .getByTestId("public-arrival-case")
    .filter({ hasText: "QA COMPLETE CALL" });
  await expect(complete).toContainText("MATCHED");
  await expect(complete).toContainText("0.02 h");
  await expect(
    page
      .getByTestId("public-arrival-case")
      .filter({ hasText: "QA AMBIGUOUS CALL" }),
  ).toContainText("AMBIGUOUS_CALL_MATCH");
  const conflicting = page
    .getByTestId("public-arrival-case")
    .filter({ hasText: "QA CONFLICTING BERTH" });
  await expect(conflicting).toContainText(
    "CONFLICTING_REPORTED_BERTH_REFERENCES",
  );
  await expect(conflicting).toContainText("Arrival-to-berth wait: Unavailable");
  await expect(
    conflicting.getByRole("button", { name: "Disputed berth QA1 evidence" }),
  ).toBeVisible();
  await expect(
    conflicting.getByRole("button", { name: "Disputed berth QA2 evidence" }),
  ).toBeVisible();
  await page
    .getByText(/Missing timestamps, exclusions and parser issues/)
    .click();
  await expect(page.getByText(/ALIYA:.*MISSING_CLOCK/)).toBeVisible();
  await expect(page.getByText(/MALFORMED_DATE_HEADING/)).toBeVisible();
  await page.getByText(/Archived reports \(/).click();
  const pdfDownload = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download archived PDF", exact: true })
    .first()
    .click();
  const pdf = await pdfDownload;
  expect(pdf.suggestedFilename()).toMatch(/INMAA-.*\.pdf/);
  const datasetDownload = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export public dataset", exact: true })
    .click();
  const dataset = await datasetDownload;
  const stream = await dataset.createReadStream();
  let text = "";
  for await (const chunk of stream!) text += chunk.toString();
  const data = JSON.parse(text);
  expect(
    data.cases.find(
      (c: { vesselName: string }) => c.vesselName === "QA COMPLETE CALL",
    ).outcome.waitingHours,
  ).toBeCloseTo(1 / 60);
  expect(
    data.snapshots.every((s: { sha256: string }) => s.sha256.length === 64),
  ).toBeTruthy();
  await page
    .getByRole("button", { name: "Evaluate chronological baselines" })
    .click();
  await expect(page.locator("pre")).toContainText("UNAVAILABLE");
  // A second viewport run shares the isolated API; the first defines enrollment.
  const cohortButton = page.getByRole("button", {
    name: "Start 30-day cohort",
  });
  if (await cohortButton.isEnabled()) {
    await cohortButton.click();
  }
  await expect(page.getByTestId("public-pilot-cohort")).toContainText(
    "ENROLLING",
  );
  await expect(cohortButton).toBeDisabled();
  await page
    .getByRole("button", { name: "Evaluate chronological baselines" })
    .click();
  await expect(page.locator("pre")).toContainText("fixed enrollment cutoff");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});

test("manual refresh collects official sources through the real API and preserves first-seen originals", async ({
  page,
  context,
}) => {
  const token = await login(page, "paradip");
  const headers = { Authorization: `Bearer ${token}` };
  await page.goto("/port/operations");
  await expect(
    page.getByRole("button", { name: "Refresh official reports" }),
  ).toBeEnabled();
  const before = await (
    await context.request.get(`${API}/public-arrivals/dataset?portCode=INPRT`, {
      headers,
    })
  ).json();
  if (before.collection.lastRun?.errors.length) {
    await expect(page.getByTestId("public-collection-errors")).toContainText(
      "QA collection failure fixture",
    );
  }
  const response = page.waitForResponse(
    (r) =>
      r.url().includes("/public-arrivals/refresh") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Refresh official reports" }).click();
  const result = await response;
  expect(result.status(), await result.text()).toBe(200);
  expect((await result.json()).errors).toEqual([]);
  await expect(page.getByTestId("public-collection-errors")).toHaveCount(0);
  await expect(page.getByTestId("public-pilot-collection")).toContainText(
    "Last successful collection:",
  );
  const after = await (
    await context.request.get(`${API}/public-arrivals/dataset?portCode=INPRT`, {
      headers,
    })
  ).json();
  for (const original of before.snapshots)
    expect(
      after.snapshots.find(
        (s: { snapshotId: string }) => s.snapshotId === original.snapshotId,
      ).firstSeenAt,
    ).toBe(original.firstSeenAt);
  for (const original of before.cases)
    expect(
      after.cases.find((c: { caseId: string }) => c.caseId === original.caseId)
        .etaAt,
    ).toBe(original.etaAt);
  await expect(page.getByTestId("public-pilot-counts")).toContainText(
    "snapshots:",
  );
});

test("replay hides evidence collected later and refuses collection and cross-port access", async ({
  page,
  context,
}) => {
  const token = await login(page, "admin");
  const headers = { Authorization: `Bearer ${token}` };
  const data = await (
    await context.request.get(`${API}/public-arrivals/dataset?portCode=INMAA`, {
      headers,
    })
  ).json();
  const earliest = Math.min(
    ...data.snapshots.map((s: { firstSeenAt: string }) =>
      Date.parse(s.firstSeenAt),
    ),
  );
  try {
    const clock = await context.request.post(`${API}/world/clock`, {
      headers,
      data: {
        mode: "REPLAY",
        at: new Date(earliest - 60_000).toISOString(),
        rate: 0,
        reason: "QA public-evidence availability",
      },
    });
    expect(clock.status(), await clock.text()).toBe(200);
    await page.goto("/port/operations");
    await page.getByLabel("Select port", { exact: true }).selectOption("INMAA");
    await expect(
      page.getByRole("button", { name: "Refresh official reports" }),
    ).toBeDisabled();
    await expect(page.getByTestId("public-pilot-counts")).toContainText(
      "snapshots: 0",
    );
    await expect(page.getByTestId("public-pilot-cohort")).toContainText(
      "No cohort defined",
    );
    await expect(
      page.getByRole("button", { name: "Start 30-day cohort" }),
    ).toBeDisabled();
    expect(
      (
        await context.request.post(
          `${API}/public-arrivals/cohorts?portCode=INMAA`,
          { headers, data: {} },
        )
      ).status(),
    ).toBe(409);
    expect(
      (
        await context.request.post(
          `${API}/public-arrivals/refresh?portCode=INMAA`,
          { headers, data: {} },
        )
      ).status(),
    ).toBe(409);
    expect(
      (
        await context.request.get(
          `${API}/public-arrivals/evidence/${data.snapshots[0].snapshotId}?portCode=INMAA`,
          { headers },
        )
      ).status(),
    ).toBe(404);
    expect(
      (
        await context.request.get(
          `${API}/public-arrivals/workspace?portCode=INMAA`,
          { headers: { "X-PortWatch-Role": "NATIONAL_ADMIN" } },
        )
      ).status(),
    ).toBe(401);
    const portLogin = await context.request.post(`${API}/auth/login`, {
      data: {
        email: "paradip@qa.invalid",
        password: "qa-only-verified-password",
      },
    });
    const portToken = (await portLogin.json()).accessToken;
    expect(
      (
        await context.request.get(
          `${API}/public-arrivals/workspace?portCode=INMAA`,
          {
            headers: {
              Authorization: `Bearer ${portToken}`,
              "X-PortWatch-Port": "INMAA",
              "X-PortWatch-Role": "NATIONAL_ADMIN",
            },
          },
        )
      ).status(),
    ).toBe(403);
  } finally {
    const result = await context.request.post(`${API}/world/clock`, {
      headers,
      data: { mode: "LIVE", reason: "QA restore live clock" },
    });
    expect(result.status()).toBe(200);
  }
});

test("JNPA retains the existing confirmed workflow", async ({ page }) => {
  await login(page, "port");
  await page.goto("/port/operations");
  await expect(
    page.getByRole("button", {
      name: "Register arrival evidence",
      exact: true,
    }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Refresh official reports" }),
  ).toHaveCount(0);
});
