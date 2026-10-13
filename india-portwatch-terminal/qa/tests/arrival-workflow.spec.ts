/** Real arrival API; the resilience check aborts only the unrelated aggregate chain request. */
import { expect, test, type Page } from "@playwright/test";
const API = process.env.PW_REAL_API;
test.skip(!API, "Start the verified QA server with PW_QA_ARRIVALS=1");
test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

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
function local(d: Date) {
  const n = (v: number) => String(v).padStart(2, "0");
  // Chromium normalizes zero seconds away; fill requires the canonical value.
  return `${d.getFullYear()}-${n(d.getMonth() + 1)}-${n(d.getDate())}T${n(d.getHours())}:${n(d.getMinutes())}${d.getSeconds() ? `:${n(d.getSeconds())}` : ""}`;
}
async function create(page: Page, reference: string, mmsi = "419000168") {
  await page.goto("/port/operations");
  await page
    .getByRole("button", { name: "Register arrival evidence", exact: true })
    .click();
  await page.getByLabel("Arrival / booking reference").fill(reference);
  await page.getByLabel("Observed vessel MMSI").fill(mmsi);
  await page
    .getByLabel("Vessel name", { exact: true })
    .fill("QA browser arrival");
  await page
    .getByLabel("Recipient organisation", { exact: true })
    .fill("QA Shipping");
  await page
    .getByLabel("Planned anchorage arrival", { exact: true })
    .fill(local(new Date(Date.now() + 86_400_000)));
  await page
    .getByLabel("Route revision (if known)")
    .fill("QA-route-browser-v1");
  await page.getByLabel("Incumbent scheduled wait, hours").fill("22");
  await page
    .getByLabel("Incumbent schedule source / reference")
    .fill("QA synthetic scheduler call; test only");
  await page
    .getByLabel("Individual scheduler reference")
    .fill(`QA-scheduler-${reference}`);
  await page
    .getByLabel("Scheduler estimate issued at")
    .fill(local(new Date(Date.now() - 120000)));
  await page
    .getByLabel("Scheduler estimate available at")
    .fill(local(new Date(Date.now() - 60000)));
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/arrivals/operations") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Freeze evidence and create review" })
    .click();
  const result = await response;
  expect(result.status(), await result.text()).toBe(200);
  return result.json();
}
test.beforeEach(async ({ context }) => {
  await context.route("https://fonts.googleapis.com/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/css", body: "" }),
  );
});

test("arrival evidence remains available when the aggregate port chain fails", async ({
  page,
  context,
}) => {
  await login(page, "port");
  await context.route(`${API}/model/INNSA/chain`, (route) =>
    route.abort("failed"),
  );
  await page.goto("/port/operations");
  await expect(
    page.getByRole("button", {
      name: "Register arrival evidence",
      exact: true,
    }),
  ).toBeEnabled();
  await expect(
    page.getByText(
      "Aggregate operational state unavailable. Arrival evidence and outcomes remain available independently.",
      { exact: true },
    ),
  ).toBeVisible({ timeout: 30_000 });
});

