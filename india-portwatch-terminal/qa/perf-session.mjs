// Frontend performance: the production build against the real API, timed
// and then driven for fifteen minutes to see whether it leaks.
//
//   node qa/perf-session.mjs [--minutes 15] [--out ../docs/qa/perf]
//
// Needs the API on :8000 (python -m portwatch.demo start --no-terminal or the
// full stack) and the production build served on :4173 with the API base
// baked in:
//
//   VITE_PORTWATCH_API_BASE=http://127.0.0.1:8000/api NITRO_PRESET=node-server npm run build
//   node qa/serve-build.mjs   (PW_SKIP_BUILD=1)
//
// Headed Chromium by default: the WebGL chart renders in software in headless
// mode at a few frames a second, and every interaction timing below would be
// the renderer's, not the product's. PW_HEADLESS=1 forces headless for a
// memory-only run.
//
// Measures: navigation timing, script and total transfer, map first render,
// the latency of opening a decision, of a cascade play, of a scenario
// (option) switch and of a mission switch; then loops select event -> open
// decision -> switch option -> compare -> close, sampling JS heap, DOM nodes,
// map layers and sources every 30 s. Growth is the least-squares slope over
// the samples after warm-up, reported in MB per minute with the first and
// last readings. Writes a JSON report and prints it.
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : fallback;
};
const MINUTES = Number(flag("--minutes", "15"));
const OUT = flag("--out", "../docs/qa/perf");
const BASE = process.env.PW_BASE ?? "http://127.0.0.1:4173";
const HEADLESS = process.env.PW_HEADLESS === "1";
// --gc forces a garbage collection before every sample, so the heap figure
// is what the page retains rather than what the collector has not got to.
const FORCE_GC = args.includes("--gc");
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

const browser = await chromium.launch({
  headless: HEADLESS,
  args: ["--enable-precise-memory-info"],
});
const context = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
});
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
const client = await context.newCDPSession(page);
await client.send("Performance.enable");
await client.send("HeapProfiler.enable").catch(() => {});
const errors = [];
page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));

const report = {
  base: BASE,
  headless: HEADLESS,
  forcedGc: FORCE_GC,
  minutes: MINUTES,
  startedAt: new Date().toISOString(),
};

async function metrics() {
  if (FORCE_GC)
    await client.send("HeapProfiler.collectGarbage").catch(() => {});
  const { metrics: rows } = await client.send("Performance.getMetrics");
  const get = (name) => rows.find((m) => m.name === name)?.value ?? null;
  const page_ = await page.evaluate(() => ({
    domNodes: document.getElementsByTagName("*").length,
    mapLayers: window.__portwatchMap?.getStyle?.()?.layers?.length ?? null,
    mapSources: window.__portwatchMap
      ? Object.keys(window.__portwatchMap.getStyle?.()?.sources ?? {}).length
      : null,
    heapUsedMb: performance.memory
      ? performance.memory.usedJSHeapSize / 1048576
      : null,
  }));
  return {
    at: new Date().toISOString(),
    jsHeapUsedMb:
      get("JSHeapUsedSize") == null
        ? page_.heapUsedMb
        : get("JSHeapUsedSize") / 1048576,
    jsHeapTotalMb:
      get("JSHeapTotalSize") == null ? null : get("JSHeapTotalSize") / 1048576,
    documents: get("Documents"),
    nodes: get("Nodes"),
    listeners: get("JSEventListeners"),
    domNodes: page_.domNodes,
    mapLayers: page_.mapLayers,
    mapSources: page_.mapSources,
  };
}

async function mapReady() {
  await page.waitForFunction(
    () =>
      window.__portwatchMap &&
      window.__portwatchMap.isStyleLoaded !== undefined &&
      !/INITIALISING CHART/.test(document.body.innerText),
    undefined,
    { timeout: 120000 },
  );
}

const timed = async (label, fn) => {
  const t0 = performance.now();
  await fn();
  const ms = Math.round(performance.now() - t0);
  console.log(`  ${label.padEnd(36)} ${String(ms).padStart(6)} ms`);
  return ms;
};

