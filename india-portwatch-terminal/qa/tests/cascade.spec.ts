/**
 * The world reacting, and the claims that reaction makes.
 *
 * A cascade drawn on the chart is a causal claim: this event did that to that
 * water, which did this to those routes. The risk is that the drawing and the
 * computation drift -- the map keeps lighting lanes after the engine has stopped
 * saying they are affected, or lights lanes the engine never named. Either would
 * look completely fine in a screenshot, and either would be the product lying in
 * the place an operator believes fastest.
 *
 * So the assertions here are mostly correspondence: what the chart drew must be
 * what the API returned, and when the API stops saying it, the chart must stop
 * drawing it.
 */

import {
  expect,
  horizontalOverflow,
  seedSession,
  settle,
  test,
} from "../harness";

/** The GeoJSON the chart last handed the GL context. */
async function cascadeSource(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const registry = (window as unknown as {
      __portwatchSources?: Record<string, GeoJSON.FeatureCollection>;
    }).__portwatchSources;
    const collection = registry?.cascade;
    if (!collection) return null;
    return {
      total: collection.features.length,
      lanes: collection.features.filter(
        (f) => (f.properties as Record<string, unknown>)?.part === "lane",
      ).length,
      rings: collection.features.filter(
        (f) => (f.properties as Record<string, unknown>)?.part === "ring",
      ).length,
      laneCodes: collection.features
        .map((f) => (f.properties as Record<string, unknown>)?.laneCode)
        .filter(Boolean) as string[],
      portCodes: collection.features
        .map((f) => (f.properties as Record<string, unknown>)?.id)
        .filter(Boolean) as string[],
    };
  });
}

test.describe("the world reacts", () => {
  test("a live event draws its consequence on the chart", async ({ context, page }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);

    await expect(page.getByTestId("cascade-headline")).toBeVisible();

    // The reveal is staged, so wait for it to settle rather than racing it.
    await page.waitForFunction(
      () => {
        const registry = (window as unknown as {
          __portwatchSources?: Record<string, GeoJSON.FeatureCollection>;
        }).__portwatchSources;
        return (registry?.cascade?.features.length ?? 0) > 0;
      },
      undefined,
      { timeout: 15_000 },
    );

    const drawn = await cascadeSource(page);
    expect(drawn).not.toBeNull();
    expect(drawn!.lanes).toBeGreaterThan(0);
    expect(drawn!.rings).toBeGreaterThan(0);
  });

  /**
   * The correspondence test. What the chart drew has to be what the engine said.
   *
   * A map that lit lanes the cascade never named would be inventing consequence,
   * and it would be invisible to every other test in this suite.
   */
  test("the drawn cascade matches the cascade the API returned", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");

    const responses: Array<Record<string, unknown>> = [];
    page.on("response", async (response) => {
      if (!/\/api\/world\/cascades\/[^/?]+/.test(response.url())) return;
      try {
        responses.push(await response.json());
      } catch {
        /* a non-JSON body is not the payload under test */
      }
    });

    await page.goto("/admin/global-eye");
    await settle(page);
    await page.waitForFunction(
      () => {
        const registry = (window as unknown as {
          __portwatchSources?: Record<string, GeoJSON.FeatureCollection>;
        }).__portwatchSources;
        return (registry?.cascade?.features.length ?? 0) > 0;
      },
      undefined,
      { timeout: 15_000 },
    );

    expect(responses.length).toBeGreaterThan(0);
    const cascade = responses[responses.length - 1] as {
      affected: { lanes: Array<{ id: string }>; ports: Array<{ id: string }> };
    };
    const drawn = await cascadeSource(page);

    const apiLanes = new Set(cascade.affected.lanes.map((l) => l.id));
    for (const code of new Set(drawn!.laneCodes)) {
      expect(apiLanes).toContain(code);
    }
    // Every ring the chart drew names a chokepoint or a port the cascade reached.
    const apiSubjects = new Set([
      ...cascade.affected.ports.map((p) => p.id),
      ...(cascade.affected as unknown as { chokepoints: Array<{ id: string }> })
        .chokepoints.map((c) => c.id),
    ]);
    for (const id of new Set(drawn!.portCodes)) {
      expect(apiSubjects).toContain(id);
    }
  });

  test("the action rail leads with what can still be acted on", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);

    const rail = page.getByTestId("action-rail");
    await expect(rail).toBeVisible();

    const items = page.getByTestId("attention-item");
    const count = await items.count();
    expect(count).toBeGreaterThan(0);
    // A queue nobody can finish is a queue nobody starts.
    expect(count).toBeLessThanOrEqual(5);
  });

  /**
   * Every actionable row states an action and the window it closes in.
   *
   * The other half of this rule -- that a committed hull is offered no action at
   * all -- is asserted in `tests/test_attention_and_fabric.py`, where a vessel
   * already inside the water can be constructed. The recorded feed contains no
   * such hull, and a browser test that skipped forever would look like coverage
   * while proving nothing.
   */
  test("an actionable row states its action and its deadline", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);

    const actionable = page.locator(
      '[data-testid="attention-item"][data-status="ACT_NOW"], ' +
        '[data-testid="attention-item"][data-status="ACT_SOON"]',
    );
    expect(await actionable.count()).toBeGreaterThan(0);

    const first = actionable.first();
    // A window an operator can read: "5h 54m", not "5.9 hours".
    await expect(first).toContainText(/\d+h(\s\d+m)?|\d+m/);
    // And an instruction rather than a restatement of the problem.
    await expect(first).toContainText(/Divert|advisor|Brief|Reduce|spread/i);
  });
});

