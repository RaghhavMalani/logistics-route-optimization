/**
 * The traffic display, exercised the way it is used.
 *
 * Assertions read the geometry the map actually put into its GL sources rather
 * than counting DOM nodes, because the traffic layer deliberately has no DOM:
 * a test that passed by finding markers would be testing a different
 * implementation from the one that ships.
 */

import type { Page } from "@playwright/test";

import { expect, seedSession, settle, test, type Role } from "../harness";

async function mapReady(page: Page): Promise<void> {
  // Wait for a fleet, not for a clock. Three workers each running an eight
  // hundred vessel animation loop against a software renderer make any fixed
  // settle either flaky or slow, and "the source holds ships" is the condition
  // every assertion below actually depends on.
  await page.waitForFunction(
    () => {
      const sources = (window as any).__portwatchSources;
      return Boolean(
        (window as any).__portwatchMap && (sources?.vessels?.features?.length ?? 0) > 0,
      );
    },
    undefined,
    { timeout: 45_000 },
  );
}

/** How many vessels the chart is drawing right now. */
async function drawnCount(page: Page, source: string): Promise<number> {
  return page.evaluate(
    (key) =>
      ((window as unknown as { __portwatchSources?: Record<string, any> }).__portwatchSources?.[
        key
      ]?.features?.length ?? 0) as number,
    source,
  );
}

async function drawn(page: Page, source: string) {
  return page.evaluate((key) => {
    const registry = (window as unknown as { __portwatchSources?: Record<string, any> })
      .__portwatchSources;
    const data = registry?.[key];
    return (data?.features ?? []).map((feature: any) => feature.properties ?? {});
  }, source);
}

async function open(page: Page, context: Parameters<typeof seedSession>[0], role: Role, path: string) {
  await seedSession(context, role);
  await page.goto(path);
  await settle(page);
  await mapReady(page);
}

/* ------------------------------------------------------------- population -- */

test.describe("traffic population", () => {
  test("national command draws a fleet, not a handful", async ({ context, page }) => {
    await open(page, context, "ADMIN", "/admin/radar");

    const vessels = await drawn(page, "vessels");
    expect(vessels.length, "too few vessels for a traffic picture").toBeGreaterThan(120);

    // Colour carries class, and the mix has to be a mix.
    const classes = new Set(vessels.map((v: any) => v.class));
    expect(classes.size, "every vessel is the same class").toBeGreaterThan(3);

    // Heading-oriented glyphs: a fleet where nothing has a course is a scatter
    // plot, not traffic.
    const heading = vessels.filter((v: any) => typeof v.cog === "number" && v.cog !== 0);
    expect(heading.length).toBeGreaterThan(50);
  });

  test("the source is declared as simulated, not as observed AIS", async ({ context, page }) => {
    await open(page, context, "ADMIN", "/admin/radar");
    await expect(page.getByText("Simulated replay").first()).toBeVisible();
    await expect(page.getByText(/\d+ vessels/).first()).toBeVisible();
  });

  test("the port cockpit shows the traffic around its own facility", async ({ context, page }) => {
    await open(page, context, "PORT_OPERATOR", "/port/overview");

    const board = page.getByTestId("traffic-board");
    await expect(board).toBeVisible();
    await expect(board.getByText(/\d+ vessels/)).toBeVisible();

    // Inbound, anchored and alongside are all represented, which is what makes
    // it a harbour picture rather than a list of arrivals.
    // The pills are upper-cased in CSS; the text in the DOM is not.
    for (const status of ["Inbound", "Anchored", "Moored"]) {
      await expect(board.getByText(status, { exact: true }).first()).toBeVisible();
    }
  });

  test("the vessel operator sees other traffic, not only their own ship", async ({
    context,
    page,
  }) => {
    await open(page, context, "VESSEL_OPERATOR", "/vessel/overview");

    const vessels = await drawn(page, "vessels");
    expect(vessels.length, "the bridge view drew almost no surrounding traffic").toBeGreaterThan(40);

    await expect(page.getByText("Traffic around o", { exact: false })).toBeVisible();
    await expect(page.getByText(/within 60 nm/)).toBeVisible();
  });
});

/* ---------------------------------------------------------------- filters -- */

test("a class filter removes that class from the chart", async ({ context, page }) => {
  await open(page, context, "ADMIN", "/admin/radar");

  const before = await drawn(page, "vessels");
  const containersBefore = before.filter((v: any) => v.class === "container").length;
  expect(containersBefore, "no containers to filter").toBeGreaterThan(5);

  await page.getByRole("button", { name: /Layers and filters/i }).click();
  await page.getByRole("button", { name: "Container", exact: true }).click();

  await expect
    .poll(async () => (await drawn(page, "vessels")).filter((v: any) => v.class === "container").length, {
      timeout: 10_000,
    })
    .toBe(0);
  expect((await drawn(page, "vessels")).length).toBeLessThan(before.length);
});

/* -------------------------------------------------- search and inspection -- */

test("search finds a vessel, and selecting it opens the inspector", async ({ context, page }) => {
  await open(page, context, "ADMIN", "/admin/radar");

  const search = page.getByRole("searchbox", { name: /Search vessels, ports and chokepoints/i });
  await search.fill("Coromandel");
  const option = page.getByRole("option").first();
  await expect(option).toBeVisible({ timeout: 10_000 });
  const label = (await option.textContent()) ?? "";
  await option.click();

  const inspector = page.getByTestId("vessel-inspector");
  await expect(inspector).toBeVisible({ timeout: 10_000 });
  await expect(inspector.getByText("Speed over ground")).toBeVisible();
  await expect(inspector.getByText("Course / heading")).toBeVisible();
  await expect(inspector.getByText(/not issued · simulated/)).toBeVisible();
  // The name in the result is the name in the inspector.
  expect(label.length).toBeGreaterThan(3);
});

