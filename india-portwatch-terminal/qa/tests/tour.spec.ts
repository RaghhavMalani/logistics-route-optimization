import { test, expect } from "@playwright/test";
test.setTimeout(180_000);

const headings = [
  "A port system you can read at a glance.",
  "It starts with an event far from the berth.",
  "Keep the plan unless an intervention survives the unknown.",
  "Three ships arriving, one quay, one plan.",
  "Will this consignment make its connection?",
  "Four roles. One world. Every number traced.",
];

test("tour renders and navigates with stored identity and all application API blocked", async ({
  page,
}) => {
  const calls: string[] = [],
    errors: string[] = [];
  page.on("request", (r) => {
    if (new URL(r.url()).pathname.startsWith("/api/")) calls.push(r.url());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (
      m.type() === "error" ||
      /Too many active WebGL|removed|deprecated/i.test(m.text())
    )
      errors.push(m.text());
  });
  await page.route("**/api/**", (route) => route.abort());
  // A stored visitor is intentionally present: the root must not start session restoration.
  await page.addInitScript(() => {
    const stored = JSON.stringify({
      mode: "demo",
      issuedAt: new Date().toISOString(),
      expiresAt: new Date(Date.now() + 3600000).toISOString(),
      accessToken: "synthetic-tour-session-token",
      user: {
        id: "synthetic-tour-visitor",
        role: "SHIPPING_COMPANY",
        email: "synthetic-tour@qa.invalid",
        displayName: "Synthetic tour visitor",
        organisation: "QA fictional company",
        companyId: "qa-tour",
        portCode: null,
        vesselIds: [],
      },
    });
    localStorage.setItem("portwatch.session.v1", stored);
    sessionStorage.setItem("portwatch.session.v1", stored);
  });
  await page.goto("/tour");
  await expect(
    page.getByRole("heading", { name: headings[0], exact: true }),
  ).toBeVisible();
  await expect
    .poll(async () =>
      Number(await page.locator("canvas").getAttribute("data-render-calls")),
    )
    .toBeGreaterThan(0);
  for (let i = 0; i < 6; i++) {
    const button = page.locator(".rail button").nth(i);
    await button.click();
    await expect(button).toHaveAttribute("aria-current", "step");
    await expect(
      page.getByRole("heading", { name: headings[i], exact: true }),
    ).toBeVisible();
  }
  await page.getByRole("button", { name: "2: Decide", exact: true }).click();
  if ((page.viewportSize()?.width ?? 1920) >= 900) {
    await expect(page.locator(".pin:visible")).toHaveCount(4);
  } else {
    // The reference portrait frustum places two world pins outside the viewport.
    // All four meanings must remain inspectable without moving their geometry.
    await page.getByText("Inspect chapter points (4)", { exact: true }).click();
    await expect(page.locator(".point-index dt")).toHaveCount(4);
    await expect(page.locator(".point-index")).toContainText(
      "Keep current plan",
    );
  }
  const pin = page.getByRole("button", { name: "Your hull", exact: true });
  await pin.click();
  await expect(page.getByRole("region", { name: "Your hull" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator("#tour-popover")).toHaveCount(0);
  await expect(pin).toBeFocused();
  await page.getByRole("button", { name: "3: Berth", exact: true }).click();
  await expect(page.getByRole("heading", { name: headings[3] })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(calls).toEqual([]);
  expect(errors).toEqual([]);
  await page.goto("/tour/");
  await expect(
    page.getByRole("heading", { name: headings[0], exact: true }),
  ).toBeVisible();
  expect(calls).toEqual([]);
  // Negative control: the same stored session does restore outside the tour.
  await page.goto("/login");
  await expect
    .poll(() =>
      calls.some((url) => new URL(url).pathname === "/api/demo/session"),
    )
    .toBe(true);
});

test("reduced motion freezes vehicles and snaps chapters without font dependencies", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("https://fonts.googleapis.com/**", (route) => route.abort());
  await page.route("https://fonts.gstatic.com/**", (route) => route.abort());
  await page.route("**/fonts/**", (route) => route.abort());
  await page.goto("/tour");
  await expect(page.locator(".pw-tour")).toHaveAttribute(
    "data-reduced-motion",
    "true",
  );
  await expect
    .poll(async () =>
      Number(await page.locator("canvas").getAttribute("data-render-calls")),
    )
    .toBeGreaterThan(0);
  await page.getByRole("button", { name: "3: Berth", exact: true }).click();
  await expect(page.locator("canvas")).toHaveAttribute(
    "data-progress",
    "3.0000",
  );
  await expect(page.locator("canvas")).toHaveAttribute(
    "data-animation-time",
    "0.000",
  );
  await expect(page.getByRole("heading", { name: headings[3] })).toBeVisible();
  await expect(page.locator(".card")).toHaveAttribute("data-changing", "false");
});

test("WebGL unavailable leaves the voyage fully usable", async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      this: HTMLCanvasElement,
      type: string,
      ...args: unknown[]
    ) {
      if (type.startsWith("webgl")) return null;
      return Reflect.apply(original, this, [type, ...args]);
    } as typeof original;
  });
  await page.goto("/tour");
  await expect(page.getByRole("status")).toContainText("needs WebGL");
  await page.getByRole("button", { name: "3: Berth", exact: true }).click();
  await expect(page.getByRole("heading", { name: headings[3] })).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open the role demos", exact: true }),
  ).toHaveAttribute("href", "/login");
});

test("five login round trips dispose the miniature without route scroll leakage", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (/Too many active WebGL|context lost/i.test(m.text()))
      errors.push(m.text());
  });
  await page.goto("/tour");
  for (let i = 0; i < 5; i++) {
    await expect
      .poll(async () =>
        Number(await page.locator("canvas").getAttribute("data-render-calls")),
      )
      .toBeGreaterThan(0);
    await page
      .getByRole("link", { name: "Open the role demos", exact: true })
      .click();
    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator(".pw-tour")).toHaveCount(0);
    await page.getByRole("link", { name: "Take the tour" }).click();
    await expect(
      page.getByRole("heading", { name: headings[0] }),
    ).toBeVisible();
  }
  expect(errors).toEqual([]);
});
