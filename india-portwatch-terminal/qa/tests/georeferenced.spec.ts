import { test, expect, settle, ACCOUNTS, type Role } from "../harness";

// The shared harness predates server-issued demo sessions. Adapt only this suite.
async function seedSession(
  context: import("@playwright/test").BrowserContext,
  role: Role,
) {
  const session = {
    user: ACCOUNTS[role],
    mode: "demo",
    accessToken: "geometry-test-session",
    issuedAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 3600000).toISOString(),
  };
  await context.addInitScript((value) => {
    localStorage.setItem("portwatch.session.v1", JSON.stringify(value));
    sessionStorage.setItem("portwatch.session.v1", JSON.stringify(value));
    localStorage.setItem(
      "portwatch.viewAs.v1",
      JSON.stringify(value.user.role),
    );
    sessionStorage.setItem(
      "portwatch.viewAs.v1",
      JSON.stringify(value.user.role),
    );
  }, session);
  await context.route("**/api/demo/session", (route) =>
    route.fulfill({ json: session }),
  );
  await context.route("**/api/demo/terminal/**", (route) =>
    route.fallback({
      url: route.request().url().replace("/demo/terminal/", "/"),
    }),
  );
}

async function openPilot(page: import("@playwright/test").Page) {
  await page.goto("/admin/twins");
  await settle(page);
  await page
    .getByRole("combobox", { name: "Select the port to inspect" })
    .selectOption("INNSA");
  await expect(page.getByTestId("twin-geography-toggle")).toBeVisible();
}

test("geographic preview preserves inspector, layers, horizons and schematic reference", async ({
  context,
  page,
  recorder,
}, info) => {
  await seedSession(context, "NATIONAL_ADMIN");
  await openPilot(page);
  await page.screenshot({ path: info.outputPath("before-schematic.png") });
  await page.getByTestId("twin-geography-toggle").click();
  const scene = page.getByTestId("georeferenced-port-scene");
  await expect(scene).toBeVisible();
  await expect(scene.locator("canvas")).toBeVisible();
  await expect(
    page.getByText("horizontal accuracy unverified", { exact: false }).first(),
  ).toBeVisible();
  await page.screenshot({ path: info.outputPath("after-geography.png") });
  await scene.getByRole("button", { name: "2D plan", exact: true }).click();
  const footprint = scene.locator("svg path").nth(3);
  await footprint.dispatchEvent("click");
  await expect(page.getByTestId("twin-inspector")).toContainText(
    "Operational mapping",
  );
  await expect(page.getByTestId("twin-inspector")).toContainText(
    "review required",
  );
  const selected =
    (await page.getByTestId("twin-inspector").textContent()) ?? "";
  await scene
    .getByRole("checkbox", { name: "building", exact: true })
    .uncheck();
  await expect(page.getByTestId("twin-inspector")).toHaveText(selected);
  await page.getByRole("button", { name: "+6h", exact: true }).click();
  await expect(page.getByTestId("twin-inspector")).toHaveText(selected);
  await scene.getByRole("button", { name: "Reset / oblique" }).click();
  await expect(scene.locator("canvas")).toBeVisible();
  await scene.getByRole("button", { name: "Fit selection" }).click();
  await scene
    .getByRole("button", { name: "Schematic reference", exact: true })
    .click();
  await expect(page.getByTestId("port-twin-scene")).toBeVisible();
  await expect(page.getByTestId("twin-schematic-banner")).toContainText(
    "not a surveyed port plan",
  );
  await page.getByTestId("twin-geography-toggle").click();
  await expect(scene.locator("canvas")).toBeVisible();
  await page
    .getByRole("combobox", { name: "Select the port to inspect" })
    .selectOption("INMAA");
  await expect(scene).toHaveCount(0);
  await expect(page.getByTestId("port-twin-scene")).toBeVisible();
  expect(recorder.pageErrors).toEqual([]);
});

test("missing geographic assets offer schematic fallback", async ({
  context,
  page,
}) => {
  await seedSession(context, "NATIONAL_ADMIN");
  await context.route("**/port-geometry/**", (r) =>
    r.fulfill({ status: 404, body: "Unavailable" }),
  );
  await openPilot(page);
  await page.getByTestId("twin-geography-toggle").click();
  await expect(page.getByRole("status")).toContainText("Geometry unavailable");
  await page.getByRole("button", { name: "Open schematic reference" }).click();
  await expect(page.getByTestId("port-twin-scene")).toBeVisible();
});

test("lost WebGL context exposes selectable 2D geography", async ({
  context,
  page,
  recorder,
}) => {
  await seedSession(context, "NATIONAL_ADMIN");
  await openPilot(page);
  await page.getByTestId("twin-geography-toggle").click();
  const scene = page.getByTestId("georeferenced-port-scene");
  await expect(scene.locator("canvas")).toBeVisible();
  await scene
    .locator("canvas")
    .evaluate((canvas) =>
      canvas.dispatchEvent(new Event("webglcontextlost", { cancelable: true })),
    );
  await expect(scene.getByRole("img")).toBeVisible();
  await expect(scene.locator("canvas")).toHaveCount(0);
  await scene.locator("svg path").nth(1).dispatchEvent("click");
  await expect(page.getByTestId("twin-inspector")).toContainText("Feature ID");
  expect(recorder.pageErrors).toEqual([]);
});

for (const [role, path, heading] of [
  ["VESSEL_OPERATOR", "/vessel/overview", "Fleet Bridge"],
  ["SHIPPING_COMPANY", "/company/overview", "Fleet Command"],
  ["PORT_AUTHORITY", "/port/overview", "Chennai Port Control"],
  ["NATIONAL_ADMIN", "/admin/radar", "National Command"],
] as const) {
  test(`native ${role} workspace remains available`, async ({
    context,
    page,
    recorder,
  }) => {
    await seedSession(context, role);
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(heading);
    expect(recorder.pageErrors).toEqual([]);
  });
}