test("frozen weather/AIS → reviewed advisory → recipient response → actual action → measured error", async ({
  page,
  context,
  browser,
}) => {
  const token = await login(page, "port");
  const reference = `QA-BROWSER-${test.info().project.name}-${Date.now()}`;
  const first = await create(page, reference);
  expect(
    first.evidence.weather.some(
      (w: { variable: string }) => w.variable === "wind_speed",
    ),
  ).toBeTruthy();
  expect(first.evidence.tracks.length).toBeGreaterThanOrEqual(2);
  expect(first.prediction.status).toBe("AVAILABLE");
  expect(first.prediction.low).toBeLessThanOrEqual(first.prediction.value);
  await expect(page.getByTestId("arrival-case")).toContainText("80% interval");
  await page
    .getByLabel("Arrival review note")
    .fill("QA reviewed the evidence and missing camera coverage");
  await page
    .getByRole("button", { name: "Approve arrival review", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "Create arrival review advisory",
      exact: true,
    })
    .click();
  await page
    .getByRole("button", { name: "Review arrival advisory", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "Approve and issue arrival advisory",
      exact: true,
    })
    .click();
  await expect(page.getByLabel("Actual action taken / declined")).toBeVisible();
  const workspaceResponse = await context.request.get(
    `${API}/arrivals/workspace`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  const issued = (await workspaceResponse.json()).operations.find(
    (c: { operationRef: string }) => c.operationRef === reference,
  );
  const company = await browser.newContext();
  const companyPage = await company.newPage();
  const companyToken = await login(companyPage, "company");
  const accepted = await company.request.post(
    `${API}/advisories/${issued.advisoryId}/transition`,
    {
      headers: { Authorization: `Bearer ${companyToken}` },
      data: { target: "accepted" },
    },
  );
  expect(accepted.status(), await accepted.text()).toBe(200);
  await company.close();
  await page.reload();
  await page
    .getByLabel("Arrival operation", { exact: true })
    .selectOption(first.operationId);
  await expect(page.getByTestId("arrival-case")).toContainText("accepted");
  await expect(page.getByTestId("arrival-case")).toContainText("Not recorded");
  const actionAt = new Date(Math.floor(Date.now() / 1000) * 1000);
  await page
    .getByLabel("Actual action taken / declined")
    .fill("QA retained the planned arrival; synthetic execution log");
  await page.getByLabel("Action occurred at").fill(local(actionAt));
  await page.getByLabel("Action evidence available at").fill(local(actionAt));
  await page
    .getByLabel("Actual action source / reference")
    .fill("QA bridge log; not an operational action");
  await page
    .getByRole("button", { name: "Record actual action", exact: true })
    .click();
  await expect(page.getByLabel("Confirmed all-fast time")).toBeVisible();
  const allFast = new Date(Math.floor(Date.now() / 1000) * 1000);
  await page
    .getByLabel("Confirmed anchorage arrival", { exact: true })
    .fill(local(actionAt));
  await page.getByLabel("Confirmed all-fast time").fill(local(allFast));
  await page.getByLabel("Outcome evidence available at").fill(local(allFast));
  await page
    .getByLabel("Berth / port-call log reference")
    .fill("QA-berth-browser");
  await page
    .getByLabel("Outcome source", { exact: true })
    .fill("QA synthetic confirmed times; test only");
  await page
    .getByLabel("Outcome log / confirmation reference")
    .fill("QA-log-browser");
  await page.getByLabel("Anchorage record available at").fill(local(actionAt));
  await page.getByLabel("All-fast record available at").fill(local(allFast));
  const outcomeResponse = page.waitForResponse((r) =>
    r.url().endsWith(`/arrivals/operations/${first.operationId}/outcome`),
  );
  await page
    .getByRole("button", { name: "Resolve measured waiting", exact: true })
    .click();
  const resolvedResponse = await outcomeResponse;
  expect(resolvedResponse.status(), await resolvedResponse.text()).toBe(200);
  const resolved = await resolvedResponse.json();
  expect(resolved.prediction).toEqual(first.prediction);
  expect(resolved.evidence).toEqual(first.evidence);
  expect(resolved.errorHours).toBeCloseTo(
    resolved.outcome.waitHours - first.prediction.value,
    8,
  );
  await expect(page.getByTestId("arrival-case")).toContainText(
    "Outside predicted interval",
  );
  await page.reload();
  await page
    .getByLabel("Arrival operation", { exact: true })
    .selectOption(first.operationId);
  await expect(page.getByTestId("arrival-case")).toContainText(
    "QA synthetic confirmed times; test only",
  );
  await expect(page.getByTestId("arrival-benchmark")).toContainText(
    "incumbent MAE",
  );
  const fitsViewport = await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth + 1,
  );
  expect(fitsViewport).toBeTruthy();
  await page.screenshot({
    path: `../work/arrival-${test.info().project.name}.png`,
    fullPage: true,
  });
});

