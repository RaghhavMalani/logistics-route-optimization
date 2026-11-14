import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve, join } from "node:path";
import { chromium, expect } from "@playwright/test";

const origin = process.env.LIVE_NOW_ORIGIN;
const url = new URL(origin);
assert(
  ["127.0.0.1", "localhost"].includes(url.hostname) ||
    /^india-portwatch-[a-z0-9]+-flash2404s-projects\.vercel\.app$/.test(
      url.hostname,
    ),
  "Evidence login is restricted to local or preview, never production",
);
const out = resolve(process.env.LIVE_NOW_EVIDENCE);
const baseline = process.argv.includes("--before");
const reviewed = process.argv.includes("--reviewed");
await mkdir(out, { recursive: true });
const browser = await chromium.launch();
try {
  for (const [width, height] of [
    [1366, 768],
    [1280, 720],
  ]) {
    const context = await browser.newContext({
      viewport: { width, height },
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    page.setDefaultTimeout(30_000);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("response", (response) => {
      if (
        response.status() >= 400 &&
        new URL(response.url()).pathname.startsWith("/api/")
      )
        errors.push(`${response.status()} ${new URL(response.url()).pathname}`);
    });
    const shot = (name, locator = page) =>
      locator.screenshot({ path: join(out, `${width}-${name}.png`) });
    await page.goto(origin + "/login");
    await expect(page.getByText("Data service", { exact: true })).toBeVisible();
    await expect(page.getByText("Reachable", { exact: true })).toBeVisible();
    if (!baseline)
      await expect(page.getByTestId("login-source-freshness")).not.toHaveText(
        "Unmeasured",
      );
    await shot("login-environment");
    await page
      .getByRole("button", { name: "Company demo", exact: true })
      .click();
    await page.waitForURL("**/company/overview");
    await expect(page.getByText("Data now", { exact: true })).toBeVisible();
    if (!baseline) await expect(page.getByTestId("live-pulse")).toBeVisible();
    await page.waitForTimeout(1500);
    await shot("company");
    await shot(
      "data-now",
      page.getByText("Data now", { exact: true }).locator(".."),
    );
    if (!baseline) await shot("pulse", page.getByTestId("live-pulse"));
    await page.getByRole("button", { name: /Demo role/i }).click();
    await page.getByRole("menuitem", { name: /Vessel Bridge/ }).click();
    await page.waitForURL("**/vessel/overview");
    await expect(page.getByTestId("time-transport")).toBeVisible();
    await page.waitForTimeout(1200);
    await shot("vessel-bridge");
    await shot("vessel-timeline", page.getByTestId("time-transport"));
    const summary = {
      origin,
      width,
      height,
      capturedAt: new Date().toISOString(),
      pulse: !baseline
        ? await page.getByTestId("live-pulse").innerText()
        : null,
      timeline: await page.getByTestId("time-transport").innerText(),
      errors,
    };
    await writeFile(
      join(out, `${width}-receipt.json`),
      JSON.stringify(summary, null, 2),
    );
    if (reviewed) {
      await page.goto(origin + "/sources");
      await expect(
        page.getByRole("heading", { name: "Sources", exact: true }),
      ).toBeVisible();
      for (const [id, title] of [
        ["extended-marine", "Marine waves, swell and currents"],
        ["ensemble", "Weather ensemble members"],
        ["ecb", "ECB reference rates via Frankfurter"],
      ]) {
        const card = page.getByRole("listitem").filter({
          has: page.getByRole("heading", { name: title, exact: true }),
        });
        await card
          .getByText(
            id === "ecb"
              ? "View ECB reference rates"
              : "View modelled readings",
            { exact: true },
          )
          .click();
        await expect(
          card
            .getByRole("term")
            .filter({ hasText: /Waves|Wind member range|ECB reference rate/ })
            .first(),
        ).toBeVisible();
        await shot(`sources-${id}`, card);
      }
      await writeFile(
        join(out, `${width}-receipt.json`),
        JSON.stringify({ ...summary, reviewed: true }, null, 2),
      );
    }
    assert.equal(errors.length, 0, JSON.stringify(errors));
    await context.close();
  }
} finally {
  await browser.close();
}
