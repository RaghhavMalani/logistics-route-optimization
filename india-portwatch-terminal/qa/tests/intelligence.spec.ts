import { readFileSync } from "node:fs";
import { test as liveTest, type Page } from "@playwright/test";
import {
  expect,
  horizontalOverflow,
  seedSession,
  settle,
  test,
} from "../harness";

const intelligence = JSON.parse(
  readFileSync(
    new URL("../fixtures/intelligence_context.json", import.meta.url),
    "utf8",
  ),
) as { ports: { code: string }[] };

liveTest(
  "a real local demo token cannot register a private camera",
  async ({ page }) => {
    await page.goto("/login");
    const opened = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname.endsWith("/api/demo/session") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Admin demo", exact: true }).click();
    const response = await opened;
    const url = new URL(response.url());
    expect(url.hostname).toBe("127.0.0.1");
    expect(response.ok()).toBe(true);
    const session = await response.json();
    url.pathname = url.pathname.replace(
      /\/demo\/session$/,
      "/intelligence/cameras",
    );
    const denied = await page.request.post(url.href, {
      headers: { Authorization: `Bearer ${session.accessToken}` },
      data: {
        id: "qa-denied-private-camera",
        portCode: "INNSA",
        name: "QA denied camera",
        lat: 18.95,
        lon: 72.95,
        coverage: "Synthetic test record",
        source: "QA",
        rightsBasis: "Synthetic fixture with no media",
      },
    });
    expect([401, 403]).toContain(denied.status());
    await expect(
      page.getByRole("button", { name: "Register camera viewpoint" }),
    ).toHaveCount(0);
  },
);

async function openGlobeTab(page: Page) {
  await page.goto("/admin/global-eye#intelligence-review");
  await settle(page);
  const globeTab = page.getByRole("tab", { name: "Globe", exact: true });
  const dialog = page.getByRole("dialog").filter({ has: globeTab });
  await expect(dialog).toBeVisible();
  await globeTab.click();
  return dialog;
}

test("opens the native globe with the retained ports and releases it on return to the chart", async ({
  context,
  page,
  recorder,
}) => {
  await seedSession(context, "NATIONAL_ADMIN");
  const source = page.waitForResponse((r) =>
    new URL(r.url()).pathname.endsWith("/api/intelligence/context"),
  );
  const dialog = await openGlobeTab(page);
  const before = await page.locator(".maplibregl-canvas").elementHandle();
  expect(
    (await (await source).json()).ports.map(
      (port: { code: string }) => port.code,
    ),
  ).toEqual(intelligence.ports.map((port) => port.code));
  await dialog
    .getByRole("button", { name: "Open God’s Eye globe", exact: true })
    .click();
  await expect(dialog.locator(".cesium-widget canvas")).toBeVisible({
    timeout: 30000,
  });
  await expect(dialog.getByText(/God’s Eye View · MIT/)).toBeVisible();
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(1);
  await dialog
    .getByRole("button", { name: "Hide additional globe", exact: true })
    .click();
  await expect(dialog.locator(".cesium-widget canvas")).toHaveCount(0);
  await dialog
    .getByRole("button", { name: "Close intelligence", exact: true })
    .click();
  expect(await before?.evaluate((canvas) => canvas.isConnected)).toBe(true);
  expect(recorder.pageErrors).toEqual([]);
});

