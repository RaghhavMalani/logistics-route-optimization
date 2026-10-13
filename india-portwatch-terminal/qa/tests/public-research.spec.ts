import { test, expect } from "@playwright/test";

test.skip(
  !process.env.PW_REAL_API,
  "Public full-story checks require a real backend",
);
test.beforeEach(async ({ context }) => {
  await context.route("https://fonts.googleapis.com/**", (r) =>
    r.fulfill({ status: 200, contentType: "text/css", body: "" }),
  );
});

test("explorer hydrates with a browser clock different from the server", async ({
  page,
}) => {
  const failures: string[] = [];
  page.on("pageerror", (e) => failures.push(e.message));
  await page.clock.setSystemTime(new Date("2030-01-01T00:00:00Z"));
  await page.goto("/explore");
  await expect(
    page.getByRole("heading", { name: "Investigate the world." }),
  ).toBeVisible();
  await expect(page.locator(".workspace-port-list>button")).toHaveCount(13);
  expect(failures).toEqual([]);
});

test("anonymous journey connects sources, ports, forecasts and route assumptions", async ({
  page,
}) => {
  const failures: string[] = [];
  page.on("pageerror", (e) => failures.push(e.message));
  await page.goto("/explore");
  await expect(page).toHaveURL(/\/explore$/);
  await expect(
    page.getByRole("heading", { name: "Investigate the world." }),
  ).toBeVisible();
  await expect(page.getByTestId("intelligence-globe")).toBeVisible();
  await expect(page.getByTestId("intelligence-globe")).toHaveAttribute(
    "data-ready",
    "true",
    { timeout: 30000 },
  );
  await expect(page.locator(".workspace-port-list>button")).toHaveCount(13);
  await page
    .locator(".workspace-port-list>button")
    .filter({ hasText: "INMAA" })
    .click();
  await page.getByLabel("Forecast horizon", { exact: true }).selectOption("5");
  await expect(
    page.getByText("/ 100 congestion proxy", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Stale forecast snapshot.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText("Nominal 80% interval", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Try a shipping scenario" }).click();
  await expect(
    page.getByRole("heading", { name: "Compared options" }),
  ).toBeVisible({ timeout: 30000 });
  const speed = page.getByLabel("Service speed (kn)", { exact: true });
  const before = await page.locator(".workspace-metrics").innerText();
  await speed.fill("12");
  await page
    .getByRole("button", { name: "Compare shipping actions", exact: true })
    .click();
  await expect(page.locator(".workspace-metrics")).not.toHaveText(before);
  await speed.fill("0");
  await expect(page.getByRole("alert")).toHaveText(/Enter finite values/);
  await expect(
    page.getByRole("button", { name: "Compare shipping actions", exact: true }),
  ).toBeDisabled();
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - innerWidth,
    ),
  ).toBeLessThanOrEqual(1);
  expect(failures).toEqual([]);
  await speed.fill("16");
  await page.screenshot({
    path: `qa/shots/public-explore-${test.info().project.name}.png`,
    fullPage: true,
  });
});

test("research shows real metrics, horizons, calibration and hash-checked downloads", async ({
  page,
  request,
}) => {
  await page.goto("/research");
  await expect(
    page.getByRole("heading", { name: "Models against simple baselines" }),
  ).toBeVisible();
  const row = page.getByRole("row").filter({
    has: page.getByRole("rowheader", { name: "GBM quantile", exact: true }),
  });
  await expect(row).toContainText("5.918");
  await expect(row).toContainText("75.9%");
  await page
    .getByLabel("Compare model", { exact: true })
    .selectOption("Ridge quantile");
  await page
    .getByLabel("Reporting horizon", { exact: true })
    .selectOption("10");
  await expect(page.getByText("Day 10 MAE", { exact: false })).toBeVisible();
  await page
    .getByText("Dataset, code and model versions", { exact: true })
    .click();
  await expect(
    page.getByText("Dataset SHA-256", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Public port-call collection continues",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Simulations remain separate" }),
  ).toBeVisible();
  const csv = await request.get(
    (await page
      .getByRole("link", { name: "Download metrics" })
      .getAttribute("href")) ?? "",
  );
  expect(csv.status()).toBe(200);
  expect(await csv.text()).toContain("signed_bias");
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: /^results.zip/ }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("results.zip");
  expect(await download.failure()).toBeNull();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - innerWidth,
    ),
  ).toBeLessThanOrEqual(1);
  await page.screenshot({
    path: `qa/shots/public-research-${test.info().project.name}.png`,
    fullPage: true,
  });
});

test("visitor layout works on a narrow screen and private routes still require sign-in", async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/explore");
  await page
    .getByRole("button", { name: "Signals & layers", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Port catalogue" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - innerWidth,
    ),
  ).toBeLessThanOrEqual(1);
  await page
    .getByRole("link", { name: "Research & evidence", exact: false })
    .click();
  await expect(
    page.getByRole("heading", { name: "Models against simple baselines" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - innerWidth,
    ),
  ).toBeLessThanOrEqual(1);
  await page.screenshot({
    path: `qa/shots/public-research-mobile-${test.info().project.name}.png`,
    fullPage: true,
  });
  const api = process.env.PW_REAL_API!;
  expect(
    (
      await request.get(api + "/intelligence/cameras", {
        headers: { "X-PortWatch-Role": "NATIONAL_ADMIN" },
      })
    ).status(),
  ).toBe(401);
  expect(
    (
      await request.post(api + "/public-arrivals/refresh?portCode=INMAA", {
        headers: { "X-PortWatch-Role": "NATIONAL_ADMIN" },
      })
    ).status(),
  ).toBe(401);
  await page.goto("/admin/global-eye");
  await expect(page).toHaveURL(/\/login/);
});

