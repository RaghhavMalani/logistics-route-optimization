// The buyer flow on the deployed product, at the three operating resolutions:
//
//   node qa/buyer-flow-deploy.mjs https://india-portwatch.vercel.app ../docs/qa/deploy
//
// A clean browser context per resolution. Signs in through the form as
// National Command, then walks: National Command, the Global Eye (map ready,
// the attention queue, the Spatial Copilot's first suggestion, a vessel
// decision if the register has something to decide about), a port scenario
// and a cargo scenario (as the port authority, with a financial assumption
// entered on the port decision), a mission replay to the reveal, Signal
// Health. Every request that failed and the host it went to, every plain-http
// request, every console and page error, and what the status strip said, go
// into report-buyer-flow.json beside the screenshots. The script reports; it
// does not decide.
import { chromium } from "@playwright/test";
import fs from "node:fs";

const BASE = (process.argv[2] ?? "https://india-portwatch.vercel.app").replace(/\/$/, "");
const OUT = process.argv[3] ?? "../docs/qa/deploy";
const SIZES = (process.argv[4] ?? "1920x1080,1440x900,1366x768")
  .split(",")
  .map((s) => s.split("x").map(Number));
const PORT = "INNSA";
fs.mkdirSync(OUT, { recursive: true });

const PORT_USER = {
  id: "demo-port",
  email: "port@portwatch.demo",
  displayName: "S. Iyer",
  role: "PORT_AUTHORITY",
  organisation: "Port Authority — Control Room (demo)",
  portCode: PORT,
  companyId: null,
  vesselIds: [],
};

const browser = await chromium.launch();
const report = { base: BASE, at: new Date().toISOString(), sizes: {} };
const settle = (page, ms = 2500) => page.waitForTimeout(ms);

