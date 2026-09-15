// Screenshots of the robust recommendation on the running dev servers
// (frontend :8080, backend :8000): the headline (keep / wait / act, why,
// duration confidence, window, next observation, robustness) and the Robust
// tab (regret by stress horizon, the three picks, break-evens, the gate).
//
//   node qa/shots-robust.mjs ../docs/qa/robust [1920x1080,1440x900,1366x768]
//
// Prints what the panel says so the run is a check as well as a picture: the
// headline must carry a kind, the table must hold the current plan, and the
// break-even must be a sentence about closure length, not a score.
import { chromium } from "@playwright/test";
import fs from "node:fs";

const OUT = process.argv[2] ?? "../docs/qa/robust";
const SIZES = (process.argv[3] ?? "1920x1080,1440x900,1366x768")
  .split(",")
  .map((s) => s.split("x").map(Number));
const BASE = process.env.PW_BASE ?? "http://127.0.0.1:8080";
fs.mkdirSync(OUT, { recursive: true });

const USER = {
  id: "demo-admin",
  email: "admin@portwatch.demo",
  displayName: "A. Deshmukh",
  role: "NATIONAL_ADMIN",
  organisation: "National Maritime Operations Centre",
  portCode: null,
  companyId: null,
  vesselIds: [],
};

const browser = await chromium.launch();
const findings = [];

async function open(path, [width, height]) {
  const context = await browser.newContext({ viewport: { width, height } });
  const now = Date.now();
  await context.addInitScript(
    ([session, viewAs]) => {
      window.localStorage.setItem("portwatch.session.v1", session);
      window.localStorage.setItem("portwatch.viewAs.v1", viewAs);
    },
    [
      JSON.stringify({
        user: USER,
        mode: "demo",
        issuedAt: new Date(now).toISOString(),
        expiresAt: new Date(now + 12 * 3600000).toISOString(),
      }),
      JSON.stringify("NATIONAL_ADMIN"),
    ],
  );
  const page = await context.newPage();
  page.on("pageerror", (error) => findings.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error")
      findings.push(`console error: ${message.text()}`);
  });
  await page.goto(`${BASE}${path}`);
  await page.waitForFunction(
    () => !/Restoring session|Checking session/i.test(document.body.innerText),
    undefined,
    { timeout: 60000 },
  );
  return { context, page };
}

async function mapReady(page) {
  await page.waitForFunction(
    () =>
      window.__portwatchMap &&
      window.__portwatchMap.isStyleLoaded !== undefined &&
      !/INITIALISING CHART/.test(document.body.innerText),
    undefined,
    { timeout: 180000 },
  );
}

for (const size of SIZES) {
  const tag = `${size[0]}x${size[1]}`;
  console.log(`== ${tag}`);
  const { context, page } = await open("/admin/global-eye", size);
  await mapReady(page);
  await page.waitForSelector('[data-testid="decide-item"]', { timeout: 60000 });
  // Every actionable hull, so the run shows a KEEP and, where the register
  // offers one, a WAIT.
  const items = page.locator('[data-testid="decide-item"]');
  const count = Math.min(await items.count(), 4);
  for (let index = 0; index < count; index += 1) {
    await items.nth(index).click();
    await page.waitForSelector('[data-testid="robust-headline"]', {
      timeout: 90000,
    });
    await page.waitForTimeout(1800);
    const headline = page.locator('[data-testid="robust-headline"]');
    const kind = await headline.getAttribute("data-kind");
    const why = await page
      .locator('[data-testid="robust-why"]')
      .innerText()
      .catch(() => "");
    const wins = await page
      .locator('[data-testid="robust-wins"]')
      .innerText()
      .catch(() => "");
    const subject = await page
      .locator('[data-testid="decision-panel"]')
      .getAttribute("data-decision");
    console.log(`  ${index + 1}. ${subject} -> ${kind}`);
    console.log(`     why: ${why}`);
    console.log(`     robustness: ${wins}`);
    if (!kind) findings.push(`${subject}: the headline carries no kind`);
    if (index === 0) {
      await page.screenshot({ path: `${OUT}/01-robust-headline-${tag}.png` });
    }
    await page
      .locator('[data-testid="decision-panel"] button', {
        hasText: /^robust$/i,
      })
      .first()
      .click();
    await page.waitForSelector('[data-testid="robust-view"]', {
      timeout: 10000,
    });
    await page.waitForTimeout(600);
    const rows = await page.locator('[data-testid="robust-row"]').count();
    const breakEvens = await page
      .locator('[data-testid="break-even"]')
      .allInnerTexts();
    const checks = await page.locator('[data-testid="gate-check"]').count();
    console.log(`     table rows ${rows}, gate checks ${checks}`);
    for (const line of breakEvens) console.log(`     break-even: ${line}`);
    if (rows === 0) findings.push(`${subject}: the robust table is empty`);
    if (breakEvens.some((line) => /\d+\.\d+ score/i.test(line)))
      findings.push(`${subject}: a break-even reads as a score`);
    await page.screenshot({
      path: `${OUT}/02-robust-table-${index + 1}-${tag}.png`,
    });
    if (kind === "WAIT_FOR_MORE_INFORMATION") {
      await page.screenshot({ path: `${OUT}/03-wait-${tag}.png` });
    }
    await page
      .locator('[data-testid="decision-panel"] button', {
        hasText: /^options/i,
      })
      .first()
      .click();
    const close = page.locator('button[aria-label="Close decision"]');
    if (await close.count()) await close.click();
    await page.waitForTimeout(400);
  }
  await context.close();
}

await browser.close();
if (findings.length) {
  console.log("FINDINGS:");
  for (const line of findings) console.log("  - " + line);
  process.exit(1);
}
console.log("ok");
