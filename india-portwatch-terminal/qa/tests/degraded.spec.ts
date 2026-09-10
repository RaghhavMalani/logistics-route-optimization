/**
 * What the terminal does when the data service is gone.
 *
 * The whole provenance design exists so a degraded run is honest rather than
 * broken, and that has to hold at the interface too: no blank screen, no
 * spinner that never resolves, no plausible-looking number standing in for a
 * measurement that was never made.
 */

import { expect, killApi, seedSession, settle, test } from "../harness";

const WORKSPACES: Array<[Parameters<typeof seedSession>[1], string]> = [
  ["NATIONAL_ADMIN", "/admin/radar"],
  ["NATIONAL_ADMIN", "/admin/data"],
  ["PORT_AUTHORITY", "/port/overview"],
  ["VESSEL_OPERATOR", "/vessel/overview"],
];

for (const [role, path] of WORKSPACES) {
  test(`${path} reports the outage instead of hanging`, async ({ context, page }) => {
    await killApi(context);
    await seedSession(context, role);

    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(String(error)));

    await page.goto(path);
    await settle(page);

    // The shell still renders: an operator must be able to navigate away.
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByText("Feed down")).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText(/Operational data service unavailable|Service returned/),
    ).toBeVisible();
    // The one command that fixes it is on screen.
    await expect(page.getByText(/uvicorn backend\.app\.main:app/)).toBeVisible();
    expect(pageErrors).toEqual([]);
  });
}

test("the top bar marks the service as down", async ({ context, page }) => {
  await killApi(context);
  await seedSession(context, "NATIONAL_ADMIN");
  await page.goto("/admin/radar");
  await settle(page);
  await expect(page.getByText("API down")).toBeVisible({ timeout: 15_000 });
});

test("the sign-in screen reports an unreachable service", async ({ context, page }) => {
  await killApi(context);
  await page.goto("/login");
  await settle(page);
  await expect(page.getByRole("heading", { name: "Secure sign-in" })).toBeVisible();
  await expect(page.getByText("Unreachable")).toBeVisible({ timeout: 15_000 });
});

test("a missing artefact is reported as missing, not as zero", async ({ context, page }) => {
  // The recorded fixtures carry no artefacts for this port, so the API answers
  // 404 exactly as the real one does for a port outside the run.
  await seedSession(context, "NATIONAL_ADMIN");
  await page.goto("/port/overview");
  await settle(page);
  await page.getByRole("combobox", { name: "Select port" }).selectOption("INVTZ");
  await expect(page.getByText(/Artefact not in this run|No forecast rows/)).toBeVisible({
    timeout: 15_000,
  });
});
