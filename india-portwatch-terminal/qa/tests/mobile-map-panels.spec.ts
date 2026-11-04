import { test, expect } from "@playwright/test";

// Actual local visitor and API. No route fixtures, forced clicks or DOM events.
test("Layers remains operable with the original inspector and retains workspace state", async ({
  page,
}, info) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Company demo", exact: true }).click();
  await expect(page).toHaveURL(/\/company\/overview$/);
  const fleet = page.getByTestId("fleet-command-panel");
  await expect(fleet).toBeVisible();
  await fleet.getByTestId("action-required-row").first().click();
  await expect(page.getByText("Particulars", { exact: true })).toBeVisible();
  await page.screenshot({
    path: `../phase-a-before-layers-${info.project.name}.png`,
  });
  const mobile = (page.viewportSize()?.width ?? 1366) < 700;
  const trigger = fleet.getByRole("button", {
    name: "Layers and filters",
    exact: true,
  });
  const layers = mobile
    ? trigger
    : page.getByRole("button", { name: "Layers and filters", exact: true });
  await layers.click();
  const scope = mobile
    ? page.getByTestId("mobile-map-layers")
    : page
        .getByRole("button", { name: "Vessel traffic", exact: true })
        .locator("..")
        .locator("..");
  const traffic = scope.getByRole("button", {
    name: "Vessel traffic",
    exact: true,
  });
  await expect(traffic).toHaveClass(/bg-\[var\(--panel-4\)\]/);
  await traffic.click();
  await expect(traffic).toHaveClass(/bg-transparent/);
  if (mobile) {
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("mobile-map-layers")).toBeHidden();
    await expect(trigger).toBeFocused();
    await expect(page.getByText("Particulars", { exact: true })).toBeVisible();
    await trigger.click();
    await expect(traffic).toHaveClass(/bg-transparent/);
    await page
      .getByRole("button", { name: "Return to inspector", exact: true })
      .click();
    await fleet
      .getByRole("button", { name: "Timeline controls", exact: true })
      .click();
    await expect(
      page.getByRole("slider", { name: "Forecast lead time in hours" }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Return to inspector", exact: true })
      .click();
  } else {
    await layers.click();
  }
  await page.getByRole("button", { name: /Fleet review queue/ }).click();
  await expect(page.getByTestId("company-fleet-triage")).toBeVisible();
  await page.keyboard.press("Escape");
  await layers.click();
  await expect(traffic).toHaveClass(/bg-transparent/);
  if (mobile) {
    await page.evaluate(
      () => (document.documentElement.style.fontSize = "24px"),
    );
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      )
      .toBe(true);
    await page
      .getByRole("button", { name: "Return to inspector", exact: true })
      .click();
  }
  await page.screenshot({
    path: `../phase-a-after-layers-${info.project.name}.png`,
  });
});
