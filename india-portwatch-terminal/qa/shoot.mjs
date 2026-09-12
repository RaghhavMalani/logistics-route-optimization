/**
 * Visual QA harness.
 *
 * Drives the running terminal at the three supported operating resolutions,
 * captures every route, and reports console errors, failed requests and any
 * horizontal page overflow. Screenshots are for a human to look at; the report
 * is what fails a review.
 *
 *   SHOT_OUT=... SHOT_ROLE=ADMIN SHOT_SIZES=1920x1080,1440x900,1366x768 \
 *   SHOT_ROUTES='{"radar":"/admin/radar"}' node qa/shoot.mjs
 */

import fs from "node:fs";
import { chromium } from "@playwright/test";

const BASE = process.env.SHOT_BASE ?? "http://localhost:8080";
const OUT = process.env.SHOT_OUT ?? "qa/shots";
const SIZES = (process.env.SHOT_SIZES ?? "1920x1080").split(",").map((s) => {
  const [w, h] = s.split("x").map(Number);
  return { w, h };
});
const ROUTES = JSON.parse(process.env.SHOT_ROUTES ?? '{"login":"/login"}');
const ROLE = process.env.SHOT_ROLE ?? null;
const SETTLE = Number(process.env.SHOT_SETTLE ?? 2200);

/**
 * The demo accounts, in the terminal's current role vocabulary.
 *
 * These drifted: the harness moved to NATIONAL_ADMIN / PORT_AUTHORITY /
 * SHIPPING_COMPANY while this file still seeded ADMIN and PORT_OPERATOR, so a
 * screenshot run silently bounced to the login screen and captured that
 * instead. Kept in step with `qa/harness.ts`.
 */
const DEMO_COMPANY_NAME = "PortWatch Demo Shipping";
const DEMO_COMPANY_ID = "portwatch-demo-shipping";

const ACCOUNTS = {
  NATIONAL_ADMIN: {
    id: "demo-admin",
    email: "admin@portwatch.demo",
    displayName: "A. Deshmukh",
    role: "NATIONAL_ADMIN",
    organisation: "National Maritime Operations Centre",
    portCode: null,
    companyId: null,
    vesselIds: [],
  },
  PORT_AUTHORITY: {
    id: "demo-port",
    email: "port@portwatch.demo",
    displayName: "S. Iyer",
    role: "PORT_AUTHORITY",
    organisation: "Chennai Port Authority — Control Room",
    portCode: "INMAA",
    companyId: null,
    vesselIds: [],
  },
  SHIPPING_COMPANY: {
    id: "demo-company",
    email: "company@portwatch.demo",
    displayName: "M. Fernandes",
    role: "SHIPPING_COMPANY",
    organisation: DEMO_COMPANY_NAME,
    portCode: null,
    companyId: DEMO_COMPANY_ID,
    vesselIds: [],
  },
  VESSEL_OPERATOR: {
    id: "demo-vessel",
    email: "vessel@portwatch.demo",
    displayName: "R. Nayar",
    role: "VESSEL_OPERATOR",
    organisation: DEMO_COMPANY_NAME,
    portCode: null,
    companyId: DEMO_COMPANY_ID,
    vesselIds: ["PWD-001"],
  },
};

function session(role) {
  const now = Date.now();
  return {
    user: ACCOUNTS[role],
    mode: "demo",
    issuedAt: new Date(now).toISOString(),
    expiresAt: new Date(now + 12 * 3600_000).toISOString(),
  };
}

fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const report = [];

for (const { w, h } of SIZES) {
  const context = await browser.newContext({
    viewport: { width: w, height: h },
    deviceScaleFactor: 1,
  });
  if (ROLE) {
    await context.addInitScript(
      ([key, value, viewKey, role]) => {
        window.localStorage.setItem(key, value);
        window.localStorage.setItem(viewKey, JSON.stringify(role));
      },
      ["portwatch.session.v1", JSON.stringify(session(ROLE)), "portwatch.viewAs.v1", ROLE],
    );
  }

  const page = await context.newPage();
  const errors = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text().slice(0, 260));
  });
  page.on("pageerror", (e) => errors.push(`pageerror: ${String(e).slice(0, 260)}`));
  page.on("requestfailed", (r) => {
    const text = r.failure()?.errorText ?? "";
    if (text.includes("ERR_ABORTED")) return;
    errors.push(`requestfailed: ${r.url()} ${text}`);
  });

  for (const [name, path] of Object.entries(ROUTES)) {
    errors.length = 0;
    await page
      .goto(BASE + path, { waitUntil: "domcontentloaded", timeout: 45000 })
      .catch((e) => errors.push(`goto: ${e.message}`));
    // Hydration has to land before a screenshot means anything: the session
    // gate renders server-side and only resolves once effects run.
    await page
      .waitForFunction(
        () => !/Restoring session|Checking session/i.test(document.body.innerText),
        undefined,
        { timeout: 20000 },
      )
      .catch(() => errors.push("hydration: session gate never resolved"));
    await page.waitForTimeout(SETTLE);
    await page.screenshot({ path: `${OUT}/${name}-${w}x${h}.png` });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    report.push({
      route: path,
      size: `${w}x${h}`,
      url: page.url().replace(BASE, ""),
      overflowPx: overflow,
      errors: [...errors],
    });
  }
  await context.close();
}

await browser.close();
fs.writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 2));

const bad = report.filter((r) => r.errors.length > 0 || r.overflowPx > 0);
console.log(JSON.stringify(bad.length ? bad : { ok: report.length }, null, 2));
