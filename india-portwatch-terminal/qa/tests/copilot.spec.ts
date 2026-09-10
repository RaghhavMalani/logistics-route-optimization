/**
 * The Copilot loop, and the lenses.
 *
 * The claim being tested is narrow and important: an answer *moves the world*.
 * A Copilot that returned commands the application ignored would look
 * identical in every screenshot and in every unit test of the backend, and it
 * is exactly what this milestone existed to fix -- the commands were being
 * emitted and thrown away.
 *
 * The second claim is that a lens is a reading rather than a mode. Switching
 * one must change what is drawn and must not change what is true, so the tests
 * assert both halves: the layers move, the cascade does not.
 */

import {
  expect,
  horizontalOverflow,
  seedSession,
  settle,
  test,
} from "../harness";

/** The world's own state, as the dispatcher left it. */
async function worldState(page: import("@playwright/test").Page) {
  return page.evaluate(() => ({
    lens: document
      .querySelector('[data-testid="lens-option"][data-active="true"]')
      ?.getAttribute("data-lens"),
    cascadeFeatures:
      (window as unknown as {
        __portwatchSources?: Record<string, GeoJSON.FeatureCollection>;
      }).__portwatchSources?.cascade?.features.length ?? 0,
    attentionCount: document.querySelectorAll('[data-testid="attention-item"]').length,
  }));
}

test.describe("spatial copilot", () => {
  test("the command bar opens on its shortcut and on its control", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);

    // Compact by default: a control, not a panel taking a third of the screen.
    await expect(page.getByTestId("command-bar-open")).toBeVisible();
    await expect(page.getByTestId("command-bar")).toHaveCount(0);

    await page.keyboard.press("ControlOrMeta+k");
    await expect(page.getByTestId("command-bar")).toBeVisible();
    await expect(page.getByTestId("command-input")).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(page.getByTestId("command-bar")).toHaveCount(0);
  });

  /**
   * The loop closing. An answer selects the event, draws its cascade and
   * narrows the queue -- without the operator touching the map.
   */
  test("asking a question moves the world", async ({ context, page }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);

    await page.getByTestId("command-bar-open").click();
    await page.getByTestId("command-suggestion").first().click();

    await expect(page.getByTestId("command-answer")).toBeVisible({ timeout: 20_000 });

    // What changed is reported, and it is not empty.
    const applied = page.getByTestId("command-applied");
    await expect(applied).toBeVisible();
    const changes = await applied.innerText();
    expect(changes.length).toBeGreaterThan(0);
    // The recorded run focuses an event and draws its cascade.
    expect(changes.toLowerCase()).toContain("cascade");

    await settle(page);
    const state = await worldState(page);
    expect(state.cascadeFeatures).toBeGreaterThan(0);
  });

  /**
   * A refusal is reported rather than swallowed.
   *
   * An operator has to be able to tell "the camera moved" from "and something
   * was also sent". A Copilot that quietly dropped what it could not run would
   * make that distinction invisible.
   */
  test("a command the world will not run is reported, not hidden", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);

    // Drive the dispatcher directly with the two classes that must not run
    // automatically, then assert both were refused with a reason.
    const outcomes = await page.evaluate(() => {
      const probe = (window as unknown as {
        __portwatchWorld?: {
          dispatch: (c: Record<string, unknown>) => {
            kind: string; applied: boolean; reason: string;
          };
        };
      }).__portwatchWorld;
      if (!probe) return null;
      return [
        probe.dispatch({ kind: "COMPARE_SCENARIOS", subject: "x", safety: "SIMULATION" }),
        probe.dispatch({ kind: "ISSUE_ADVISORY", subject: "x", safety: "OPERATIONAL" }),
        probe.dispatch({ kind: "FOCUS_VESSEL", safety: "UI" }),
      ];
    });

    expect(outcomes).not.toBeNull();
    const [simulation, operational, unnamed] = outcomes!;

    expect(simulation.applied).toBe(false);
    expect(simulation.reason).toContain("simulation context");

    // The one that must never run from an answer, at any confidence.
    expect(operational.applied).toBe(false);
    expect(operational.reason).toContain("approval boundary");

    expect(unnamed.applied).toBe(false);
    expect(unnamed.reason).toContain("no vessel named");
  });
});

test.describe("world lenses", () => {
  test("all six lenses are offered on the world, not as pages", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);

    await expect(page.getByTestId("lens-bar")).toBeVisible();
    await expect(page.getByTestId("lens-option")).toHaveCount(6);

    const before = page.url();
    await page.locator('[data-testid="lens-option"][data-lens="INTELLIGENCE"]').click();
    await settle(page);
    // A lens is not a route.
    expect(page.url()).toBe(before);
    await expect(
      page.locator('[data-testid="lens-option"][data-lens="INTELLIGENCE"]'),
    ).toHaveAttribute("data-active", "true");
  });

  /**
   * A lens changes what is drawn and not what is true.
   *
   * The cascade is the world's conclusion. If switching a reading of it changed
   * the conclusion, the six lenses would be six different products.
   */
  test("switching lens does not change the computed world", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);
    await page.waitForFunction(
      () =>
        ((window as unknown as {
          __portwatchSources?: Record<string, GeoJSON.FeatureCollection>;
        }).__portwatchSources?.cascade?.features.length ?? 0) > 0,
      undefined,
      { timeout: 15_000 },
    );

    const before = await worldState(page);
    await page.locator('[data-testid="lens-option"][data-lens="INTELLIGENCE"]').click();
    await settle(page);
    const after = await worldState(page);

    expect(after.lens).toBe("INTELLIGENCE");
    expect(after.cascadeFeatures).toBe(before.cascadeFeatures);
    expect(after.attentionCount).toBe(before.attentionCount);
  });

  /**
   * A lens describing something unobservable says so.
   *
   * This is the most important assertion in the file. A security lens that drew
   * plausible detections over replayed traffic would be detections *of the
   * simulator*, and an operator would act on them.
   */
  test("a lens with no underlying observation refuses to draw one", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);

    for (const lens of ["SECURITY", "CARGO", "FINANCIAL"]) {
      await page.locator(`[data-testid="lens-option"][data-lens="${lens}"]`).click();
      await settle(page);
      const notice = page.getByTestId("lens-unavailable");
      await expect(notice).toBeVisible();
      // It states what is missing and what would fix it, rather than an
      // apology with no next step.
      await expect(notice).toContainText(/unavailable/i);
    }
  });

  test("an observable lens draws rather than apologising", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);

    for (const lens of ["OPERATIONS", "INTELLIGENCE", "WEATHER"]) {
      await page.locator(`[data-testid="lens-option"][data-lens="${lens}"]`).click();
      await settle(page);
      await expect(page.getByTestId("lens-unavailable")).toHaveCount(0);
    }
  });

  test("the lens bar does not push the world off screen", async ({
    context,
    page,
  }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/global-eye");
    await settle(page);
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  });
});
