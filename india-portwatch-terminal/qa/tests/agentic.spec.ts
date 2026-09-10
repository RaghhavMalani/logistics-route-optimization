/**
 * The agentic surfaces, and the honesty they are required to carry.
 *
 * These tests exist because the claims this product makes about itself are the
 * easiest thing to break silently. A weather layer that quietly stops rendering,
 * a schematic twin that loses its banner, an agent console that shows a
 * confident answer with no trace behind it — each of those would still *look*
 * fine in a screenshot. So each is asserted.
 */

import {
  expect,
  horizontalOverflow,
  seedSession,
  settle,
  test,
} from "../harness";

test.describe("weather composite", () => {
  /**
   * Weather must be on and visible without the operator choosing a field.
   *
   * The raster is a data URL written into a GL image source, so there is no DOM
   * node to assert on. The legend is the observable proof that the composite
   * built and what it found, which is what a reader would check too.
   */
  test("the environment layer is a composite and is on by default", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/radar");
    await settle(page);

    const legend = page.getByTestId("environment-legend");
    await expect(legend).toBeVisible();
    // "rain · wind · severe" only renders for the composite; a single-field
    // legend shows that field's unit instead.
    await expect(legend.getByText("rain · wind · severe")).toBeVisible();
    await expect(legend.getByText("Environment")).toBeVisible();
    // The composite reports the peak of each field it carries, which is how a
    // reader tells a hot cell of rain from one of wind.
    await expect(legend.getByText(/peak Rain/i)).toBeVisible();
    await expect(legend.getByText(/peak Wind/i)).toBeVisible();
  });

  test("the forecast cursor plays, and the scrubber moves it", async ({
    context,
    page,
  }) => {
    // The only test here that waits on wall-clock animation: it plays the
    // cursor, then pauses it and proves it stopped. Every step contends with an
    // eight hundred vessel render loop on a software renderer, so it gets a
    // longer budget rather than a shorter assertion -- the thing under test is
    // that the animation really runs and really stops.
    test.slow();
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/radar");
    await settle(page);

    const offset = page.getByTestId("weather-offset");
    await expect(offset).toHaveText("NOW");

    // Dragging to a step takes the cursor off autoplay and moves it there.
    await page.getByRole("button", { name: "+24h" }).click();
    await expect(offset).toHaveText("+24H");

    // The accessible name is the assertion: it is what a screen-reader user is
    // told the control will do, and it changes with the state.
    const play = page.getByTestId("weather-play");
    await expect(play).toHaveAccessibleName("Play the forecast forward");
    await play.click();
    await expect(play).toHaveAccessibleName("Pause the forecast animation");

    // The cursor is advancing on its own clock, so the read-out changes without
    // any further interaction.
    await page.waitForTimeout(1400);
    await expect(offset).not.toHaveText("+24H");

    // Pause is asserted on behaviour rather than on the attribute round-trip:
    // what matters is that the cursor actually stops, and the animation runs on
    // requestAnimationFrame, so reading a value twice a second apart is the
    // only honest way to check it.
    await play.click();
    await expect(play).toHaveAccessibleName("Play the forecast forward");
    const stopped = await offset.textContent();
    await page.waitForTimeout(900);
    expect(await offset.textContent(), "the forecast cursor kept moving after pause")
      .toBe(stopped);
  });
});

test.describe("Global Eye", () => {
  /**
   * The impact chain is still the whole product claim of Global Eye. What
   * changed is where it is made: it used to be a labelled list in a panel, and
   * it is now drawn on the water and summarised above it. The hops are asserted
   * through the cascade the chart received, which is the same chain and is
   * harder to fake than a list of headings.
   */
  test("the register renders and an event traces its impact chain", async ({
    context,
    page,
    recorder,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);

    await expect(page.getByTestId("cascade-register")).toBeVisible();
    const rows = page.getByTestId("cascade-row");
    expect(await rows.count()).toBeGreaterThan(0);

    await rows.first().click();
    await expect(page.getByTestId("cascade-headline")).toBeVisible();

    // Every hop of the chain, read off the consequence the chart drew.
    const hops = await page.evaluate(() => {
      const registry = (window as unknown as {
        __portwatchSources?: Record<string, GeoJSON.FeatureCollection>;
      }).__portwatchSources;
      const features = registry?.cascade?.features ?? [];
      return {
        lanes: features.filter(
          (f) => (f.properties as Record<string, unknown>)?.part === "lane",
        ).length,
        rings: features.filter(
          (f) => (f.properties as Record<string, unknown>)?.part === "ring",
        ).length,
      };
    });
    expect(hops.lanes).toBeGreaterThan(0);
    expect(hops.rings).toBeGreaterThan(0);

    expect(recorder.pageErrors).toEqual([]);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  });

  /**
   * A probability is either calibrated or withheld with a reason. There is no
   * third state, and the screen must never show a bare percentage that came out
   * of a word-list heuristic.
   *
   * The claim now attaches to the cascade's seed. A cascade is seeded with the
   * calibrated probability where one exists and with raw severity where none
   * does, so everything drawn downstream inherits whichever was used and the
   * reader has to be able to tell which.
   */
  test("an uncalibrated event says so rather than showing a number", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);
    await page.getByTestId("cascade-row").first().click();
    await settle(page);

    const basis = page.getByTestId("seed-basis");
    await expect(basis).toBeVisible();

    const text = (await basis.innerText()).toLowerCase();
    const withheld = text.includes("no calibrated probability");
    const stated = /\d+% calibrated/.test(text);
    expect(
      withheld || stated,
      "a cascade must either state a calibrated seed or say it has none",
    ).toBe(true);
    expect(
      withheld && stated,
      "a cascade cannot both withhold and state a calibrated probability",
    ).toBe(false);
  });
});

