import { expect, seedSession, settle, test, type Role } from "../harness";

for (const [role, path] of [
  ["SHIPPING_COMPANY", "/company/overview"],
  ["PORT_AUTHORITY", "/port/overview"],
  ["VESSEL_OPERATOR", "/vessel/overview"],
  ["NATIONAL_ADMIN", "/admin/radar"],
] as [Role, string][]) {
  test(`${role} shows one source pulse with honest retained states`, async ({ context, page }) => {
    await page.clock.setFixedTime(new Date("2026-11-06T12:00:00Z"));
    await seedSession(context, role);
    await page.goto(path);
    await settle(page);
    const pulse = page.getByTestId("live-pulse");
    await expect(pulse).toHaveCount(1);
    await expect(pulse.locator('[data-source="imf-portwatch-data"]')).toHaveAttribute("data-status", "stale");
    await expect(pulse.locator('[data-source="aisstream-websocket"]')).toHaveAttribute("data-status", "unavailable");
    await expect(page.getByTestId("weather-offset")).toHaveText("Latest available");
    await expect(page.getByRole("button", { name: "NOW", exact: true })).toHaveCount(0);
  });
}

test("login and Sources expose degradation, source dates and unmeasured rates", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-11-06T12:00:00Z"));
  await page.goto("/login");
  await expect(page.getByTestId("login-source-freshness")).toHaveText("Degraded · latest available data");
  await page.goto("/sources");
  await expect(page.getByTestId("source-latest-available")).toHaveCount(3);
  await expect(page.getByText("Unmeasured", { exact: true }).first()).toBeVisible();
});