test("inspects original, corrected and verified weather outcome", async ({
  context,
  page,
}) => {
  await seedSession(context, "NATIONAL_ADMIN");
  await context.route("**/api/weather/feedback?**", (route) =>
    route.fulfill({
      json: {
        total: 1,
        resolved: 1,
        pending: 0,
        scores: [],
        note: "Presentation fixture with one labelled station outcome.",
        forecasts: [
          {
            id: "qa-wind",
            portCode: "INNSA",
            horizonDays: 5,
            unit: "kn",
            issuedAt: "2026-10-10T00:00:00Z",
            targetDate: "2026-10-15",
            original: 12,
            corrected: 11,
            observed: 14,
            observationSource: "QA station fixture",
            correction: { status: "COLLECTING", sampleCount: 1 },
          },
        ],
      },
    }),
  );
  await page.goto("/admin/learning");
  const table = page
    .getByRole("table")
    .filter({ hasText: "QA station fixture" });
  for (const name of ["Original", "Corrected", "Observed"]) {
    await expect(
      table.getByRole("columnheader", { name, exact: true }),
    ).toBeVisible();
  }
  await expect(
    table.getByRole("row").filter({ hasText: "QA station fixture" }),
  ).toContainText("12.0011.0014.00");
  await expect(table.getByText("COLLECTING", { exact: true })).toBeVisible();
});

test("malformed globe context can be retried without losing the maritime chart", async ({
  context,
  page,
}) => {
  await seedSession(context, "NATIONAL_ADMIN");
  const malformed = "**/api/intelligence/context?**";
  await context.route(malformed, (route) =>
    route.fulfill({ json: { ports: "bad shape" } }),
  );
  const dialog = await openGlobeTab(page);
  await expect(
    dialog
      .getByRole("alert")
      .filter({ hasText: "does not match the API contract" }),
  ).toBeVisible();
  await context.unroute(malformed);
  await dialog
    .getByRole("button", { name: "Retry connection", exact: true })
    .click();
  await expect(dialog.getByText(/Context unavailable/)).toHaveCount(0);
  await expect(page.locator(".maplibregl-canvas")).toBeAttached();
});

for (const status of ["LIVE", "STALE"] as const) {
  test(`globe uses backend earthquakes with a labelled ${status} receipt`, async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await context.route("**/api/intelligence/earthquakes", (route) =>
      route.fulfill({
        json: {
          type: "FeatureCollection",
          features:
            status === "STALE"
              ? []
              : [
                  {
                    type: "Feature",
                    id: "qa-quake",
                    geometry: { type: "Point", coordinates: [72, 19, 5] },
                    properties: {
                      mag: 4,
                      place: "QA earthquake fixture",
                      time: Date.now(),
                    },
                  },
                ],
          portwatch: {
            status,
            fetchedAt: "2026-10-06T00:00:00Z",
            source: "USGS",
          },
        },
      }),
    );
    const dialog = await openGlobeTab(page);
    if (status === "STALE") {
      await dialog.getByRole("tab", { name: "Scenarios", exact: true }).focus();
      await page.keyboard.press("ArrowRight");
      const globe = dialog.getByRole("tab", { name: "Globe", exact: true });
      await expect(globe).toBeFocused();
      await expect(globe).toHaveAttribute("aria-selected", "true");
    }
    await dialog
      .getByRole("button", { name: "Open God’s Eye globe", exact: true })
      .click();
    await dialog
      .getByRole("checkbox", { name: "Earthquakes", exact: true })
      .check();
    await expect(
      dialog.getByText(
        new RegExp(
          `${status === "LIVE" ? 1 : 0} USGS events · ${status} snapshot · retrieved`,
        ),
      ),
    ).toBeVisible({ timeout: 30000 });
  });
}

test("global intelligence stays reachable during a shipping cascade outage", async ({
  context,
  page,
}) => {
  await seedSession(context, "NATIONAL_ADMIN");
  await context.route("**/api/world/cascades*", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "QA shipping cascade outage" },
    }),
  );
  const dialog = await openGlobeTab(page);
  await expect(
    dialog.getByRole("heading", { name: "Global intelligence", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Shipping consequence feed unavailable.", { exact: true }),
  ).toHaveCount(1, { timeout: 20_000 });
  await dialog
    .getByRole("button", { name: "Open God’s Eye globe", exact: true })
    .click();
  await expect(dialog.locator(".cesium-widget canvas")).toBeVisible({
    timeout: 30000,
  });
});