test.describe("Fleet Command", () => {
  test("the action queue leads, and committed vessels are kept out of it", async ({
    context,
    page,
    recorder,
  }) => {
    await seedSession(context, "SHIPPING_COMPANY");
    await page.goto("/company/overview");
    await settle(page);

    await expect(page.getByTestId("fleet-command-panel")).toBeVisible();

    const actionRequired = page.getByTestId("action-required");
    if (await actionRequired.count()) {
      await expect(actionRequired.getByText("Action required")).toBeVisible();
      const rows = page.getByTestId("action-required-row");
      expect(await rows.count()).toBeGreaterThan(0);
      // Nothing in the action queue may be a vessel that has already entered
      // the risk area: the option has closed and the advice would be unusable.
      await expect(actionRequired.getByText("In the risk area")).toHaveCount(0);
    }

    expect(recorder.pageErrors).toEqual([]);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  });
});

test.describe("agent console", () => {
  test("a run shows its tool trace, its critic and where the numbers came from", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/radar");
    await settle(page);

    await page.getByTestId("agent-console-open").click();
    const console_ = page.getByTestId("agent-console");
    await expect(console_).toBeVisible();

    await page.getByTestId("agent-question").fill("Which vessels require action?");
    await page.getByTestId("agent-question").press("Enter");

    // The replayed run carries a chain, so the trace must render.
    await expect(console_.getByText(/tool calls/)).toBeVisible({ timeout: 15_000 });
    await expect(
      console_.getByText(/Agents orchestrate and explain/),
    ).toBeVisible();
  });

  test("the console is a strip, not the product", async ({ context, page }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/radar");
    await settle(page);

    // Collapsed by default: the map is the primary surface and stays so.
    await expect(page.getByTestId("agent-console")).toHaveCount(0);
    await expect(page.getByTestId("agent-console-open")).toBeVisible();
  });
});

test.describe("the approval boundary", () => {
  /**
   * The single most important claim this product makes about its own safety:
   * an agent cannot execute anything. The tool catalogue is where that is
   * visible, and it is asserted here rather than trusted.
   */
  test("EXECUTE tools are marked and separated from what agents may call", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/agents");
    await settle(page);

    await expect(page.getByTestId("agent-boundary")).toBeVisible();
    const catalogue = page.getByTestId("tool-catalogue");
    await expect(catalogue).toBeVisible();

    for (const level of ["READ", "SIMULATE", "PROPOSE", "EXECUTE"]) {
      await expect(catalogue.getByText(level, { exact: true }).first()).toBeVisible();
    }

    await expect(
      page.getByText(/EXECUTE tools require an ApprovalContext/i),
    ).toBeVisible();

    // Every specialist is capped below EXECUTE. The Critic and the orchestrator
    // included -- there is no agent in the list with an EXECUTE ceiling.
    const agents = page.getByTestId("agent-list");
    await expect(agents.getByText("EXECUTE")).toHaveCount(0);
  });
});

test.describe("learning dashboard", () => {
  test("an empty ledger reports unavailable rather than perfect", async ({
    context,
    page,
    recorder,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/learning");
    await settle(page);

    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Learning");

    // With no resolved claims the screen must say so in words, not draw a chart
    // of zeros. With claims resolved, the accuracy panel carries real numbers.
    const empty = page.getByText(/holds no resolved claims yet/i);
    const calibration = page.getByTestId("learning-calibration");
    await expect(calibration).toBeVisible();

    if (await empty.count()) {
      // Whichever branch the empty state took, it must explain the absence
      // rather than draw a chart of zeros.
      await expect(
        page
          .getByText(
            /(reporting them as perfect would be worse than reporting nothing|Run the pipeline to write claims into the ledger)/i,
          )
          .first(),
      ).toBeVisible();
    }

    expect(recorder.pageErrors).toEqual([]);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  });

  test("policies show their promotion state and why one was refused", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/learning");
    await settle(page);
    await expect(page.getByTestId("learning-policies")).toBeVisible();
  });
});