// ------------------------------------------------------------- initial load --
console.log("== initial load (Global Eye)");
const navStart = performance.now();
await page.goto(`${BASE}/admin/global-eye`, { waitUntil: "load" });
report.loadMs = Math.round(performance.now() - navStart);
await page.waitForFunction(
  () => !/Restoring session|Checking session/i.test(document.body.innerText),
  undefined,
  { timeout: 60000 },
);
report.mapFirstRenderMs = await timed(
  "map first render (chart drawn)",
  mapReady,
);
const navigation = await page.evaluate(() => {
  const nav = performance.getEntriesByType("navigation")[0];
  const resources = performance.getEntriesByType("resource");
  const scripts = resources.filter(
    (r) => r.initiatorType === "script" || /\.m?js(\?|$)/.test(r.name),
  );
  const sum = (rows) =>
    rows.reduce((total, r) => total + (r.transferSize || 0), 0);
  const decoded = (rows) =>
    rows.reduce((total, r) => total + (r.decodedBodySize || 0), 0);
  return {
    ttfbMs: Math.round(nav.responseStart - nav.requestStart),
    domContentLoadedMs: Math.round(nav.domContentLoadedEventEnd),
    loadEventMs: Math.round(nav.loadEventEnd),
    scripts: scripts.length,
    scriptTransferKb: Math.round(sum(scripts) / 1024),
    scriptDecodedKb: Math.round(decoded(scripts) / 1024),
    resources: resources.length,
    totalTransferKb: Math.round(sum(resources) / 1024),
  };
});
Object.assign(report, navigation);
console.log(
  `  TTFB ${navigation.ttfbMs} ms · DOMContentLoaded ${navigation.domContentLoadedMs} ms · load ${navigation.loadEventMs} ms`,
);
console.log(
  `  scripts ${navigation.scripts} (${navigation.scriptTransferKb} KB transferred, ${navigation.scriptDecodedKb} KB decoded) · ${navigation.resources} resources, ${navigation.totalTransferKb} KB`,
);
report.baseline = await metrics();

// -------------------------------------------------------------- interactions --
console.log("== interactions");
await page.waitForSelector('[data-testid="decide-item"]', { timeout: 60000 });
report.openDecisionMs = await timed(
  "open a decision (click -> panel)",
  async () => {
    await page.locator('[data-testid="decide-item"]').first().click();
    await page.waitForSelector('[data-testid="decision-panel"]', {
      timeout: 90000,
    });
  },
);
report.switchOptionMs = await timed(
  "switch option (branch redraw)",
  async () => {
    const other = page.locator(
      '[data-testid="decision-option"][data-selected="false"]',
    );
    if ((await other.count()) > 0) {
      await other.last().click();
      await page.waitForFunction(
        () =>
          document.querySelector(
            '[data-testid="decision-option"][data-selected="true"]',
          ) !== null,
      );
    }
  },
);
report.robustTabMs = await timed("robust tab", async () => {
  await page
    .locator('[data-testid="decision-panel"] button', { hasText: /^robust$/i })
    .first()
    .click();
  await page.waitForSelector('[data-testid="robust-view"]', { timeout: 10000 });
});
const close = page.locator('button[aria-label="Close decision"]');
if (await close.count()) await close.click();
report.cascadePlayMs = await timed(
  "cascade play (button -> frames)",
  async () => {
    const play = page.locator('[data-testid="play-cascade"]');
    if (await play.count()) {
      await play.first().click();
      await page.waitForTimeout(2500);
      const reset = page.locator('[data-testid="reset-cascade"]');
      if (await reset.count()) await reset.first().click();
    }
  },
);
report.scenarioSwitchMs = await timed(
  "scenario screen (navigate)",
  async () => {
    await page.goto(`${BASE}/admin/scenarios`, { waitUntil: "load" });
    await page.waitForFunction(
      () => document.body.innerText.length > 500,
      undefined,
      { timeout: 60000 },
    );
  },
);
report.missionSwitchMs = await timed("mission screen + replay", async () => {
  await page.goto(`${BASE}/admin/missions`, { waitUntil: "load" });
  await page
    .waitForSelector(
      '[data-testid="mission-clock"], [data-testid="mission-switch"]',
      { timeout: 90000 },
    )
    .catch(() => {});
  const sw = page.locator('[data-testid="mission-switch"]');
  if ((await sw.count()) > 1) {
    await sw.nth(1).click();
    await page.waitForTimeout(1500);
  }
});

