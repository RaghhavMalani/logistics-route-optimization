import { expect, test } from "@playwright/test";

test("existing Global Eye globe returns to the same maritime chart", async ({
  page,
}, info) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Admin demo", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/radar$/);
  await page.goto("/admin/global-eye#intelligence-review");
  const dialog = page.getByRole("dialog", {
    name: "Connected global intelligence",
  });
  await expect(dialog).toBeVisible();
  const chart = await page.locator("canvas.maplibregl-canvas").elementHandle();
  await dialog
    .getByRole("button", { name: "Open God’s Eye globe", exact: true })
    .click();
  await expect(dialog.getByText(/God’s Eye View · MIT/)).toBeVisible({
    timeout: 30000,
  });
  await expect(dialog.locator(".cesium-widget canvas")).toBeVisible();
  await page.screenshot({ path: info.outputPath("global-eye-globe.png") });
  await dialog
    .getByRole("button", { name: "Hide additional globe", exact: true })
    .click();
  await expect(dialog.locator(".cesium-widget canvas")).toHaveCount(0);
  await dialog
    .getByRole("button", { name: "Close intelligence", exact: true })
    .click();
  expect(await chart?.evaluate((element) => element.isConnected)).toBe(true);
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
});

// Real isolated demo visitor. This checks shared chrome without replacing
// protected role screens or treating simulated traffic as observed AIS.
test("four restored role workspaces retain chart, layers, timeline and visitor identity", async ({
  page,
}, info) => {
  test.setTimeout(120000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("requestfailed", (request) =>
    errors.push(
      `${new URL(request.url()).pathname}: ${request.failure()?.errorText}`,
    ),
  );
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text().slice(0, 500));
  });
  await page.goto("/login");
  await expect(
    page.getByRole("button", { name: "Company demo", exact: true }),
    errors.join("\n"),
  ).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: "Company demo", exact: true }).click();
  await expect(page).toHaveURL(/\/company\/overview$/);
  const visitor = await page.evaluate(
    () => JSON.parse(sessionStorage.getItem("portwatch.session.v1")!).demoId,
  );
  const narrow = (page.viewportSize()?.width ?? 1366) < 700;
  async function chart(label: string) {
    await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
    const layers = page
      .getByRole("button", { name: "Layers and filters", exact: true })
      .first();
    await layers.click();
    const scope = narrow ? page.getByTestId("mobile-map-layers") : page;
    await expect(
      scope.getByRole("button", { name: "Vessel traffic", exact: true }),
    ).toBeVisible();
    await expect(
      scope.getByRole("button", { name: "Weather composite", exact: true }),
    ).toBeVisible();
    if (narrow) {
      await page.keyboard.press("Escape");
      await expect(layers).toBeFocused();
      await page
        .getByRole("button", { name: "Timeline controls", exact: true })
        .first()
        .click();
    } else await layers.click();
    await expect(
      page.getByRole("slider", { name: "Forecast lead time in hours" }),
    ).toBeVisible();
    if (narrow) await page.keyboard.press("Escape");
    await page.screenshot({ path: info.outputPath(`role-${label}.png`) });
  }
  await chart("company");
  for (const role of [
    { label: "Port Authority", path: "/port/overview" },
    { label: "Vessel Bridge", path: "/vessel/overview" },
    { label: "National Command", path: "/admin/radar" },
  ]) {
    await page.getByRole("button", { name: /Demo role/i }).click();
    await page.getByRole("menuitem", { name: new RegExp(role.label) }).click();
    await expect(page).toHaveURL(new RegExp(role.path + "$"));
    expect(
      await page.evaluate(
        () =>
          JSON.parse(sessionStorage.getItem("portwatch.session.v1")!).demoId,
      ),
    ).toBe(visitor);
    await chart(role.label.replaceAll(" ", "-"));
  }
});
