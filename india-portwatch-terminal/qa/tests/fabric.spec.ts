/**
 * The live world fabric: traffic that says what it is, and a sea that says
 * when it is for.
 *
 * Every state here is a recording of the real API in that state, produced by
 * pushing synthetic AIS messages through the real ingest path
 * (qa/record-ais-states.py). The suite moves the API between recordings and
 * asserts what the terminal *says* -- because the claim under test is not
 * that the chart draws vessels, it is that the chart never calls them LIVE
 * unless the server did, and never calls them SIMULATED once they were
 * observed.
 */

import type { Page } from "@playwright/test";

import {
  expect,
  refocus,
  seedSession,
  settle,
  test,
  withFixture,
} from "../harness";

const GLOBAL_EYE = "/admin/global-eye";

// Every case here loads the world, then moves it between recorded states and
// waits for the terminal to notice; that is two or three round trips more
// than the other specs, on a chart animating eight hundred vessels beneath.
test.describe.configure({ timeout: 120_000 });

async function mapReady(page: Page): Promise<void> {
  await page.waitForFunction(
    () => {
      const sources = (window as any).__portwatchSources;
      return Boolean(
        (window as any).__portwatchMap &&
        (sources?.vessels?.features?.length ?? 0) > 0,
      );
    },
    undefined,
    { timeout: 45_000 },
  );
}

async function featureCount(page: Page, source: string): Promise<number> {
  return page.evaluate(
    (key) =>
      ((window as any).__portwatchSources?.[key]?.features?.length ??
        0) as number,
    source,
  );
}

/**
 * Click an observed mark where the map drew it.
 *
 * The mark is a five-pixel ring on a GL canvas with no DOM of its own, so the
 * click is delivered to the canvas at the projected point as the mouse
 * events MapLibre's handler reads. What is being tested is what the click
 * *does* -- the map's own hit-test and the inspector it opens -- not the
 * pointer's journey to a pixel, which under two workers on a software
 * renderer occasionally arrives before the ring has been drawn.
 */
async function clickMark(page: Page, mmsi: string): Promise<string[]> {
  return page.evaluate((id) => {
    const map = (window as any).__portwatchMap;
    const feature = (window as any).__portwatchSources.observed.features.find(
      (f: any) => f.properties.kind === "mark" && f.properties.id === id,
    );
    const point = map.project(feature.geometry.coordinates);
    const canvas = map.getCanvas();
    const rect = canvas.getBoundingClientRect();
    const hits = map
      .queryRenderedFeatures([point.x, point.y], { layers: ["observed-mark"] })
      .map((hit: any) => hit.properties.id as string);
    for (const type of ["mousedown", "mouseup", "click"]) {
      canvas.dispatchEvent(
        new MouseEvent(type, {
          bubbles: true,
          cancelable: true,
          clientX: rect.left + point.x,
          clientY: rect.top + point.y,
          button: 0,
        }),
      );
    }
    return hits;
  }, mmsi);
}

/**
 * Move the API to a recorded traffic state and wait until the terminal has
 * read it.
 *
 * The first health fetch may still be in flight when the fixture is swapped,
 * and a refetch triggered during a fetch is coalesced into it. So the strip
 * is waited for first, and then the refocus is repeated until the new mode
 * lands -- a state change here means "the terminal noticed", not "the
 * server changed".
 */
async function moveTo(
  context: Parameters<typeof withFixture>[0],
  page: Page,
  state: "live" | "stale",
) {
  await expect(page.getByTestId("status-traffic")).toHaveAttribute(
    "data-mode",
    /./,
    {
      timeout: 30_000,
    },
  );
  await withFixture(context, "/fabric/health", `fabric_health_${state}.json`);
  await withFixture(
    context,
    "/world/ais/tracks",
    `world_ais_tracks_${state}.json`,
  );
  const wanted = state === "live" ? "LIVE_AIS" : "AIS_STALE";
  await expect
    .poll(
      async () => {
        await refocus(page);
        return page.getByTestId("status-traffic").getAttribute("data-mode");
      },
      { timeout: 30_000, intervals: [1_000, 2_000, 2_000, 3_000] },
    )
    .toBe(wanted);
}

