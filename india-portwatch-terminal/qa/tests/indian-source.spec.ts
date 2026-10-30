import fs from "node:fs";
import { expect, test } from "@playwright/test";

// Actual retained authority product and local visitor. Only the explicit
// source-read failure/retry below is a simulated network interruption.
test("historical Indian source is inspectable with audit parity and an explicit owned declaration", async ({
  page,
}, info) => {
  test.setTimeout(120000);
  await page.goto("/login");
  await page.getByRole("button", { name: "Company demo", exact: true }).click();
  await expect(page).toHaveURL(/\/company\/overview$/);
  await page.goto(
    "/company/global-eye#intelligence-review?noticeId=NHO_NAVAREA_VIII%3A609%2F25&vesselId=PWD-001",
  );
  const panel = page.getByTestId("indian-source-review");
  await expect(panel).toBeVisible({ timeout: 30000 });
  await expect(panel).toContainText("HISTORICAL_PRODUCT");
  await expect(panel).toContainText("2025-07-07 · date only");
  await expect(panel).toContainText(
    "does not establish today's in-force condition",
  );
  await panel
    .getByText("Source identity, revisions and use limits", { exact: true })
    .click();
  await expect(panel).toContainText(
    "e216905fa5edf106a6bae93a42256a3b34a72280b28a930cc189f75c2667f518",
  );
  const downloading = page.waitForEvent("download");
  await panel
    .getByRole("button", { name: "Download source audit", exact: true })
    .click();
  const download = await downloading;
  const path = await download.path();
  const audit = JSON.parse(fs.readFileSync(path!, "utf8"));
  expect(audit.notice.noticeId).toBe("NHO_NAVAREA_VIII:609/25");
  expect(audit.notice.documentPages).toEqual([8]);
  expect(audit.notice.sourceStatus).toBe("HISTORICAL_PRODUCT");
  expect(audit.numericalConsequence).toBe("UNAVAILABLE");
  expect(audit.realOperationalTargetsResolved).toBe(0);
  expect(audit.notice).not.toHaveProperty("sourceText");
  const sourceUrl = "**/api/demo/terminal/intelligence/navigation-restrictions";
  const refreshUrl =
    "**/api/demo/terminal/intelligence/navigation-restrictions/refresh";
  await page.route(sourceUrl, (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "SIMULATED retained-read interruption" },
    }),
  );
  await page.route(refreshUrl, (route) =>
    route.fulfill({
      json: { status: "SIMULATED_REFRESH_NO_PROVIDER_REQUEST" },
    }),
  );
  await page
    .getByRole("button", { name: "Explicitly refresh source", exact: true })
    .click();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "SIMULATED retained-read interruption" }),
  ).toBeVisible();
  await expect(panel).toContainText("HISTORICAL_PRODUCT");
  await page.unroute(sourceUrl);
  await page.unroute(refreshUrl);
  await page
    .getByRole("button", { name: "Retry retained source read", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Retry retained source read",
      exact: true,
    }),
  ).toBeHidden();
  await panel
    .getByText("Declare this owned voyage's Paradip approach", { exact: true })
    .click();
  const declare = panel.getByRole("button", {
    name: "Declare fictional Paradip approach",
    exact: true,
  });
  await expect(declare).toBeDisabled();
  const when = new Date(Date.now() + 24 * 3600000).toISOString().slice(0, 16);
  await panel.getByLabel("Indian passage UTC", { exact: true }).fill(when);
  await panel.getByLabel("Indian onward hours", { exact: true }).fill("0");
  await expect(declare).toBeDisabled();
  await panel
    .getByRole("checkbox", { name: /These are fictional operator-declared/ })
    .check();
  await declare.click();
  const next = panel.getByRole("link", {
    name: "Review current inputs for this exact voyage",
    exact: true,
  });
  await expect(next).toBeVisible();
  await expect(next).toHaveAttribute(
    "href",
    /current-inputs\?vesselId=PWD-001&episodeId=/,
  );
  await panel.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("indian-real-source.png"),
  });
  const state = await page.evaluate(() =>
    JSON.parse(sessionStorage.getItem("portwatch.session.v1")!),
  );
  const response = await page.request.get(
    "http://127.0.0.1:8815/api/demo/terminal/intelligence/navigation-restrictions",
    { headers: { Authorization: `Bearer ${state.accessToken}` } },
  );
  expect(response.ok()).toBeTruthy();
  const vessel = (await response.json()).voyages.find(
    (v: { id: string }) => v.id === "PWD-001",
  );
  expect(vessel.portCode).toBe("INPRT");
  expect(vessel.declaredPassages.NHO_PARADIP_DGPS.source).toBe(
    "OPERATOR_DECLARED_FICTIONAL_VOYAGE",
  );
  await next.click();
  await expect(
    page.getByRole("dialog", { name: "Current inputs for voyage planning" }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Current input voyage" }),
  ).toHaveValue("PWD-001");
  await page.keyboard.press("Escape");
});