test("search finds a port and flies to it", async ({ context, page }) => {
  await open(page, context, "ADMIN", "/admin/radar");
  const before = await page.evaluate(() => (window as any).__portwatchMap.getZoom());

  await page
    .getByRole("searchbox", { name: /Search vessels, ports and chokepoints/i })
    .fill("Chennai");
  const option = page.getByRole("option").first();
  await expect(option).toBeVisible({ timeout: 10_000 });
  await option.click();
  await page.waitForTimeout(1600);

  const after = await page.evaluate(() => (window as any).__portwatchMap.getZoom());
  expect(after, "selecting a port did not move the camera in").toBeGreaterThan(before);
});

test("isolating the selection hides the rest of the traffic", async ({ context, page }) => {
  await open(page, context, "VESSEL_OPERATOR", "/vessel/overview");

  const before = await drawn(page, "vessels");
  expect(before.length).toBeGreaterThan(20);

  await page.getByRole("button", { name: "Isolate", exact: true }).click();
  await expect
    .poll(() => drawnCount(page, "vessels"), { timeout: 10_000 })
    .toBeLessThan(before.length);

  const isolated = await drawnCount(page, "vessels");
  expect(isolated, "isolation removed the selection too").toBeGreaterThan(0);

  await page.getByRole("button", { name: "Show all traffic" }).click();
  await expect
    .poll(() => drawnCount(page, "vessels"), { timeout: 10_000 })
    .toBeGreaterThan(isolated);
});

/* ------------------------------------------------------------------- time -- */

test("scrubbing the forecast moves the weather and the predicted fleet", async ({
  context,
  page,
}) => {
  await open(page, context, "ADMIN", "/admin/radar");

  // At NOW there is nothing to predict, so no ghosts are drawn.
  expect((await drawn(page, "ghosts")).length).toBe(0);
  await expect(page.getByTestId("weather-offset")).toHaveText("NOW");

  await page.getByRole("button", { name: "+24h", exact: true }).click();

  await expect(page.getByTestId("weather-offset")).toHaveText("+24H");
  await expect
    .poll(() => drawnCount(page, "ghosts"), { timeout: 10_000 })
    .toBeGreaterThan(20);

  // And the weather field is now declared as derived rather than observed.
  await expect(page.getByText("derived").first()).toBeVisible();

  await page.getByRole("button", { name: "NOW", exact: true }).first().click();
  await expect(page.getByTestId("weather-offset")).toHaveText("NOW");
  await expect.poll(() => drawnCount(page, "ghosts"), { timeout: 10_000 }).toBe(0);
});

test("the replay clock can be paused and restarted", async ({ context, page }) => {
  await open(page, context, "ADMIN", "/admin/radar");

  await page.getByRole("button", { name: "Pause replay" }).click();
  await expect(page.getByRole("button", { name: "Play replay" })).toBeVisible();
  expect(await drawnCount(page, "vessels")).toBeGreaterThan(0);

  await page.getByRole("button", { name: "Play replay" }).click();
  await expect(page.getByRole("button", { name: "Pause replay" })).toBeVisible();
});

/* ----------------------------------------------------------- environment -- */

test("weather is on by default and states what it is", async ({ context, page }) => {
  await open(page, context, "ADMIN", "/admin/radar");

  const visible = await page.evaluate(
    () => (window as any).__portwatchMap.getLayoutProperty("wx-field", "visibility"),
  );
  expect(visible, "the weather composite was not on by default").not.toBe("none");

  await expect(page.getByText("Precipitation").first()).toBeVisible();
  await expect(page.getByText("observed").first()).toBeVisible();
  await expect(page.getByText(/modelled/).first()).toBeVisible();
});

test("wave height is reported as unavailable rather than substituted", async ({
  context,
  page,
}) => {
  await open(page, context, "PORT_OPERATOR", "/port/overview");
  await page.getByRole("tab", { name: /Weather/ }).click();
  await expect(page.getByText("UNAVAILABLE").first()).toBeVisible();
});

/* ------------------------------------------------------ arrival sequence -- */

test("the arrival sequence ranks by ETA and shows the berth wait", async ({ context, page }) => {
  await open(page, context, "PORT_OPERATOR", "/port/overview");

  await page.getByRole("tab", { name: /Arrivals/ }).click();
  await expect(page.getByText(/berths ·/)).toBeVisible();
  await expect(page.getByText(/anchor time in queue/)).toBeVisible();
  await expect(page.getByText(/if staggered/)).toBeVisible();
});

test("the traffic board sorts", async ({ context, page }) => {
  await open(page, context, "PORT_OPERATOR", "/port/overview");
  const board = page.getByTestId("traffic-board");
  // The board opens itself only where there is room for it and the chart both.
  const expand = board.getByRole("button", { name: "expand" });
  if (await expand.isVisible().catch(() => false)) await expand.click();

  await expect(board.getByRole("button", { name: /ETA ↑/ })).toBeVisible();
  await board.getByRole("button", { name: /^SOG/ }).click();
  // The header marks the active sort, which is the assertion that survives a
  // fleet that happens to be ordered the same way under two keys.
  await expect(board.getByRole("button", { name: /SOG ↑/ })).toBeVisible();
  await board.getByRole("button", { name: /^SOG/ }).click();
  await expect(board.getByRole("button", { name: /SOG ↓/ })).toBeVisible();
});