test("the status strip names the licence mode and the traffic truth, and says when the mode was defaulted", async ({
  context,
  page,
}) => {
  await seedSession(context, "NATIONAL_ADMIN");
  await page.goto(GLOBAL_EYE);
  const mode = page.getByTestId("status-mode");
  await expect(mode).toHaveAttribute(
    "data-mode",
    /^(DEMO|RESEARCH|COMMERCIAL|GOVERNMENT)$/,
    { timeout: 30_000 },
  );
  await expect(mode).toHaveAttribute("data-stated", /^(true|false)$/);
  const stated = await mode.getAttribute("data-stated");
  const text = (await mode.innerText()).toLowerCase();
  if (stated === "false") expect(text).toContain("default");
  else expect(text).not.toContain("default");
  await expect(page.getByTestId("status-traffic")).toHaveAttribute(
    "data-mode",
    /^(LIVE_AIS|AIS_STALE|SIMULATED_TRAFFIC|UNAVAILABLE)$/,
  );
  const traffic = (
    await page.getByTestId("status-traffic").innerText()
  ).toLowerCase();
  expect(traffic).toMatch(
    /live ais|ais stale|simulated replay|no traffic feed/,
  );
});

async function goLive(context: Parameters<typeof withFixture>[0], page: Page) {
  await moveTo(context, page, "live");
}

/* ------------------------------------------------------------- the strip -- */