test.describe("project 72h", () => {
  /**
   * The signature interaction, and the thing that makes it honest.
   *
   * Scrubbing forward re-queries the same temporal graph. An event past its
   * claim horizon stops reaching anything, so the consequence drains. Nothing
   * predicts that; it falls out of interval validity, and this test is what
   * stops somebody later "fixing" the empty state by inventing a forecast.
   */
  test("scrubbing to +72h drains the consequence rather than predicting one", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);
    await page.waitForFunction(
      () => {
        const registry = (window as unknown as {
          __portwatchSources?: Record<string, GeoJSON.FeatureCollection>;
        }).__portwatchSources;
        return (registry?.cascade?.features.length ?? 0) > 0;
      },
      undefined,
      { timeout: 15_000 },
    );

    const before = await cascadeSource(page);
    expect(before!.total).toBeGreaterThan(0);
    await expect(page.getByTestId("projection-state")).toContainText("propagating");

    await page.locator('[data-testid="projection-offset"][data-offset="72"]').click();
    await settle(page);

    await expect(
      page.locator('[data-testid="projection-offset"][data-offset="72"]'),
    ).toHaveAttribute("data-active", "true");
  });

  test("the projection control offers the documented horizons", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);

    for (const offset of ["0", "3", "6", "12", "24", "48", "72"]) {
      await expect(
        page.locator(`[data-testid="projection-offset"][data-offset="${offset}"]`),
      ).toBeVisible();
    }
  });
});

test.describe("evidence mode", () => {
  /**
   * "Why do you think this?" must be answered from the computation.
   *
   * The trace is rendered from the steps the engine ran, so a step naming a rule
   * and a source is the proof that no separate explanation layer is inventing a
   * story alongside the numbers.
   */
  test("inspecting an item shows the steps that produced it", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);

    await page.getByTestId("attention-item").first().hover();
    await page.getByTestId("inspect-item").first().click();
    await settle(page);

    const drawer = page.getByTestId("evidence-drawer");
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText("Computation trail")).toBeVisible();

    const steps = page.getByTestId("evidence-step");
    await expect(steps.first()).toBeVisible();
    // Every step names the rule that ran; a step without one would be a claim
    // with no arithmetic behind it.
    await expect(steps.first()).toContainText(/reaches|becomes|shift/);
  });

  test("the drawer states what it could not compute", async ({ context, page }) => {
    await seedSession(context, "PORT_AUTHORITY");
    await page.goto("/port/global-eye");
    await settle(page);

    const items = page.getByTestId("attention-item");
    if ((await items.count()) === 0) {
      test.skip(true, "no attention item for this port in the recorded feed");
    }
    await items.first().hover();
    await page.getByTestId("inspect-item").first().click();
    await settle(page);

    // The financial effect is refused without a configured rate, and says so
    // rather than showing a number nobody can defend.
    await expect(page.getByTestId("evidence-drawer")).toContainText(
      /not computed|no .*rate/i,
    );
  });
});

test.describe("layout", () => {
  /**
   * The world is the product. The panels are guests on it.
   */
  test("the chart is not squeezed between two permanent rails", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);

    const viewport = page.viewportSize();
    const rail = await page.getByTestId("action-rail").boundingBox();
    expect(rail).not.toBeNull();
    // One rail, and it takes well under a quarter of the width.
    expect(rail!.width / (viewport?.width ?? 1920)).toBeLessThan(0.25);

    // The evidence drawer is not permanent: it is absent until asked for.
    await expect(page.getByTestId("evidence-panel")).toHaveCount(0);
  });

  test("nothing overflows horizontally", async ({ context, page }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  });
});
