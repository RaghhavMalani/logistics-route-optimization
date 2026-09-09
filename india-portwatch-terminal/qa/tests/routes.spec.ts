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
  ],
  PORT_OPERATOR: [
    { path: "/port/overview", heading: "Chennai Port Control" },
    { path: "/port/operations", heading: "Operations" },
    { path: "/port/forecast", heading: "Forecast" },
    { path: "/port/vessels", heading: "Vessels" },
    { path: "/port/weather", heading: "Weather" },
    { path: "/port/events", heading: "Events" },
    { path: "/port/decisions", heading: "Decisions" },
  ],
  ADMIN: [
    { path: "/admin/radar", heading: "National Command" },
    { path: "/admin/ports", heading: "Ports" },
    { path: "/admin/vessels", heading: "Vessels" },
    { path: "/admin/model", heading: "Model Intelligence" },
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
  ];

  for (const [from, to] of REDIRECTS) {
    test(`${from} resolves to ${to}`, async ({ context, page }) => {
      await seedSession(context, "ADMIN");
      await page.goto(from);
      await settle(page);
      await expect(page).toHaveURL(new RegExp(`${to.replace(/\//g, "\\/")}$`));
    });
  }
});

test("an unknown workspace address is reported, not blank", async ({ context, page }) => {
  await seedSession(context, "ADMIN");
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