test.describe("traffic source", () => {
  test("a replay deployment is labelled simulated, in the strip and in the inspector", async ({
    context,
    page,
    recorder,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto(GLOBAL_EYE);
    await settle(page);
    await mapReady(page);

    const strip = page.getByTestId("status-traffic");
    await expect(strip).toHaveAttribute("data-mode", "SIMULATED_TRAFFIC");
    await expect(strip).toContainText("Simulated replay");
    await expect(page.getByTestId("signal-health")).toHaveAttribute(
      "data-traffic",
      "SIMULATED_TRAFFIC",
    );
    // Nothing observed is drawn on a replay deployment.
    expect(await featureCount(page, "observed")).toBe(0);
    expect(recorder.pageErrors).toEqual([]);
  });

  test("the chart goes SIMULATED -> LIVE only when the server says observations arrived", async ({
    context,
    page,
    recorder,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto(GLOBAL_EYE);
    await settle(page);
    await mapReady(page);
    await expect(page.getByTestId("status-traffic")).toHaveAttribute(
      "data-mode",
      "SIMULATED_TRAFFIC",
    );

    await goLive(context, page);

    const strip = page.getByTestId("status-traffic");
    await expect(strip).toHaveAttribute("data-mode", "LIVE_AIS", {
      timeout: 15_000,
    });
    await expect(strip).toContainText("Live AIS");
    await expect(strip).toContainText("4 observed");
    // The replay fleet is still drawn, and still called simulated.
    await expect(strip).toContainText("simulated");

    // Observed marks and their tracks reach the GL source.
    await page.waitForFunction(
      () =>
        ((window as any).__portwatchSources?.observed?.features?.length ?? 0) >
        0,
      undefined,
      { timeout: 15_000 },
    );
    const marks = await page.evaluate(() =>
      (window as any).__portwatchSources.observed.features
        .filter((f: any) => f.properties.kind === "mark")
        .map((f: any) => f.properties),
    );
    expect(marks).toHaveLength(4);
    expect(marks.every((m: any) => m.freshness === "LIVE")).toBe(true);
    expect(marks.every((m: any) => m.source === "OBSERVED_AIS")).toBe(true);
    // A position report names nobody: two of the four carry no name.
    expect(marks.filter((m: any) => !m.name)).toHaveLength(2);
    expect(recorder.pageErrors).toEqual([]);
  });

  test("the chart goes LIVE -> STALE, never back to simulated", async ({
    context,
    page,
    recorder,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto(GLOBAL_EYE);
    await settle(page);
    await mapReady(page);
    await goLive(context, page);
    const strip = page.getByTestId("status-traffic");
    await expect(strip).toHaveAttribute("data-mode", "LIVE_AIS", {
      timeout: 15_000,
    });

    await moveTo(context, page, "stale");

    await expect(strip).toHaveAttribute("data-mode", "AIS_STALE", {
      timeout: 15_000,
    });
    await expect(strip).toContainText("AIS stale");
    await expect(strip).not.toContainText("Simulated replay");

    // The last known positions stay on the chart, marked stale.
    await page.waitForFunction(
      () =>
        (window as any).__portwatchSources?.observed?.features?.some(
          (f: any) =>
            f.properties.kind === "mark" && f.properties.freshness === "STALE",
        ),
      undefined,
      { timeout: 15_000 },
    );
    const live = await page.evaluate(
      () =>
        (window as any).__portwatchSources.observed.features.filter(
          (f: any) =>
            f.properties.kind === "mark" && f.properties.freshness === "LIVE",
        ).length,
    );
    expect(live).toBe(0);

    // And the health panel says so in words, with the last observation dated.
    await page.getByTestId("signal-health").click();
    const traffic = page.getByTestId("traffic-mode");
    await expect(traffic).toHaveAttribute("data-mode", "AIS_STALE");
    await expect(traffic).toContainText("last known, not current");
    await expect(
      page.getByTestId("traffic-last-observation"),
    ).not.toContainText("—");
    expect(recorder.pageErrors).toEqual([]);
  });
});

/* --------------------------------------------------------- the inspector -- */

test.describe("vessel provenance", () => {
  test("an observed hull opens an inspector that says OBSERVED AIS and states only what was reported", async ({
    context,
    page,
    recorder,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto(GLOBAL_EYE);
    await settle(page);
    await mapReady(page);
    await goLive(context, page);
    await page.waitForFunction(
      () =>
        ((window as any).__portwatchSources?.observed?.features?.length ?? 0) >
        0,
      undefined,
      { timeout: 15_000 },
    );

    // Bring the hull into view, then click it where the map drew it.
    await page.evaluate(() => {
      (window as any).__portwatchMap.jumpTo({ center: [70.9, 18.6], zoom: 6 });
    });
    await page.waitForTimeout(600);
    // Wait for the ring to be drawn, then click it through the map's own
    // hit-test.
    await expect
      .poll(() => clickMark(page, "419001103"), { timeout: 15_000 })
      .toContain("419001103");

    const inspector = page.getByTestId("observed-inspector");
    await expect(inspector).toBeVisible({ timeout: 10_000 });
    const source = inspector.getByTestId("vessel-source");
    await expect(source).toHaveAttribute("data-source", "OBSERVED_AIS");
    await expect(source).toHaveAttribute("data-freshness", "LIVE");
    await expect(source).toContainText("OBSERVED AIS");
    // This transponder sent only position reports: name and IMO are not stated,
    // and the title is the MMSI rather than an invented name.
    await expect(inspector).toContainText("MMSI 419001103");
    await expect(inspector).toContainText("not stated");
    // Heading 511 is "not available", not a bearing.
    await expect(inspector).toContainText("not available");
    expect(recorder.pageErrors).toEqual([]);
  });

  test("a replay hull's inspector says SIMULATED TRAFFIC", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/radar");
    await settle(page);
    await mapReady(page);

    const search = page.getByRole("searchbox", {
      name: /Search vessels, ports and chokepoints/i,
    });
    await search.fill("Coromandel");
    const option = page.getByRole("option").first();
    await expect(option).toBeVisible({ timeout: 10_000 });
    await option.click();
    const inspector = page.getByTestId("vessel-inspector");
    await expect(inspector).toBeVisible();
    const source = inspector.getByTestId("vessel-source");
    await expect(source).toHaveAttribute("data-source", "SIMULATED_TRAFFIC");
    await expect(source).toContainText("SIMULATED TRAFFIC");
  });
});

/* ---------------------------------------------------------- trust surface -- */

test.describe("signal health", () => {
  test("every row answers mode, status, last observation, age, coverage, product and licence state", async ({
    context,
    page,
    recorder,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto(GLOBAL_EYE);
    await settle(page);

    await page.getByTestId("signal-health").click();
    const panel = page.getByTestId("signal-health-panel");
    await expect(panel).toBeVisible();

    // The AIS product on a replay deployment: REQUIRES_REVIEW, not "allowed"
    // and not "non-commercial" -- the terms were looked for and not found.
    const ais = panel.locator(
      '[data-testid="signal-row"][data-capability="ais"]',
    );
    await expect(ais).toHaveAttribute("data-product", "aisstream-websocket");
    await expect(ais).toHaveAttribute("data-commercial", "REQUIRES_REVIEW");
    await ais.locator("button").first().click();
    const evidence = ais.getByTestId("signal-evidence");
    for (const label of [
      "Mode",
      "Status",
      "Last observation",
      "Age",
      "Coverage",
      "Product",
      "Licence state",
    ]) {
      await expect(evidence).toContainText(label);
    }
    await expect(evidence.getByTestId("licence-commercial")).toHaveAttribute(
      "data-state",
      "REQUIRES_REVIEW",
    );
    await expect(evidence.getByTestId("licence-commercial")).toContainText(
      "requires review",
    );
    await expect(evidence).toContainText("no published terms found");

    // The marine product: the free tier, PROHIBITED commercially, with terms cited.
    const marine = panel.locator(
      '[data-testid="signal-row"][data-capability="marine"]',
    );
    await expect(marine).toHaveAttribute("data-product", "open-meteo-free");
    await expect(marine).toHaveAttribute("data-commercial", "PROHIBITED");
    await marine.locator("button").first().click();
    await expect(marine.getByTestId("licence-commercial")).toContainText(
      "prohibited",
    );
    await expect(marine.getByTestId("signal-evidence")).toContainText(
      "terms reviewed",
    );
    expect(recorder.pageErrors).toEqual([]);
  });

  test("the traffic block reads the socket, not the key", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto(GLOBAL_EYE);
    await settle(page);
    await goLive(context, page);
    await expect(page.getByTestId("signal-health")).toHaveAttribute(
      "data-traffic",
      "LIVE_AIS",
      { timeout: 15_000 },
    );
    await page.getByTestId("signal-health").click();
    const traffic = page.getByTestId("traffic-mode");
    await expect(traffic).toHaveAttribute("data-mode", "LIVE_AIS");
    await expect(traffic).toHaveAttribute("data-socket", "LIVE");
    await expect(traffic).toContainText("valid observations are arriving");
    await expect(page.getByTestId("traffic-vessels")).toContainText("4 live");
  });
});

/* ------------------------------------------------------------------ sea -- */

test.describe("the sea", () => {
  test("the WEATHER lens draws forecast cells with their product, age and validity", async ({
    context,
    page,
    recorder,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto(GLOBAL_EYE);
    await settle(page);
    await mapReady(page);

    // Off until the lens asks for it.
    expect(await featureCount(page, "seastate")).toBe(0);
    await page
      .locator('[data-testid="lens-option"][data-lens="WEATHER"]')
      .click();

    await page.waitForFunction(
      () =>
        ((window as any).__portwatchSources?.seastate?.features?.length ?? 0) >
        0,
      undefined,
      { timeout: 15_000 },
    );
    const kinds = await page.evaluate(() =>
      (window as any).__portwatchSources.seastate.features.map(
        (f: any) => f.properties.kind,
      ),
    );
    expect(kinds.filter((k: string) => k === "cell")).toHaveLength(3);
    expect(kinds).toContain("current");
    expect(
      await page.evaluate(() =>
        (window as any).__portwatchMap.getLayoutProperty(
          "seastate-wave",
          "visibility",
        ),
      ),
    ).toBe("visible");

    const legend = page.getByTestId("seastate-legend");
    await expect(legend).toBeVisible();
    await expect(legend).toHaveAttribute("data-cells", "3");
    await expect(legend).toHaveAttribute("data-status", "AVAILABLE");
    const attribution = page.getByTestId("seastate-attribution");
    await expect(attribution).toContainText("open-meteo-free");
    await expect(attribution).toContainText("Open-Meteo");
    await expect(attribution).toContainText("valid");

    // Leaving the lens takes the sea with it.
    await page
      .locator('[data-testid="lens-option"][data-lens="OPERATIONS"]')
      .click();
    await expect
      .poll(() =>
        page.evaluate(() =>
          (window as any).__portwatchMap.getLayoutProperty(
            "seastate-wave",
            "visibility",
          ),
        ),
      )
      .toBe("none");
    expect(recorder.pageErrors).toEqual([]);
  });
});
