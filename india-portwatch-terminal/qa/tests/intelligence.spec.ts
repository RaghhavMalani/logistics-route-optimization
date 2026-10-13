import path from "node:path";
import {
  expect,
  horizontalOverflow,
  seedSession,
  settle,
  test,
} from "../harness";

test.describe("global intelligence integration", () => {
  test.beforeEach(async ({ context }) => {
    // The inherited shell imports web fonts; offline tests use its CSS fallback.
    await context.route("https://fonts.googleapis.com/**", (route) =>
      route.fulfill({ status: 200, contentType: "text/css", body: "" }),
    );
  });
  test("opens native globe, keeps all ports available and releases the previous renderer", async ({
    context,
    page,
    recorder,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);
    await page.getByTestId("open-intelligence").click();
    await expect(
      page.getByRole("heading", { name: "Global intelligence", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByTestId("intelligence-port-select").locator("option"),
    ).toHaveCount(14);
    await expect(page.locator(".cesium-widget canvas")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText("Preparing global scene…")).toHaveCount(0);
    await expect(page.locator(".maplibregl-canvas")).toHaveCount(0);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(1);
    await page.screenshot({
      path: path.resolve("qa/shots/global-intelligence.png"),
    });
    await page
      .getByRole("button", { name: "Shipping workspace", exact: true })
      .click();
    await expect(page.locator(".cesium-widget canvas")).toHaveCount(0);
    await expect(page.getByTestId("open-intelligence")).toBeVisible();
    expect(recorder.pageErrors).toEqual([]);
    expect(recorder.consoleErrors).toEqual([]);
  });

  test("inspects original, corrected and verified weather outcome", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);
    await page.getByTestId("open-intelligence").click();
    await page.getByRole("tab", { name: "Forecasts", exact: true }).click();
    const inspection = page.getByTestId("forecast-inspection");
    await expect(inspection).toContainText("Original");
    await expect(inspection).toContainText("Corrected");
    await expect(inspection).toContainText("Observed");
    await expect(inspection).toContainText("QA station fixture");
    await expect(inspection).toContainText("COLLECTING");
  });

  test("demo roles cannot register private camera viewpoints", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);
    await page.getByTestId("open-intelligence").click();
    await page.getByRole("tab", { name: "Cameras", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "No camera feeds registered" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Register camera viewpoint" }),
    ).toHaveCount(0);
    await expect(
      page.getByText(/registration requires a verified authority account/),
    ).toBeVisible();
  });

  test("invalid API contracts produce a retryable error", async ({
    context,
    page,
  }) => {
    await context.route("**/api/intelligence/context*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ports: "bad shape" }),
      }),
    );
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);
    await page.getByTestId("open-intelligence").click();
    await expect(
      page.getByRole("heading", { name: "Intelligence context unavailable" }),
    ).toBeVisible();
    await expect(page.getByRole("alert")).toContainText(
      "does not match the API contract",
    );
    await expect(
      page.getByRole("button", { name: "Retry connection" }),
    ).toBeVisible();
  });

  test("earthquakes use the backend provider and expose observation counts", async ({
    context,
    page,
  }) => {
    await context.route("**/api/intelligence/earthquakes", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              id: "qa-quake",
              geometry: { type: "Point", coordinates: [72, 19, 5] },
              properties: {
                mag: 4,
                place: "QA earthquake fixture",
                time: Date.now(),
                url: "https://earthquake.usgs.gov/",
              },
            },
          ],
          portwatch: {
            status: "LIVE",
            fetchedAt: new Date().toISOString(),
            source: "USGS",
          },
        }),
      }),
    );
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);
    await page.getByTestId("open-intelligence").click();
    await page.getByLabel("Global earthquakes").check();
    await expect(page.getByText(/1 USGS events · last 24h/)).toBeVisible({
      timeout: 30_000,
    });
  });

  test("keyboard tabs and stale earthquake snapshots keep their meaning", async ({
    context,
    page,
  }) => {
    await context.route("**/api/intelligence/earthquakes", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          type: "FeatureCollection",
          features: [],
          portwatch: {
            status: "STALE",
            fetchedAt: "2026-10-06T00:00:00Z",
            source: "USGS",
          },
        }),
      }),
    );
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);
    await page.getByTestId("open-intelligence").click();
    await page.getByRole("tab", { name: "Events", exact: true }).focus();
    await page.keyboard.press("ArrowRight");
    await expect(
      page.getByRole("tab", { name: "Economics", exact: true }),
    ).toBeFocused();
    await expect(
      page.getByRole("tab", { name: "Economics", exact: true }),
    ).toHaveAttribute("aria-selected", "true");
    await page.getByLabel("Global earthquakes").check();
    await expect(
      page.getByText(/0 USGS events · STALE snapshot · retrieved/),
    ).toBeVisible({ timeout: 30_000 });
  });

  test("global intelligence stays reachable when shipping cascades are unavailable", async ({
    context,
    page,
  }) => {
    await context.route("**/api/world/cascades*", (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "QA shipping cascade outage" }),
      }),
    );
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);
    await page.getByTestId("open-intelligence").click();
    await expect(
      page.getByRole("heading", { name: "Global intelligence", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByTestId("intelligence-port-select").locator("option"),
    ).toHaveCount(14);
  });
});