test("missing observed vessel reports withhold the numeric prediction", async ({
  page,
}) => {
  await login(page, "port");
  const row = await create(
    page,
    `QA-MISSING-${test.info().project.name}-${Date.now()}`,
    "419999998",
  );
  expect(row.prediction.value).toBeNull();
  expect(row.evidence.tracks).toHaveLength(0);
  await expect(page.getByTestId("arrival-case")).toContainText(
    "Uncertainty unavailable until calibration",
  );
  await page
    .getByText("Evidence, missing inputs and audit", { exact: true })
    .click();
  await expect(page.getByTestId("arrival-case")).toContainText(
    "Two archived AIS positions",
  );
});

test("prospective CSV preview → commit → independent confirmed outcome and cohort export", async ({
  page,
}) => {
  const token = await login(page, "port");
  await page.goto("/port/operations");
  const collection = page.getByTestId("arrival-collection");
  await expect(collection).toBeVisible();
  const start = collection.getByRole("button", {
    name: "Start prospective cohort",
  });
  if (await start.isVisible()) await start.click();
  await expect(collection).toContainText("COLLECTING");
  await expect(collection.getByTestId("jnpa-public-evidence")).toContainText(
    "awaiting verification",
  );
  await collection
    .getByText("Import operator / port-call CSV", { exact: true })
    .click();
  const reference = `QA-CSV-${test.info().project.name}-${Date.now()}`;
  const csv = [
    "operationRef,mmsi,vesselName,recipientOrganisation,plannedArrivalAt,baselineWaitHours,baselineSource,baselineRef,baselineEstimatedAt,baselineAvailableAt",
    `${reference},419000169,QA CSV vessel,QA Shipping,${new Date(Date.now() + 86400000).toISOString()},20,QA scheduler,QA-estimate,${new Date(Date.now() - 120000).toISOString()},${new Date(Date.now() - 60000).toISOString()}`,
  ].join("\n");
  const before = await page.request.get(`${API}/arrivals/workspace`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const beforeState = await before.json();
  const previous = beforeState.operations.length;
  await collection.getByLabel("CSV records", { exact: true }).fill(csv);
  await collection
    .getByRole("button", { name: "Preview CSV", exact: true })
    .click();
  await expect(collection).toContainText(
    "Preview: 1 valid records. No writes kept.",
  );
  const afterPreview = await page.request.get(`${API}/arrivals/workspace`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect((await afterPreview.json()).operations.length).toBe(previous);
  await collection
    .getByRole("button", { name: "Commit validated CSV", exact: true })
    .click();
  await expect(collection).toContainText("Imported 1 records");
  const after = await page.request.get(`${API}/arrivals/workspace`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const caseRow = (await after.json()).operations.find(
    (r: { operationRef: string }) => r.operationRef === reference,
  );
  expect(caseRow.cohortId).toBeTruthy();
  await page
    .getByLabel("Arrival operation", { exact: true })
    .selectOption(caseRow.operationId);
  await expect(page.getByTestId("arrival-case")).toContainText("Not recorded");
  await expect
    .poll(() => Date.now())
    .toBeGreaterThan(Date.parse(caseRow.issuedAt) + 1100);
  const at = new Date(Math.floor(Date.now() / 1000) * 1000);
  for (const label of [
    "Confirmed anchorage arrival",
    "Confirmed all-fast time",
    "Outcome evidence available at",
    "Anchorage record available at",
    "All-fast record available at",
  ])
    await page.getByLabel(label, { exact: true }).fill(local(at));
  await page.getByLabel("Berth / port-call log reference").fill("QA berth CSV");
  await page
    .getByLabel("Outcome source", { exact: true })
    .fill("QA synthetic verified log");
  await page
    .getByLabel("Outcome log / confirmation reference")
    .fill("QA log CSV");
  await page
    .getByRole("button", { name: "Resolve measured waiting", exact: true })
    .click();
  await expect(page.getByTestId("arrival-case")).toContainText(
    "QA synthetic verified log",
  );
  await expect(collection).toContainText(
    `${beforeState.collection.qualifyingCount} / 60 qualifying calls`,
  );
  const download = page.waitForEvent("download");
  await collection
    .getByRole("button", { name: "Export cohort JSON", exact: true })
    .click();
  expect((await download).suggestedFilename()).toBe(
    "jnpa-prospective-cohort.json",
  );
  await page.screenshot({
    path: `../work/collection-${test.info().project.name}.png`,
    fullPage: true,
  });
});
