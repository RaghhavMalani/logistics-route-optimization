import { test, expect, settle, ACCOUNTS, type Role } from "../harness";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const release = path.resolve(
  "../data/port_geometry/INNSA/authority-20261019-v2",
);
const geometry = JSON.parse(
  fs.readFileSync(path.join(release, "footprints.geojson"), "utf8"),
);
const layerCatalogue = JSON.parse(
  fs.readFileSync(path.join(release, "layers.json"), "utf8"),
);

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
  await context.route(
    /\/api\/(?:demo\/terminal\/)?port-twin\/INNSA\/simulate\?/,
    (r) => {
      const fixture = JSON.parse(
        fs.readFileSync(
          path.resolve("qa/fixtures/port-twin_INNSA_simulate.json"),
          "utf8",
        ),
      );
      const hours = Number(
        new URL(r.request().url()).searchParams.get("horizon_hours"),
      );
      // Explicit synthetic response to verify request/state identity, not simulator physics.
      fixture.horizonHours = hours;
      fixture.finalState.hour = hours;
      fixture.metrics.hour = hours;
      return r.fulfill({ json: fixture });
    },
  );
  await context.route("**/api/public/port-geometry/INNSA/geometry", (r) =>
    r.fulfill({ json: geometry }),
  );
  await context.route("**/api/public/port-geometry/INNSA/layers", (r) =>
    r.fulfill({ json: layerCatalogue }),
  );
  await context.route(
    "**/api/public/port-geometry/INNSA/reference-image",
    (r) =>
      r.fulfill({
        contentType: "image/png",
        body: fs.readFileSync(path.join(release, "reference/reference.png")),
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
  await expect(scene.getByTestId("remote-geospatial-layers")).toContainText(
    "2026-03-22",
  );
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

test("expired and malformed GEE layers leave geography usable", async ({
  context,
  page,
}) => {
  await seedSession(context, "NATIONAL_ADMIN");
  const expired = structuredClone(layerCatalogue);
  expired.layers[0].displayResource.expiresAt = "2020-01-01T00:00:00Z";
  await context.route("**/api/public/port-geometry/INNSA/layers", (r) =>
    r.fulfill({ json: expired }),
  );
  await openPilot(page);
  await page.getByTestId("twin-geography-toggle").click();
  const scene = page.getByTestId("georeferenced-port-scene");
  await expect(scene.getByText(/expired — refresh required/)).toBeVisible();
  await expect(
    scene.getByRole("checkbox", { name: /innsa-sentinel2/ }),
  ).toBeDisabled();
  const bad = structuredClone(layerCatalogue);
  bad.layers[0].horizontalCrs = "EPSG:3857";
  await context.route("**/api/public/port-geometry/INNSA/layers", (r) =>
    r.fulfill({ json: bad }),
  );
  await scene.getByRole("button", { name: "Refresh layers" }).click();
  await expect(scene.getByTestId("remote-geospatial-layers")).toContainText(
    "Invalid layer identity or CRS",
  );
  await expect(scene.locator("canvas")).toBeVisible();
});

test("reviewed operational ID fixture updates without rebuilding geometry", async ({
  context,
  page,
}) => {
  await seedSession(context, "NATIONAL_ADMIN");
  const mapped = structuredClone(geometry);
  // Synthetic test-only mapping. The retained real release remains unmapped.
  mapped.operationalMappings = [
    {
      featureId: "jnpa-berth-12",
      operationalAssetId: "B1",
      status: "reviewed",
      reviewedBy: "test fixture",
      reviewedAt: "2026-10-19",
    },
  ];
  await context.route("**/api/public/port-geometry/INNSA/geometry", (r) =>
    r.fulfill({ json: mapped }),
  );
  await openPilot(page);
  await page.getByTestId("twin-geography-toggle").click();
  const scene = page.getByTestId("georeferenced-port-scene");
  await scene.getByRole("button", { name: "2D plan", exact: true }).click();
  await scene
    .locator("svg path")
    .filter({ has: page.locator("title", { hasText: "NSIGT" }) })
    .first()
    .dispatchEvent("click");
  await expect(page.getByTestId("twin-inspector")).toContainText(
    "Operational ID",
  );
  await expect(page.getByTestId("twin-inspector")).toContainText("B1");
  await scene.getByRole("button", { name: "Reset / oblique" }).click();
  const canvas = scene.locator("canvas");
  await canvas.evaluate((el) =>
    el.setAttribute("data-identity-check", "retained"),
  );
  const selectedHorizonRequest = page.waitForRequest(
    (r) =>
      r.url().includes("/simulate?") &&
      new URL(r.url()).searchParams.get("horizon_hours") === "6",
  );
  await page.getByRole("button", { name: "+6h", exact: true }).click();
  await selectedHorizonRequest;
  await expect(canvas).toHaveAttribute("data-identity-check", "retained");
  await expect(page.getByTestId("twin-inspector")).toContainText("B1");
  await expect(page.getByTestId("twin-inspector")).toContainText(
    "Simulation hour 6",
  );
});

test("record geographic interaction performance", async ({
  context,
  page,
  browser,
}, info) => {
  await seedSession(context, "NATIONAL_ADMIN");
  await openPilot(page);
  await page.getByTestId("twin-geography-toggle").click();
  const canvas = page.getByTestId("georeferenced-port-scene").locator("canvas");
  await expect(canvas).toBeVisible();
  const initialTriangles = Number(await canvas.getAttribute("data-triangles"));
  await page
    .getByRole("checkbox", { name: "Illustrative building height: 6 m" })
    .check();
  await expect
    .poll(async () => Number(await canvas.getAttribute("data-triangles")))
    .toBeGreaterThan(initialTriangles);
  await expect(page.getByTestId("remote-geospatial-layers")).toContainText(
    "10 m native",
  );
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.65);
  await page.mouse.down();
  await page.evaluate(() => {
    const samples: number[] = [];
    let previous = performance.now();
    const start = previous;
    const tick = (now: number) => {
      samples.push(now - previous);
      previous = now;
      if (now - start < 2200) requestAnimationFrame(tick);
    };
    (window as unknown as { portFrames: number[] }).portFrames = samples;
    requestAnimationFrame(tick);
  });
  for (let i = 0; i < 70; i++) {
    await page.mouse.move(
      box.x + box.width * (0.5 + 0.2 * Math.sin(i / 15)),
      box.y + box.height * 0.65,
    );
    await page.waitForTimeout(25);
  }
  await page.mouse.up();
  const measurement = await canvas.evaluate((el) => {
    const samples = (window as unknown as { portFrames: number[] }).portFrames
      .filter((v) => v > 0)
      .sort((a, b) => a - b);
    const gl = (el as HTMLCanvasElement).getContext("webgl2");
    return {
      samples: samples.length,
      medianFrameMs: samples[Math.floor(samples.length * 0.5)],
      p95FrameMs: samples[Math.floor(samples.length * 0.95)],
      meanFrameMs: samples.reduce((a, b) => a + b, 0) / samples.length,
      drawCalls: el.getAttribute("data-draw-calls"),
      triangles: el.getAttribute("data-triangles"),
      glVendor: gl?.getParameter(gl.VENDOR),
      glRenderer: gl?.getParameter(gl.RENDERER),
    };
  });
  fs.writeFileSync(
    info.outputPath("performance.json"),
    JSON.stringify(
      {
        ...measurement,
        approximateFps: 1000 / measurement.meanFrameMs,
        browser: browser.version(),
        cpu: os.cpus()[0]?.model,
        platform: os.platform(),
        viewport: page.viewportSize(),
        featureCount: geometry.features.length,
        mode: "Headless interaction with dated raster and explicitly illustrative 6m building extrusion; frame cadence includes application workload",
      },
      null,
      2,
    ),
  );
  expect(measurement.samples).toBeGreaterThan(10);
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