// ------------------------------------------------------------ 15-minute loop --
console.log(
  `== ${MINUTES}-minute session: select event -> open decision -> switch option -> compare -> close`,
);
await page.goto(`${BASE}/admin/global-eye`, { waitUntil: "load" });
await mapReady();
await page.waitForSelector('[data-testid="decide-item"]', { timeout: 60000 });
const samples = [];
const deadline = Date.now() + MINUTES * 60000;
let cycles = 0;
let lastSample = 0;
samples.push({ cycle: 0, ...(await metrics()) });
while (Date.now() < deadline) {
  const items = page.locator('[data-testid="decide-item"]');
  const count = await items.count();
  if (!count) break;
  try {
    const rows = page.locator('[data-testid="global-event-row"]');
    if ((await rows.count()) > 1)
      await rows.nth(cycles % (await rows.count())).click();
    await items.nth(cycles % count).click();
    await page.waitForSelector('[data-testid="decision-panel"]', {
      timeout: 90000,
    });
    const other = page.locator(
      '[data-testid="decision-option"][data-selected="false"]',
    );
    if ((await other.count()) > 0) await other.last().click();
    const compare = page.locator('[data-testid="decision-panel"] button', {
      hasText: /^compare$/i,
    });
    if (await compare.count()) {
      await compare.first().click();
      await page.waitForTimeout(300);
      await compare.first().click();
    }
    const closeButton = page.locator('button[aria-label="Close decision"]');
    if (await closeButton.count()) await closeButton.click();
    await page.waitForTimeout(400);
  } catch (error) {
    errors.push(`cycle ${cycles}: ${error.message.split("\n")[0]}`);
  }
  cycles += 1;
  if (Date.now() - lastSample > 30000) {
    lastSample = Date.now();
    const sample = { cycle: cycles, ...(await metrics()) };
    samples.push(sample);
    console.log(
      `  t+${Math.round((MINUTES * 60000 - (deadline - Date.now())) / 1000)
        .toString()
        .padStart(
          4,
        )} s  cycles ${String(cycles).padStart(4)}  heap ${sample.jsHeapUsedMb?.toFixed(1)} MB  nodes ${sample.nodes}  listeners ${sample.listeners}  layers ${sample.mapLayers}  sources ${sample.mapSources}`,
    );
  }
}
samples.push({ cycle: cycles, ...(await metrics()) });

// ---------------------------------------------------------------- growth --
function slope(rows, key) {
  const points = rows
    .map((r, i) => [i, r[key]])
    .filter(([, v]) => typeof v === "number");
  if (points.length < 3) return null;
  const n = points.length;
  const mx = points.reduce((t, [x]) => t + x, 0) / n,
    my = points.reduce((t, [, y]) => t + y, 0) / n;
  const num = points.reduce((t, [x, y]) => t + (x - mx) * (y - my), 0);
  const den = points.reduce((t, [x]) => t + (x - mx) ** 2, 0);
  return den ? num / den : 0;
}
const settled = samples.slice(Math.min(3, samples.length - 2)); // after warm-up
const intervalMin = settled.length > 1 ? 0.5 : 1;
report.session = {
  cycles,
  samples,
  heapFirstMb: samples[0].jsHeapUsedMb,
  heapLastMb: samples[samples.length - 1].jsHeapUsedMb,
  heapSlopeMbPerMinute:
    slope(settled, "jsHeapUsedMb") == null
      ? null
      : slope(settled, "jsHeapUsedMb") / intervalMin,
  nodesFirst: samples[0].nodes,
  nodesLast: samples[samples.length - 1].nodes,
  listenersFirst: samples[0].listeners,
  listenersLast: samples[samples.length - 1].listeners,
  mapLayersFirst: samples[0].mapLayers,
  mapLayersLast: samples[samples.length - 1].mapLayers,
  mapSourcesFirst: samples[0].mapSources,
  mapSourcesLast: samples[samples.length - 1].mapSources,
};
report.errors = errors;
report.finishedAt = new Date().toISOString();
fs.writeFileSync(
  path.join(OUT, "session.json"),
  JSON.stringify(report, null, 2),
);
console.log("== result");
console.log(
  `  cycles ${cycles}; heap ${report.session.heapFirstMb?.toFixed(1)} -> ${report.session.heapLastMb?.toFixed(1)} MB` +
    ` (slope ${report.session.heapSlopeMbPerMinute == null ? "n/a" : report.session.heapSlopeMbPerMinute.toFixed(2)} MB/min after warm-up);` +
    ` DOM nodes ${report.session.nodesFirst} -> ${report.session.nodesLast}; listeners ${report.session.listenersFirst} -> ${report.session.listenersLast};` +
    ` map layers ${report.session.mapLayersFirst} -> ${report.session.mapLayersLast}; sources ${report.session.mapSourcesFirst} -> ${report.session.mapSourcesLast}`,
);
if (errors.length)
  console.log(`  errors: ${errors.length} (first: ${errors[0]})`);
console.log(`wrote ${path.join(OUT, "session.json")}`);
await browser.close();