async function strip(page) {
  return page.evaluate(() => {
    const text = document.body.innerText;
    const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
    const find = (re) => lines.find((l) => re.test(l)) ?? null;
    return {
      mode: find(/^MODE\b/) ?? find(/\bDEMO\b/),
      traffic: find(/SIMULATED|LIVE AIS|AIS STALE/i),
      twin: find(/^TWIN\b/),
      world: find(/^WORLD\b/),
      feedDown: /Feed down|FEED DOWN/i.test(text),
    };
  });
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

for (const [width, height] of SIZES) {
  const tag = `${width}x${height}`;
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const failed = [];
  const mixed = [];
  const consoleErrors = [];
  const pageErrors = [];
  const apiHosts = new Set();
  const localhostRequests = [];
  page.on("requestfailed", (r) => failed.push({ url: r.url(), error: r.failure()?.errorText ?? "?" }));
  page.on("response", (r) => {
    if (r.status() >= 400) failed.push({ url: r.url(), error: `HTTP ${r.status()}` });
  });
  page.on("request", (r) => {
    const url = r.url();
    if (url.startsWith("http://")) mixed.push(url);
    if (/localhost|127\.0\.0\.1/.test(url)) localhostRequests.push(url);
    if (/\/api\//.test(url)) apiHosts.add(new URL(url).host);
  });
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text().slice(0, 300));
  });
  page.on("pageerror", (e) => pageErrors.push(String(e.message).slice(0, 300)));

  const steps = {};
  const shots = {};
  const shot = async (name) => {
    const file = `${OUT}/${name}-${tag}.png`;
    await page.screenshot({ path: file });
    shots[name] = file;
  };
  const step = async (name, fn) => {
    try {
      steps[name] = (await fn()) ?? "ok";
    } catch (error) {
      steps[name] = `FAILED: ${String(error.message ?? error).split("\n")[0].slice(0, 200)}`;
    }
  };

  // sign in through the form ---------------------------------------------------
  await step("login", async () => {
    await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
    await settle(page);
    await page.getByRole("button", { name: /admin@portwatch\.demo/ }).click();
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL(/\/admin\//, { timeout: 30_000 });
    return page.url();
  });

  // National Command ------------------------------------------------------------
  await step("nationalCommand", async () => {
    await page.goto(`${BASE}/admin/radar`, { waitUntil: "domcontentloaded" });
    await settle(page, 5000);
    await shot("10-national-command");
    const s = await strip(page);
    if (s.feedDown) throw new Error("FEED DOWN on National Command");
    return s;
  });

  // Global Eye: map, attention, copilot, a vessel decision if any -----------------
  await step("globalEye", async () => {
    await page.goto(`${BASE}/admin/global-eye`, { waitUntil: "domcontentloaded" });
    await mapReady(page);
    await settle(page, 4000);
    await shot("11-global-eye");
    const s = await strip(page);
    if (s.feedDown) throw new Error("FEED DOWN on the Global Eye");
    const layers = await page.evaluate(() => window.__portwatchMap?.getStyle()?.layers?.length ?? 0);
    return { ...s, mapLayers: layers };
  });
  await step("attention", async () => {
    const text = await page.evaluate(() => document.body.innerText);
    const rows = await page.locator('[data-testid="cascade-row"]').count();
    const decide = await page.locator('[data-testid="decide-item"]').count();
    return { cascadeRows: rows, decideItems: decide, saysNothingToDecide: /nothing|no live|empty/i.test(text) };
  });
  await step("copilot", async () => {
    await page.getByTestId("command-bar-open").click();
    await page.getByTestId("command-suggestion").first().click();
    await page.getByTestId("command-answer").waitFor({ timeout: 30_000 });
    await settle(page, 1500);
    await shot("12-spatial-copilot");
    const applied = await page.getByTestId("command-applied").innerText().catch(() => "");
    const refused = await page.getByTestId("command-refused").innerText().catch(() => "");
    await page.keyboard.press("Escape");
    return { applied: applied.slice(0, 200), refused: refused.slice(0, 200) };
  });
  await step("vesselDecision", async () => {
    const decide = page.locator('[data-testid="decide-item"]');
    if (!(await decide.count())) return "no actionable hull in the register at this instant (nothing to decide; reported, not invented)";
    await decide.first().click();
    await page.waitForSelector('[data-testid="decision-panel"]', { timeout: 120_000 });
    await settle(page, 2500);
    await shot("13-vessel-decision");
    const kind = await page.locator('[data-testid="robust-headline"]').getAttribute("data-kind").catch(() => null);
    return { recommendation: kind };
  });
  await context.close();

  // the port authority: port scenario with a financial assumption, cargo --------
  const portContext = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
  await portContext.addInitScript(
    ([session, viewAs, port]) => {
      window.localStorage.setItem("portwatch.session.v1", session);
      window.localStorage.setItem("portwatch.viewAs.v1", viewAs);
      window.localStorage.setItem("portwatch.port.v1", port);
    },
    [
      JSON.stringify({
        user: PORT_USER,
        mode: "demo",
        issuedAt: new Date().toISOString(),
        expiresAt: new Date(Date.now() + 12 * 3600000).toISOString(),
      }),
      JSON.stringify("PORT_AUTHORITY"),
      JSON.stringify(PORT),
    ],
  );
  const port = await portContext.newPage();
  port.on("requestfailed", (r) => failed.push({ url: r.url(), error: r.failure()?.errorText ?? "?" }));
  port.on("response", (r) => {
    if (r.status() >= 400) failed.push({ url: r.url(), error: `HTTP ${r.status()}` });
  });
  port.on("request", (r) => {
    const url = r.url();
    if (url.startsWith("http://")) mixed.push(url);
    if (/localhost|127\.0\.0\.1/.test(url)) localhostRequests.push(url);
    if (/\/api\//.test(url)) apiHosts.add(new URL(url).host);
  });
  port.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text().slice(0, 300));
  });
  port.on("pageerror", (e) => pageErrors.push(String(e.message).slice(0, 300)));
  const pshot = async (name) => {
    const file = `${OUT}/${name}-${tag}.png`;
    await port.screenshot({ path: file });
    shots[name] = file;
  };

  await step("portDecision", async () => {
    await port.goto(`${BASE}/port/twin`, { waitUntil: "domcontentloaded" });
    await port.waitForSelector('[data-testid="port-decide"]', { timeout: 120_000 });
    await settle(port, 3000);
    const bunch = port.locator('[data-testid="port-bunch"]');
    if (await bunch.count()) await bunch.first().click();
    await port.locator('[data-testid="port-decide"]').first().click();
    await port.waitForSelector('[data-testid="decision-panel"]', { timeout: 120_000 });
    await settle(port, 2500);
    await pshot("14-port-decision");
    const rec = await port.locator('[data-testid="decision-panel"]').getAttribute("data-decision");
    return { decisionId: rec };
  });
  await step("financialAssumption", async () => {
    const money = port.locator('[data-testid="decision-panel"] button', { hasText: /^money$/i }).first();
    if (!(await money.count())) return "no Money tab on this decision";
    await money.click();
    await port.waitForSelector('[data-testid="financial-evidence"]', { timeout: 20_000 });
    const form = port.locator('[data-testid="assumption-form"]');
    if (!(await form.count())) return "no assumption form on this decision";
    for (const [id, value] of [["charter", 28000], ["bunker", 610], ["burn", 95], ["grt", 52000]]) {
      const field = port.locator(`[data-testid="assume-${id}"]`);
      if (await field.count()) await field.fill(String(value));
    }
    const before = await port.locator('[data-testid="decision-panel"]').getAttribute("data-decision");
    await port.locator('[data-testid="assume-submit"]').click();
    await port.waitForFunction(
      (prev) => document.querySelector('[data-testid="decision-panel"]')?.getAttribute("data-decision") !== prev,
      before,
      { timeout: 120_000 },
    );
    await settle(port, 1500);
    await pshot("15-financial-assumption");
    return "the priced decision recomputed";
  });
  await step("cargoDecision", async () => {
    await port.goto(`${BASE}/port/cargo`, { waitUntil: "domcontentloaded" });
    await port.waitForSelector('[data-testid="cargo-decide"]', { timeout: 120_000 });
    await settle(port, 1500);
    await port.locator('[data-testid="cargo-decide"]').click();
    await port.waitForSelector('[data-testid="decision-panel"]', { timeout: 120_000 });
    await settle(port, 2000);
    await pshot("16-cargo-decision");
  });
  await portContext.close();

  // National Command again: missions and signal health --------------------------
  const adminContext = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
  const admin = await adminContext.newPage();
  admin.on("requestfailed", (r) => failed.push({ url: r.url(), error: r.failure()?.errorText ?? "?" }));
  admin.on("response", (r) => {
    if (r.status() >= 400) failed.push({ url: r.url(), error: `HTTP ${r.status()}` });
  });
  admin.on("request", (r) => {
    const url = r.url();
    if (url.startsWith("http://")) mixed.push(url);
    if (/localhost|127\.0\.0\.1/.test(url)) localhostRequests.push(url);
    if (/\/api\//.test(url)) apiHosts.add(new URL(url).host);
  });
  admin.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text().slice(0, 300));
  });
  admin.on("pageerror", (e) => pageErrors.push(String(e.message).slice(0, 300)));
  const ashot = async (name) => {
    const file = `${OUT}/${name}-${tag}.png`;
    await admin.screenshot({ path: file });
    shots[name] = file;
  };
  await step("loginAgain", async () => {
    await admin.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
    await settle(admin);
    await admin.getByRole("button", { name: /admin@portwatch\.demo/ }).click();
    await admin.getByRole("button", { name: "Sign in" }).click();
    await admin.waitForURL(/\/admin\//, { timeout: 30_000 });
  });
  await step("mission", async () => {
    await admin.goto(`${BASE}/admin/missions`, { waitUntil: "domcontentloaded" });
    await admin.waitForSelector('[data-testid="mission-decide"]', { timeout: 120_000 });
    await settle(admin, 2500);
    await admin.locator('[data-testid="mission-decide"]').first().click();
    await admin.waitForSelector('[data-testid="mission-decision"]', { timeout: 120_000 });
    await settle(admin, 2000);
    await admin.locator('[data-testid="mission-choose"]').click();
    await admin.waitForFunction(() => /Chosen:/.test(document.body.innerText), undefined, { timeout: 30_000 });
    await admin.locator('[data-testid="mission-reveal"]').click();
    await admin.waitForSelector('[data-testid="mission-scorecard"]', { timeout: 120_000 });
    await settle(admin, 2000);
    await ashot("17-mission-reveal");
  });
  await step("signalHealth", async () => {
    await admin.goto(`${BASE}/admin/system`, { waitUntil: "domcontentloaded" });
    await admin.waitForSelector('[data-testid="freshness-row"]', { timeout: 60_000 });
    await settle(admin, 2000);
    await ashot("18-signal-health");
    const text = await admin.evaluate(() => document.body.innerText);
    return {
      mode: /DEMO/.test(text) ? "DEMO visible" : "DEMO not visible",
      traffic: /SIMULATED/i.test(text) ? "SIMULATED visible" : "SIMULATED not visible",
      strip: await strip(admin),
    };
  });
  await adminContext.close();

  report.sizes[tag] = {
    steps,
    apiHosts: [...apiHosts],
    failedRequests: failed,
    mixedContent: mixed,
    localhostRequests,
    consoleErrors,
    pageErrors,
    screenshots: shots,
  };
  console.log(`== ${tag}`);
  for (const [k, v] of Object.entries(steps)) console.log(`  ${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`);
  console.log(`  API hosts: ${[...apiHosts].join(", ")}`);
  console.log(
    `  failed requests: ${failed.length}; mixed content: ${mixed.length}; localhost requests: ${localhostRequests.length}; console errors: ${consoleErrors.length}; page errors: ${pageErrors.length}`,
  );
}

await browser.close();
fs.writeFileSync(`${OUT}/report-buyer-flow.json`, JSON.stringify(report, null, 2));
console.log(`report: ${OUT}/report-buyer-flow.json`);
