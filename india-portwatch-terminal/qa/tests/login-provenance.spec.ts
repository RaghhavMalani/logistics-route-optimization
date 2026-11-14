import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

const ports = JSON.parse(
  readFileSync(
    new URL(
      "../../src/components/miniature/ports.generated.json",
      import.meta.url,
    ),
    "utf8",
  ),
) as Array<{ code: string }>;

const origin = "2026-11-03T00:00:00Z";

for (const state of ["current", "expired", "unavailable"] as const) {
  test(`login states forecast provenance independently of registry coverage (${state})`, async ({
    page,
  }) => {
    await page.route("**/api/health", (route) =>
      state === "unavailable"
        ? route.fulfill({ status: 401, json: { detail: "Unauthorized" } })
        : route.fulfill({
            json: {
              forecastOrigin: origin,
              forecastOriginStatus: state === "current" ? "LIVE" : "STALE",
              targetThrough: "2026-11-12",
              targetStatus: state === "current" ? "CURRENT_HORIZON" : "EXPIRED",
              ports: ports.length - 1,
            },
          }),
    );
    await page.goto("/login");
    await expect(page).toHaveTitle("PortWatch X — Sign in");
    await expect(
      page.getByRole("button", { name: "Company demo", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Start the 3-minute demo" }),
    ).toBeVisible();
    await expect(page.getByLabel("Email", { exact: true })).toBeHidden();
    await page.getByText("Live status", { exact: true }).click();
    await expect(
      page.getByText(new RegExp(`^${ports.length} registered`)),
    ).toBeVisible();
    if (state === "unavailable") {
      await expect(
        page.getByText("Unreachable", { exact: true }),
      ).toBeVisible();
      await expect(page.getByText("Unavailable", { exact: true })).toHaveCount(
        2,
      );
    } else {
      await expect(
        page.getByText(`${ports.length - 1} in forecast export`, {
          exact: false,
        }),
      ).toBeVisible();
      await expect(
        page.getByText(
          `2026-11-03 00:00Z · ${state === "current" ? "Current" : "Stale"}`,
        ),
      ).toBeVisible();
      await expect(
        page.getByText(state === "current" ? /Current horizon/ : /Expired/),
      ).toBeVisible();
    }
    await expect(page.getByText(/walk-forward validated/i)).toHaveCount(0);
  });
}
