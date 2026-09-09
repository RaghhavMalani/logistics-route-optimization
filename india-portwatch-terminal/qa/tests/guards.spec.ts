/**
 * Access control.
 *
 * A role is not a cosmetic filter, so these tests assert the negative: a
 * vessel operator who types an admin address does not reach it, and an
 * anonymous visitor reaches nothing but the sign-in screen.
 *
 * The pair worth watching is PORT_AUTHORITY and SHIPPING_COMPANY. They are the
 * two ends of an advisory, and a carrier reaching a port authority's control
 * room would collapse the human approval step the whole workflow rests on.
 */

import { expect, seedSession, settle, test, type Role } from "../harness";

const HOME: Record<Role, string> = {
  VESSEL_OPERATOR: "/vessel/overview",
  SHIPPING_COMPANY: "/company/overview",
  PORT_AUTHORITY: "/port/overview",
  NATIONAL_ADMIN: "/admin/radar",
};

test.describe("anonymous", () => {
  const GUARDED = ["/admin/radar", "/port/overview", "/vessel/fleet", "/company/overview", "/"];

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
    ["VESSEL_OPERATOR", "/company/overview"],
    ["PORT_AUTHORITY", "/admin/radar"],
    ["PORT_AUTHORITY", "/vessel/fleet"],
    // The boundary that matters most: a carrier has no business inside a port
    // authority's control room, and the port issues advisories to the carrier.
    ["PORT_AUTHORITY", "/company/overview"],
    ["SHIPPING_COMPANY", "/port/overview"],
    ["SHIPPING_COMPANY", "/port/advisories"],
    ["SHIPPING_COMPANY", "/admin/learning"],
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
    ["NATIONAL_ADMIN", "/admin/radar"],
    ["NATIONAL_ADMIN", "/admin/learning"],
    ["NATIONAL_ADMIN", "/admin/agents"],
    ["NATIONAL_ADMIN", "/port/overview"],
    ["NATIONAL_ADMIN", "/vessel/fleet"],
    ["NATIONAL_ADMIN", "/company/overview"],
    ["PORT_AUTHORITY", "/port/decisions"],
    ["PORT_AUTHORITY", "/port/advisories"],
    ["SHIPPING_COMPANY", "/company/risk"],
    ["SHIPPING_COMPANY", "/company/global-eye"],
    // A fleet desk drills into one of its own ships, so the vessel workspace is
    // in scope for a carrier.
    ["SHIPPING_COMPANY", "/vessel/routes"],
    ["VESSEL_OPERATOR", "/vessel/routes"],
    ["VESSEL_OPERATOR", "/vessel/advisories"],
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
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/radar");
    await settle(page);
    await expect(page.getByText("View as")).toBeVisible();

    await context.clearCookies();
    await page.evaluate(() => window.localStorage.clear());
    await seedSession(context, "PORT_AUTHORITY");
    await page.goto("/port/overview");
    await settle(page);
    await expect(page.getByText("View as")).toHaveCount(0);
  });

  test("a port authority is locked to their own facility", async ({ context, page }) => {
    await seedSession(context, "PORT_AUTHORITY");
    await page.goto("/port/overview");
    await settle(page);
    await expect(page.getByText("Facility scope")).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Select port" })).toHaveCount(0);
  });

  test("an admin inspecting a port may switch facility", async ({ context, page }) => {
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/port/overview");
    await settle(page);
    await expect(page.getByRole("combobox", { name: "Select port" })).toBeVisible();
  });
});

test.describe("advisory workflow", () => {
  test("a controller sees the issuing side", async ({ context, page }) => {
    await seedSession(context, "PORT_AUTHORITY");
    await page.goto("/port/advisories");
    await settle(page);
    await expect(page.getByTestId("advisory-register")).toBeVisible();
    await expect(
      page.getByText(/A draft is not visible to the recipient until a named controller issues it/i),
    ).toBeVisible();
  });

  test("a carrier sees the recipient side and is told drafts are withheld", async ({
    context,
    page,
  }) => {
    await seedSession(context, "SHIPPING_COMPANY");
    await page.goto("/company/advisories");
    await settle(page);
    await expect(page.getByTestId("advisory-register")).toBeVisible();
    // The filter tab and the panel title both carry this label, so the first
    // match is the assertion -- the point is that the recipient side rendered.
    await expect(page.getByText("Awaiting response").first()).toBeVisible();
  });

  test("the API states that identity is asserted rather than verified", async ({
    context,
    page,
  }) => {
    await seedSession(context, "PORT_AUTHORITY");
    await page.goto("/port/advisories");
    await settle(page);
    await expect(page.getByText("asserted, not verified")).toBeVisible();
  });
});

test.describe("sign-in", () => {
  test("a signed-in operator is moved off the sign-in screen", async ({ context, page }) => {
    await seedSession(context, "VESSEL_OPERATOR");
    await page.goto("/login");
    await settle(page);
    await expect(page).toHaveURL(/\/vessel\/overview$/);
  });

  test("the demo roster signs a port authority in", async ({ page }) => {
    await page.goto("/login");
    await settle(page);
    await page.getByRole("button", { name: /port@portwatch\.demo/ }).click();
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/port\/overview$/, { timeout: 15_000 });
    await expect(page.getByText("Port Authority")).toBeVisible();
  });

  test("the demo roster signs a shipping company in", async ({ page }) => {
    await page.goto("/login");
    await settle(page);
    await page.getByRole("button", { name: /company@portwatch\.demo/ }).click();
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/company\/overview$/, { timeout: 15_000 });
    await expect(page.getByText("Fleet Command").first()).toBeVisible();
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
    await seedSession(context, "NATIONAL_ADMIN");
    await page.goto("/admin/radar");
    await settle(page);
    await page.getByRole("button", { name: /A\. Deshmukh/ }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
  });

  /**
   * A session written by the previous build restores rather than being thrown
   * away. Everyone signed in at deploy time would otherwise land on the login
   * screen with no explanation, which reads as a bug.
   */
  test("a session with a pre-rename role still restores", async ({ context, page }) => {
    const now = Date.now();
    await context.addInitScript(
      (session) => {
        window.localStorage.setItem("portwatch.session.v1", session as string);
        window.localStorage.setItem("portwatch.viewAs.v1", JSON.stringify("ADMIN"));
      },
      JSON.stringify({
        user: {
          id: "demo-admin",
          email: "admin@portwatch.demo",
          displayName: "A. Deshmukh",
          role: "ADMIN",
          organisation: "National Maritime Operations Centre",
          portCode: null,
        },
        mode: "demo",
        issuedAt: new Date(now).toISOString(),
        expiresAt: new Date(now + 12 * 3_600_000).toISOString(),
      }),
    );
    await page.goto("/");
    await settle(page);
    await expect(page).toHaveURL(/\/admin\/radar$/);
  });
});