test("source failures show an explicit error and retry restores real evidence", async ({
  page,
  context,
  request,
}) => {
  await context.route("**/api/public/workspace*", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Deliberate QA outage" }),
    }),
  );
  await page.goto("/explore");
  await expect(
    page.getByText("Public signals could not load.", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".workspace-port-list>button")).toHaveCount(0);
  await context.unroute("**/api/public/workspace*");
  await page.getByRole("button", { name: "Retry sources" }).click();
  await expect(
    page.getByRole("heading", { name: "Port catalogue" }),
  ).toBeVisible();
  const actual = await (
    await request.get(process.env.PW_REAL_API! + "/public/workspace")
  ).json();
  const missing = actual.ports.find(
    (p: { code: string; forecasts: unknown[] }) => !p.forecasts.length,
  );
  if (missing) {
    await page
      .locator(".workspace-port-list>button")
      .filter({ hasText: missing.code })
      .click();
    await expect(
      page.getByText(
        "No forecast available for this port, horizon and evidence time.",
        { exact: true },
      ),
    ).toBeVisible();
  }
  // Deliberately fail optional stores while retaining the real published data.
  await context.route("**/api/public/research", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({
      json: {
        ...data,
        weather: {
          ...data.weather,
          available: false,
          total: null,
          resolved: null,
          pending: null,
          scores: [],
          note: "The feedback store is unavailable.",
        },
        operational: {
          ...data.operational,
          available: false,
          ports: [],
          reason:
            "Collection status is unavailable; no zero counts are inferred.",
        },
      },
    });
  });
  await page.goto("/research");
  await expect(
    page.getByRole("heading", { name: "Models against simple baselines" }),
  ).toBeVisible();
  await expect(
    page.getByText("Weather feedback is unavailable.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Collection status is unavailable; no zero counts are inferred.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page
      .getByRole("heading", { name: "Public port-call collection continues" })
      .locator("..")
      .getByRole("rowheader", { name: "INPRT", exact: true }),
  ).toHaveCount(0);
});

test("real public case has an interactive timeline, HTTP evidence and freshness", async ({
  page,
  request,
}) => {
  await page.goto("/research#public-port-cases");
  const study = page.locator("#public-port-cases");
  await expect(
    study.getByRole("heading", { name: "MV. GLAD YOUNG", exact: true }),
  ).toBeVisible();
  await expect(
    study.getByText("Published ETA baseline error", { exact: true }),
  ).toBeVisible();
  await expect(study.getByText("-24 min", { exact: true })).toBeVisible();
  await expect(study.getByText("2.4 h", { exact: true })).toBeVisible();
  await expect(study.locator(".public-freshness")).toBeVisible();
  await study
    .getByRole("button", { name: "Inspect reported arrival", exact: true })
    .click();
  await expect(
    study.getByRole("button", {
      name: "Inspect reported arrival",
      exact: true,
    }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(study.locator(".public-raw-clock")).toHaveText("00:36\n08-10");
  await study.getByLabel("Case clock display").selectOption("UTC");
  const link = study.getByRole("link", {
    name: "Open archived reported arrival PDF",
  });
  const url = new URL((await link.getAttribute("href"))!);
  expect(url.protocol).toBe(new URL(process.env.PW_REAL_API!).protocol);
  url.hash = "";
  const pdf = await request.get(url.toString());
  expect(pdf.status()).toBe(200);
  expect(pdf.headers()["content-type"]).toBe("application/pdf");
  expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");
  const audit = await request.get(
    (await study
      .getByRole("link", { name: "Download public case audit" })
      .getAttribute("href"))!,
  );
  expect(audit.status()).toBe(200);
  const contents = await audit.text();
  expect(contents).not.toContain("D:");
  expect(contents).not.toContain("freezeActor");
  const caseLink = await study
    .getByRole("link", { name: "Link to this case" })
    .getAttribute("href");
  await page.goto(caseLink!);
  await expect(
    study.getByRole("heading", { name: "MV. GLAD YOUNG", exact: true }),
  ).toBeVisible();
  await study.getByLabel("Public call port").selectOption("INMAA");
  await expect(
    study.getByText("No complete, visually reviewed public case is available", {
      exact: false,
    }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await study.getByLabel("Public call port").selectOption("INPRT");
  await study
    .getByRole("button", { name: "Inspect reported berth", exact: true })
    .click();
  await expect(study.locator(".public-raw-clock")).toHaveText("03:00\n08-10");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - innerWidth,
    ),
  ).toBeLessThanOrEqual(1);
  await study.screenshot({
    path: `qa/shots/public-case-${test.info().project.name}.png`,
  });
});

test("a paper case link selects its case when another call is listed first", async ({
  page,
  context,
  request,
}) => {
  const evidence = await (
    await request.get(process.env.PW_REAL_API! + "/public/port-calls")
  ).json();
  const glad = evidence.cases.find(
    (c: { vesselName: string }) => c.vesselName === "MV. GLAD YOUNG",
  );
  // A UI-only fixture models later catalogue growth; no collection is written.
  await context.route("**/api/public/port-calls", (route) =>
    route.fulfill({
      json: {
        ...evidence,
        cases: [
          { ...glad, caseId: "b".repeat(64), vesselName: "UI TEST CALL" },
          glad,
        ],
      },
    }),
  );
  await page.goto(`/research#case-${glad.caseId}`);
  const study = page.locator("#public-port-cases");
  await expect(
    study.getByRole("heading", { name: "MV. GLAD YOUNG", exact: true }),
  ).toBeVisible();
  await expect(study.getByLabel("Reviewed vessel")).toHaveValue(glad.caseId);
});
