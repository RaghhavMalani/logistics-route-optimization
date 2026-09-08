/**
 * Access control.
 *
 * A role is not a cosmetic filter, so these tests assert the negative: a
 * vessel operator who types an admin address does not reach it, and an
 * anonymous visitor reaches nothing but the sign-in screen.
 */

import { expect, seedSession, settle, test, type Role } from "../harness";

const HOME: Record<Role, string> = {
  VESSEL_OPERATOR: "/vessel/overview",
  PORT_OPERATOR: "/port/overview",
  ADMIN: "/admin/radar",
};

test.describe("anonymous", () => {
  const GUARDED = ["/admin/radar", "/port/overview", "/vessel/fleet", "/"];

  for (const path of GUARDED) {
    test(`${path} sends an anonymous visitor to sign in`, async ({ page }) => {
      await page.goto(path);
      await settle(page);
      await expect(page).toHaveURL(/\/login/);
      await expect(page.getByRole("heading", { name: "Secure sign-in" })).toBeVisible();
    });
  }

  test("the return address survives the redirect", async ({ page }) => {
    await page.goto("/admin/model");
    await settle(page);
    expect(page.url()).toContain("next=%2Fadmin%2Fmodel");
  });
});

test.describe("role scope", () => {
  const DENIED: Array<[Role, string]> = [
    ["VESSEL_OPERATOR", "/admin/radar"],
    ["VESSEL_OPERATOR", "/admin/data"],
    ["VESSEL_OPERATOR", "/port/overview"],
    ["PORT_OPERATOR", "/admin/radar"],
    ["PORT_OPERATOR", "/vessel/fleet"],
  ];

  for (const [role, path] of DENIED) {
    test(`${role} cannot reach ${path}`, async ({ context, page }) => {
      await seedSession(context, role);
      await page.goto(path);
      await settle(page);
      await expect(page).toHaveURL(new RegExp(`${HOME[role].replace(/\//g, "\\/")}$`));
    });
  }

  const ALLOWED: Array<[Role, string]> = [
    ["ADMIN", "/admin/radar"],
    ["ADMIN", "/port/overview"],
    ["ADMIN", "/vessel/fleet"],
    ["PORT_OPERATOR", "/port/decisions"],
    ["VESSEL_OPERATOR", "/vessel/routes"],
  ];

  for (const [role, path] of ALLOWED) {
    test(`${role} may reach ${path}`, async ({ context, page }) => {
      await seedSession(context, role);
      await page.goto(path);
      await settle(page);
      expect(page.url()).toContain(path);
    });
  }

  test("an admin sees the workspace switcher; an operator does not", async ({
    context,
    page,
  }) => {
    await seedSession(context, "ADMIN");
    await page.goto("/admin/radar");
    await settle(page);
    await expect(page.getByText("View as")).toBeVisible();

    await context.clearCookies();
    await page.evaluate(() => window.localStorage.clear());
    await seedSession(context, "PORT_OPERATOR");
    await page.goto("/port/overview");
    await settle(page);
    await expect(page.getByText("View as")).toHaveCount(0);
  });

  test("a port operator is locked to their own facility", async ({ context, page }) => {
    await seedSession(context, "PORT_OPERATOR");
    await page.goto("/port/overview");
    await settle(page);
    await expect(page.getByText("Facility scope")).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Select port" })).toHaveCount(0);
  });

  test("an admin inspecting a port may switch facility", async ({ context, page }) => {
    await seedSession(context, "ADMIN");
    await page.goto("/port/overview");
    await settle(page);
    await expect(page.getByRole("combobox", { name: "Select port" })).toBeVisible();
  });
});

test.describe("sign-in", () => {
  test("a signed-in operator is moved off the sign-in screen", async ({ context, page }) => {
    await seedSession(context, "VESSEL_OPERATOR");
    await page.goto("/login");
    await settle(page);
    await expect(page).toHaveURL(/\/vessel\/overview$/);
  });

  test("the demo roster signs a port operator in", async ({ page }) => {
    await page.goto("/login");
    await settle(page);
    await page.getByRole("button", { name: /port@portwatch\.demo/ }).click();
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/port\/overview$/, { timeout: 15_000 });
    await expect(page.getByText("Port Operator")).toBeVisible();
  });

  test("a bad password is refused, and says so", async ({ page }) => {
    await page.goto("/login");
    await settle(page);
    await page.getByLabel("Password").fill("not-the-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText(/Unrecognised account or password/)).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("signing out returns to the sign-in screen", async ({ context, page }) => {
    await seedSession(context, "ADMIN");
    await page.goto("/admin/radar");
    await settle(page);
    await page.getByRole("button", { name: /A\. Deshmukh/ }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
  });
});
