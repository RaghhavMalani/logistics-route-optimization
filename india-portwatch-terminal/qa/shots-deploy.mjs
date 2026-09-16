// The deployed terminal, checked as a visitor sees it, at the three operating
// resolutions:
//
//   node qa/shots-deploy.mjs https://india-portwatch.vercel.app ../docs/qa/deploy
//
// For each resolution: the landing page, the sign-in (the demo roster, a real
// click on "Sign in"), National Command, the Global Eye, Signal Health, and a
// direct load of a deep route (a refresh, not a client-side navigation). It
// records every request that failed and the host it went to, every request
// made over plain http from the https page (mixed content), every console
// error and every page error, and writes a JSON report beside the
// screenshots. It does not decide whether the API is up -- it reports what the
// status strip said and where the API calls went, so the report is as true
// with the API host still to be provisioned as it is with it running.
import { chromium } from "@playwright/test";
import fs from "node:fs";

const BASE = (process.argv[2] ?? "https://india-portwatch.vercel.app").replace(/\/$/, "");
const OUT = process.argv[3] ?? "../docs/qa/deploy";
const SIZES = (process.argv[4] ?? "1920x1080,1440x900,1366x768")
  .split(",")
  .map((s) => s.split("x").map(Number));
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const report = { base: BASE, at: new Date().toISOString(), sizes: {} };

const settle = (page, ms = 2500) => page.waitForTimeout(ms);

async function stripText(page) {
  const text = await page.evaluate(() => document.body.innerText);
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const pick = (re) => lines.find((l) => re.test(l)) ?? null;
  return {
    apiState: pick(/API down|API (un)?reachable|Data service|UNREACHABLE|DEGRADED|READY/i),
    mode: pick(/^(DEMO|RESEARCH|COMMERCIAL|GOVERNMENT)\b/),
    traffic: pick(/SIMULATED|LIVE AIS|AIS STALE/i),
  };
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
  page.on("requestfailed", (r) => failed.push({ url: r.url(), error: r.failure()?.errorText ?? "?" }));
  page.on("response", (r) => {
    if (r.status() >= 400) failed.push({ url: r.url(), error: `HTTP ${r.status()}` });
  });
  page.on("request", (r) => {
    const url = r.url();
    if (url.startsWith("http://")) mixed.push(url);
    if (/\/api\//.test(url)) apiHosts.add(new URL(url).host);
  });
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text().slice(0, 300));
  });
  page.on("pageerror", (e) => pageErrors.push(String(e.message).slice(0, 300)));

  const shots = {};
  const shot = async (name) => {
    const file = `${OUT}/${name}-${tag}.png`;
    await page.screenshot({ path: file });
    shots[name] = file;
  };

  // 1. the landing page -----------------------------------------------------
  const landing = await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });
  await settle(page);
  const landingType = landing?.headers()["content-type"] ?? "";
  await shot("01-landing");

  // 2. sign in through the form ---------------------------------------------
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await settle(page);
  await page.getByRole("button", { name: /admin@portwatch\.demo/ }).click();
  await shot("02-sign-in");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/admin\//, { timeout: 30_000 }).catch(() => {});
  await settle(page, 4000);
  const afterLogin = page.url();

  // 3. National Command -----------------------------------------------------
  await page.goto(`${BASE}/admin/radar`, { waitUntil: "domcontentloaded" });
  await settle(page, 4000);
  await shot("03-national-command");
  const radarStrip = await stripText(page);

  // 4. the Global Eye ----------------------------------------------------------
  await page.goto(`${BASE}/admin/global-eye`, { waitUntil: "domcontentloaded" });
  await settle(page, 6000);
  await shot("04-global-eye");

  // 5. Signal Health ----------------------------------------------------------
  await page.goto(`${BASE}/admin/system`, { waitUntil: "domcontentloaded" });
  await settle(page, 3000);
  await shot("05-signal-health");
  const systemStrip = await stripText(page);

  // 6. a direct load of a deep route, as a refresh does -----------------------
  const deep = await page.goto(`${BASE}/admin/missions`, { waitUntil: "domcontentloaded" });
  await settle(page, 3000);
  await shot("06-direct-route");

  report.sizes[tag] = {
    landing: { status: landing?.status(), contentType: landingType },
    afterLogin,
    deepRouteStatus: deep?.status(),
    strip: { nationalCommand: radarStrip, signalHealth: systemStrip },
    apiHosts: [...apiHosts],
    failedRequests: failed,
    mixedContent: mixed,
    consoleErrors,
    pageErrors,
    screenshots: shots,
  };
  console.log(`== ${tag}`);
  console.log(`  landing ${landing?.status()} ${landingType}`);
  console.log(`  after sign-in: ${afterLogin}`);
  console.log(`  API calls went to: ${[...apiHosts].join(", ") || "(none)"}`);
  console.log(`  failed requests: ${failed.length}; mixed content: ${mixed.length}; console errors: ${consoleErrors.length}; page errors: ${pageErrors.length}`);
  await context.close();
}

await browser.close();
fs.writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 2));
console.log(`report: ${OUT}/report.json`);
