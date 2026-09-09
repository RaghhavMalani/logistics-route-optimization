import { chromium } from "@playwright/test";

const ROLE_SESSION = {
  user: {
    id: "demo-admin", email: "admin@portwatch.demo", displayName: "A. Deshmukh",
    role: "ADMIN", organisation: "National Maritime Operations Centre", portCode: null,
  },
  mode: "demo",
  issuedAt: new Date().toISOString(),
  expiresAt: new Date(Date.now() + 12 * 3600000).toISOString(),
};

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await context.addInitScript((session) => {
  window.localStorage.setItem("portwatch.session.v1", JSON.stringify(session));
}, ROLE_SESSION);
const page = await context.newPage();
const logs = [];
page.on("console", (m) => logs.push(`${m.type()}: ${m.text().slice(0, 240)}`));
page.on("pageerror", (e) => logs.push(`pageerror: ${String(e).slice(0, 240)}`));
await page.goto("http://localhost:8080/admin/radar", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(6000);

const result = await page.evaluate(async () => {
  const m = window.__portwatchMap;
  if (!m) return { fatal: "map instance not exposed" };
  const events = [];
  for (const ev of ["load", "styledata", "sourcedata", "idle", "error"]) {
    m.on(ev, (e) => events.push(ev + (e && e.error ? `: ${e.error.message ?? e.error}` : "")));
  }
  await new Promise((r) => setTimeout(r, 3000));
  const canvas = m.getCanvas();
  const container = m.getContainer();
  m.triggerRepaint();
  await new Promise((r) => setTimeout(r, 800));
  const gl = m.painter?.context?.gl;
  let sample = null;
  if (gl) {
    const px = new Uint8Array(4);
    gl.readPixels(Math.floor(canvas.width / 2), Math.floor(canvas.height / 2), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    sample = Array.from(px);
  }
  const featureCounts = {};
  for (const id of ["land-fill", "port-mark", "wx-cells", "lane-line"]) {
    try { featureCounts[id] = m.queryRenderedFeatures({ layers: [id] }).length; } catch (e) { featureCounts[id] = String(e).slice(0, 60); }
  }
  return {
    loaded: m.loaded(),
    styleLoaded: m.isStyleLoaded(),
    sources: Object.keys(m.getStyle()?.sources ?? {}),
    events: [...new Set(events)].slice(0, 20),
    canvas: { w: canvas.width, h: canvas.height, cssW: canvas.clientWidth, cssH: canvas.clientHeight },
    container: { w: container.clientWidth, h: container.clientHeight },
    centrePixel: sample,
    featureCounts,
    zoom: m.getZoom(), centre: m.getCenter(),
  };
});

console.log(JSON.stringify({ result, logs: logs.slice(-14) }, null, 2));
await browser.close();
