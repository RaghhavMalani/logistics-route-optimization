/** Real HTTP API and SQLite workflows; intentionally does not import the fixture harness. */
import { expect, test, type Page, type BrowserContext } from "@playwright/test";

const API = process.env.PW_REAL_API;
test.skip(
  !API,
  "Set PW_REAL_API to the isolated scripts.serve_verified_qa server",
);
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
  const session = await page.evaluate(() =>
    JSON.parse(sessionStorage.getItem("portwatch.session.v1")!),
  );
  expect(session.mode).toBe("production");
  expect(session.accessToken).toBeTruthy();
  return session;
}

async function http(
  context: BrowserContext,
  path: string,
  token: string,
  body?: unknown,
) {
  const response = await context.request.fetch(`${API}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { Authorization: `Bearer ${token}` },
    ...(body === undefined ? {} : { data: body }),
    timeout: 120_000,
  });
  expect(
    response.ok(),
    `${path}: ${response.status()} ${await response.text()}`,
  ).toBeTruthy();
  return response.status() === 204 ? null : response.json();
}

test.beforeEach(async ({ context }) => {
  // Font CSS is presentation-only; no /api route is intercepted or fulfilled.
  await context.route("https://fonts.googleapis.com/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/css", body: "" }),
  );
});

test("verified login, all-port variable filtering, persisted camera and replay without live requests", async ({
  context,
  page,
}) => {
  const admin = await login(page, "admin");
  const token = admin.accessToken;
  const suffix = test.info().project.name;
  const cameraId = `qa-camera-${suffix}`;
  await page.goto("/admin/global-eye");
  await page.getByTestId("open-intelligence").click();
  await expect(
    page.getByTestId("intelligence-port-select").locator("option"),
  ).toHaveCount(14);
  await page.getByTestId("intelligence-port-select").selectOption("");
  await page.getByRole("tab", { name: "Forecasts", exact: true }).click();
  await expect(page.locator(".intel-forecast-list button")).toHaveCount(65);
  await expect(
    page.getByRole("heading", { name: "Collecting forecast snapshots" }),
  ).toHaveCount(0);
  const waveResponse = page.waitForResponse(
    (r) =>
      r.url().includes("weatherVariable=wave_height") && r.status() === 200,
  );
  await page.getByLabel("Weather variable").selectOption("wave_height");
  const waves = await (await waveResponse).json();
  expect(waves.weatherFeedback.forecasts).toHaveLength(65);
  expect(
    waves.weatherFeedback.forecasts.every(
      (r: { variable: string }) => r.variable === "wave_height",
    ),
  ).toBeTruthy();
  await page.getByRole("tab", { name: "Cameras", exact: true }).click();
  await page.getByRole("button", { name: "Register camera viewpoint" }).click();
  await page
    .getByRole("combobox", { name: "Port", exact: true })
    .selectOption("INNSA");
  await page.getByLabel("Camera ID", { exact: true }).fill(cameraId);
  await page
    .getByLabel("Viewpoint name", { exact: true })
    .fill(`QA authorized viewpoint ${suffix}`);
  await page
    .getByLabel("Coverage description")
    .fill("QA camera fixture, one quay only");
  await page.getByLabel("Source / feed owner").fill("QA fixture owner");
  await page
    .getByLabel("Permission or public licence basis")
    .fill("Owned QA fixture; no private camera connected");
  await page.getByRole("button", { name: "Save camera", exact: true }).click();
  await expect(
    page.getByText(`QA authorized viewpoint ${suffix}`, { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByTestId("open-intelligence").click();
  await page.getByRole("tab", { name: "Cameras", exact: true }).click();
  await expect(
    page.getByText(`QA authorized viewpoint ${suffix}`, { exact: true }),
  ).toBeVisible();
  const saved = await http(context, "/intelligence/cameras", token);
  const camera = saved.cameras.find((c: { id: string }) => c.id === cameraId);
  expect(camera.registeredBy).toBe(admin.user.id);
  const registration = Object.fromEntries(
    [
      "id",
      "portCode",
      "name",
      "lat",
      "lon",
      "coverage",
      "viewpoint",
      "mediaUrl",
      "feedType",
      "access",
      "source",
      "rightsBasis",
      "enabled",
      "poseBasis",
    ].map((k) => [k, camera[k]]),
  );
  await http(context, "/intelligence/cameras", token, {
    ...registration,
    mediaUrl: "https://camera.qa.invalid/live.png",
  });
  const replayAt = new Date(Date.now() - 4 * 86400_000).toISOString();
  await http(context, "/intelligence/camera-evidence", token, {
    id: `later-${suffix}`,
    cameraId,
    observedAt: replayAt,
    kind: "berth_occupied",
    confidence: 0.8,
    summary: "QA observation recorded later",
    source: "QA operator",
  });
  const liveRequests: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("camera.qa.invalid")) liveRequests.push(r.url());
  });
  try {
    await http(context, "/world/clock", token, {
      mode: "REPLAY",
      at: replayAt,
    });
    const historical = await http(context, "/intelligence/cameras", token);
    expect(
      historical.cameras.every(
        (c: { mediaUrl: string | null }) => c.mediaUrl === null,
      ),
    ).toBeTruthy();
    expect(
      historical.evidence.some(
        (e: { id: string }) => e.id === `later-${suffix}`,
      ),
    ).toBeFalsy();
    await page.reload();
    await page.getByTestId("open-intelligence").click();
    await page.getByRole("tab", { name: "Cameras", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Live feed withheld during replay" }),
    ).toBeVisible();
    expect(liveRequests).toEqual([]);
    await expect(
      page.locator(".intel-camera-media img, .intel-camera-media video"),
    ).toHaveCount(0);
  } finally {
    await http(context, "/world/clock", token, { mode: "LIVE" });
  }
});

test("verified decision approval, real advisory issue and recipient acknowledgment persist", async ({
  browser,
  context,
  page,
}) => {
  const port = await login(page, "port");
  const problem = await http(context, "/decisions/problems", port.accessToken, {
    domain: "port",
    portCode: "INNSA",
    mode: "DEMO",
  });
  const option =
    problem.options.find(
      (o: { feasible: boolean; isBaseline: boolean; action: string }) =>
        o.feasible && !o.isBaseline && o.action === "SHIFT_ARRIVAL_SLOT",
    ) ??
    problem.options.find(
      (o: { feasible: boolean; isBaseline: boolean }) =>
        o.feasible && !o.isBaseline,
    );
  expect(
    option,
    "A feasible port recommendation is needed for the advisory handoff",
  ).toBeTruthy();
  const id = problem.decisionId;
  await http(
    context,
    `/decisions/problems/${id}/transition`,
    port.accessToken,
    { target: "REVIEWED" },
  );
  await http(
    context,
    `/decisions/problems/${id}/transition`,
    port.accessToken,
    {
      target: "APPROVED",
      optionId: option.optionId,
      acknowledgeMovedWorld: true,
    },
  );
  const handoff = await http(
    context,
    `/decisions/problems/${id}/handoff`,
    port.accessToken,
    { recipientOrganisation: "QA Shipping" },
  );
  expect(handoff.advisories.length).toBeGreaterThan(0);
  const advisoryId = handoff.advisories[0].advisoryId;
  await page.goto("/port/advisories");
  const card = page
    .getByTestId("advisory-card")
    .filter({ hasText: handoff.advisories[0].recipientVesselName })
    .first();
  await card.locator("button").first().click();
  await card.getByTestId("advisory-action-under_review").click();
  await card.getByTestId("advisory-action-issued").click();
  await page.getByRole("button", { name: /^Issued/ }).click();
  await expect(
    page
      .getByTestId("advisory-card")
      .filter({ hasText: handoff.advisories[0].recipientVesselName })
      .first(),
  ).toContainText("Issued");
  const recipient = await browser.newContext();
  const recipientPage = await recipient.newPage();
  try {
    const company = await login(recipientPage, "company");
    await recipientPage.goto("/company/advisories");
    const received = recipientPage
      .getByTestId("advisory-card")
      .filter({ hasText: handoff.advisories[0].recipientVesselName })
      .first();
    await received.locator("button").first().click();
    await received.getByTestId("advisory-action-acknowledged").click();
    await expect(received).toContainText("Acknowledged");
    const saved = await http(
      recipient,
      `/advisories/${advisoryId}`,
      company.accessToken,
    );
    expect(saved.state).toBe("acknowledged");
    expect(saved.audit.at(-1).actor).toBe(company.user.id);
    expect(
      (await http(context, `/decisions/problems/${id}`, port.accessToken))
        .evidence.advisories,
    ).toContain(advisoryId);
  } finally {
    await recipient.close();
  }
});

test("verified weather observations resolve immutable originals and reject forged cross-port writes", async ({
  context,
  page,
}) => {
  const port = await login(page, "port");
  const before = await http(
    context,
    "/weather/feedback?portCode=INNSA&variable=wind_gust",
    port.accessToken,
  );
  const row = before.forecasts[0];
  expect(row.original).toBe(20);
  const observation = {
    portCode: "INNSA",
    variable: "wind_gust",
    validAt: row.validAt,
    availableAt: new Date(Date.now() - 60_000).toISOString(),
    value: 29,
    unit: "kn",
    statistic: "maximum",
    source: "QA simulated operator measurement",
    kind: "operator_measurement",
  };
  const other = await context.request.post(`${API}/auth/login`, {
    data: { email: "other@qa.invalid", password: "qa-only-verified-password" },
  });
  expect(other.ok()).toBeTruthy();
  const denied = await context.request.post(`${API}/weather/observations`, {
    headers: {
      Authorization: `Bearer ${(await other.json()).accessToken}`,
      "X-PortWatch-Role": "NATIONAL_ADMIN",
      "X-PortWatch-Port": "INNSA",
    },
    data: observation,
  });
  expect(denied.status()).toBe(403);
  await http(context, "/weather/observations", port.accessToken, observation);
  const after = await http(
    context,
    "/weather/feedback?portCode=INNSA&variable=wind_gust",
    port.accessToken,
  );
  expect(after.forecasts[0].original).toBe(20);
  expect(after.forecasts[0].observed).toBe(29);
  expect(after.forecasts[0].status).toBe("resolved");
  expect(after.forecasts[0].correction.status).toBe("COLLECTING");
});
