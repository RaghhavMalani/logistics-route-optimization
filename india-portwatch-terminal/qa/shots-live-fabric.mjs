// Dev-only screenshots of the running dev servers (frontend :8080, backend :8000).
import { chromium } from "@playwright/test";
import fs from "node:fs";

const OUT = process.argv[2];
const MODE = process.argv[3] || "live";
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
const now = Date.now();
await context.addInitScript(([session, viewAs]) => {
  window.localStorage.setItem("portwatch.session.v1", session);
  window.localStorage.setItem("portwatch.viewAs.v1", viewAs);
}, [JSON.stringify({ user: { id: "demo-admin", email: "admin@portwatch.demo", displayName: "A. Deshmukh", role: "NATIONAL_ADMIN", organisation: "National Maritime Operations Centre", portCode: null, companyId: null, vesselIds: [] }, mode: "demo", issuedAt: new Date(now).toISOString(), expiresAt: new Date(now + 12 * 3600000).toISOString() }), JSON.stringify("NATIONAL_ADMIN")]);
const page = await context.newPage();
await page.goto("http://localhost:8080/admin/global-eye");
await page.waitForFunction(() => !/Restoring session|Checking session/i.test(document.body.innerText), undefined, { timeout: 60000 });
await page.waitForFunction(() => (window.__portwatchSources?.vessels?.features?.length ?? 0) > 0, undefined, { timeout: 90000 });
await page.waitForTimeout(3000);

const strip = await page.getByTestId("status-traffic").innerText();
console.log("strip:", strip.replace(/\n/g, " "));
await page.screenshot({ path: `${OUT}/01-${MODE}-global-eye.png` });

if (MODE !== "replay") {
  await page.waitForFunction(() => (window.__portwatchSources?.observed?.features?.length ?? 0) > 0, undefined, { timeout: 30000 });
  await page.evaluate(() => window.__portwatchMap.jumpTo({ center: [62, 16.5], zoom: 4.6 }));
  await page.waitForTimeout(1500);
  const hits = await page.evaluate(() => {
    const map = window.__portwatchMap;
    const f = window.__portwatchSources.observed.features.find((x) => x.properties.kind === "mark" && x.properties.id === "419001101");
    const p = map.project(f.geometry.coordinates);
    const canvas = map.getCanvas();
    const r = canvas.getBoundingClientRect();
    const hits = map.queryRenderedFeatures([p.x, p.y], { layers: ["observed-mark"] }).map((h) => h.properties.id);
    for (const t of ["mousedown", "mouseup", "click"]) canvas.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, clientX: r.left + p.x, clientY: r.top + p.y, button: 0 }));
    return hits;
  });
  console.log("hit:", hits);
  await page.waitForSelector('[data-testid="observed-inspector"]', { timeout: 10000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/02-${MODE}-observed-inspector.png` });
  console.log("inspector:", (await page.getByTestId("vessel-source").innerText()).replace(/\n/g, " "));
  await page.locator('[data-testid="observed-inspector"] button[aria-label="Close panel"]').click();
}

// Signal health, AIS row expanded.
await page.getByTestId("signal-health").click();
await page.locator('[data-testid="signal-row"][data-capability="ais"] button').first().click();
await page.waitForTimeout(600);
await page.screenshot({ path: `${OUT}/03-${MODE}-signal-health-ais.png` });
await page.locator('[data-testid="signal-row"][data-capability="marine"] button').first().click();
await page.waitForTimeout(400);
await page.screenshot({ path: `${OUT}/04-${MODE}-signal-health-marine.png` });
await page.getByRole("button", { name: "Close" }).first().click();

// The WEATHER lens with the sea.
await page.locator('[data-testid="lens-option"][data-lens="WEATHER"]').click();
await page.waitForFunction(() => (window.__portwatchSources?.seastate?.features?.length ?? 0) > 0, undefined, { timeout: 30000 });
await page.evaluate(() => window.__portwatchMap.jumpTo({ center: [66, 15], zoom: 4.2 }));
await page.waitForTimeout(2500);
await page.screenshot({ path: `${OUT}/05-${MODE}-weather-lens-sea.png` });
console.log("legend:", (await page.getByTestId("seastate-attribution").innerText()));

await browser.close();
