/**
 * Every screen, for the role that owns it.
 *
 * The assertion is deliberately not "it rendered": a screen that throws a
 * console error, drops a request or pushes the page sideways at 1366px is
 * broken even though it painted. All three are checked on every route.
 */

import {
  expect,
  horizontalOverflow,
  seedSession,
  settle,
  test,
  type Role,
} from "../harness";

interface Screen {
  path: string;
  heading: string;
}

const SCREENS: Record<Role, Screen[]> = {
  VESSEL_OPERATOR: [
    { path: "/vessel/overview", heading: "Fleet Bridge" },
    { path: "/vessel/fleet", heading: "Fleet" },
    { path: "/vessel/MV-KONKAN", heading: "MV Konkan" },
    { path: "/vessel/routes", heading: "Route Intelligence" },
    { path: "/vessel/ports", heading: "Destination Ports" },
    { path: "/vessel/alerts", heading: "Alerts" },
    { path: "/vessel/advisories", heading: "Advisories" },
  ],
  SHIPPING_COMPANY: [
    { path: "/company/overview", heading: "Fleet Command" },
    { path: "/company/fleet", heading: "Fleet" },
    { path: "/company/routes", heading: "Routes" },
    { path: "/company/risk", heading: "Risk" },
    { path: "/company/global-eye", heading: "Global Eye — Fleet exposure" },
    { path: "/company/advisories", heading: "Advisories" },
  ],
  PORT_AUTHORITY: [
    { path: "/port/overview", heading: "Chennai Port Control" },
    { path: "/port/operations", heading: "Operations" },
    { path: "/port/forecast", heading: "Forecast" },
    { path: "/port/vessels", heading: "Vessels" },
    { path: "/port/weather", heading: "Weather" },
    { path: "/port/events", heading: "Events" },
    { path: "/port/decisions", heading: "Decisions" },
    { path: "/port/advisories", heading: "Advisories" },
    { path: "/port/global-eye", heading: "Global Eye — Exposure here" },
  ],
  NATIONAL_ADMIN: [
    { path: "/admin/radar", heading: "National Command" },
    { path: "/admin/global-eye", heading: "Global Eye" },
    { path: "/admin/ports", heading: "Ports" },
    { path: "/admin/vessels", heading: "Vessels" },
    { path: "/admin/companies", heading: "Companies" },
    { path: "/admin/model", heading: "Model Intelligence" },
    { path: "/admin/learning", heading: "Learning" },
    { path: "/admin/agents", heading: "Agents" },
    { path: "/admin/scenarios", heading: "Scenario Room" },
    { path: "/admin/intelligence", heading: "Event Intelligence" },
    { path: "/admin/data", heading: "Data Sources" },
    { path: "/admin/system", heading: "System" },
  ],
};

for (const [role, screens] of Object.entries(SCREENS) as Array<[Role, Screen[]]>) {
  test.describe(`${role} workspace`, () => {
    for (const screen of screens) {
      test(`${screen.path} renders cleanly`, async ({ context, page, recorder }) => {
        await seedSession(context, role);
        await page.goto(screen.path);
        await settle(page);

        await expect(page.getByRole("heading", { level: 1 })).toHaveText(screen.heading);
        expect(page.url()).toContain(screen.path);

        expect(recorder.pageErrors, "uncaught page errors").toEqual([]);
        expect(recorder.consoleErrors, "console errors").toEqual([]);
        expect(recorder.failedRequests, "failed requests").toEqual([]);
        expect(await horizontalOverflow(page), "horizontal page overflow").toBeLessThanOrEqual(0);
      });
    }
  });
}

/**
 * The 3D twin is checked separately.
 *
 * It creates a second WebGL context on top of the map's, which the software
 * renderer the suite runs on will refuse if too many are alive at once. Giving
 * it its own case keeps that failure from looking like a fault in whichever
 * screen happened to run before it.
 */
test.describe("3D digital twin", () => {
  for (const [role, path] of [
    ["PORT_AUTHORITY", "/port/twin"],
    ["NATIONAL_ADMIN", "/admin/twins"],
  ] as Array<[Role, string]>) {
    test(`${path} renders with its schematic banner`, async ({ context, page, recorder }) => {
      await seedSession(context, role);
      await page.goto(path);
      await settle(page);

      // The banner is the point. A schematic twin that does not say so is the
      // one thing this screen must never be.
      await expect(page.getByTestId("twin-schematic-banner")).toBeVisible();
      await expect(
        page.getByText(/not a surveyed port plan/i).first(),
      ).toBeVisible();

      await expect(page.getByTestId("twin-inspector")).toBeVisible();
      await expect(page.getByTestId("twin-optimizer")).toBeVisible();

      expect(recorder.pageErrors, "uncaught page errors").toEqual([]);
      expect(await horizontalOverflow(page), "horizontal page overflow").toBeLessThanOrEqual(0);
    });
  }
});

test.describe("cargo", () => {
  test("the port assignment names why a shipment could not be placed", async ({
    context,
    page,
    recorder,
  }) => {
    await seedSession(context, "PORT_AUTHORITY");
    await page.goto("/port/cargo");
    await settle(page);

    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Cargo assignment");
    await expect(page.getByText(/Demo cargo flow/i)).toBeVisible();
    await expect(page.getByTestId("cargo-assignments")).toBeVisible();
    await expect(page.getByTestId("cargo-unplaced")).toBeVisible();

    expect(recorder.pageErrors).toEqual([]);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  });

  test("a company sees opportunities rather than a committed plan", async ({
    context,
    page,
  }) => {
    await seedSession(context, "SHIPPING_COMPANY");
    await page.goto("/company/cargo");
    await settle(page);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Cargo connections");
  });
});

test.describe("legacy addresses", () => {
  const REDIRECTS: Array<[string, string]> = [
    ["/fleet", "/vessel/fleet"],
    ["/model", "/admin/model"],
    ["/sim", "/admin/scenarios"],
    ["/sar", "/admin/vessels"],
    ["/nlp", "/admin/intelligence"],
    ["/wx", "/port/weather"],
    ["/port", "/port/overview"],
    ["/admin", "/admin/radar"],
    ["/vessel", "/vessel/overview"],
    ["/company", "/company/overview"],
  ];

  for (const [from, to] of REDIRECTS) {
    test(`${from} resolves to ${to}`, async ({ context, page }) => {
      await seedSession(context, "NATIONAL_ADMIN");
      await page.goto(from);
      await settle(page);
      await expect(page).toHaveURL(new RegExp(`${to.replace(/\//g, "\\/")}$`));
    });
  }
});

test("an unknown workspace address is reported, not blank", async ({ context, page }) => {
  await seedSession(context, "NATIONAL_ADMIN");
  await page.goto("/admin/does-not-exist");
  await settle(page);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Screen not found");
  await expect(page.getByText("No screen at this address")).toBeVisible();
  // The shell stays: the operator can navigate on without using the back button.
  await expect(page.getByRole("navigation", { name: "Workspace" })).toBeVisible();
});

test("an unknown address outside any workspace is reported", async ({ page }) => {
  await page.goto("/nowhere-at-all");
  await expect(page.getByText("Route not found")).toBeVisible();
});
