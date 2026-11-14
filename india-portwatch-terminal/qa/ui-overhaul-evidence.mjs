import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { chromium, expect } from "@playwright/test";

const [origin, sha, output, mode = "all"] = process.argv.slice(2);
if (!/^https:\/\/india-portwatch-[a-z0-9]+-flash2404s-projects\.vercel\.app$/.test(origin) ||
    !/^[a-f0-9]{40}$/.test(sha) || !output ||
    !["all", "screens", "story", "research", "twin-weather"].includes(mode)) {
  throw new Error("Pass the isolated preview origin, full SHA, evidence directory and optional mode.");
}
const health = await fetch(origin + "/api/health").then((response) => response.json());
assert.equal(health.release?.sha, sha);
assert.equal(health.service?.status, "ok");

const browser = await chromium.launch(mode === "twin-weather" ? {
  headless: false,
  args: process.platform === "win32" ? ["--use-angle=d3d11", "--disable-software-rasterizer"] : [],
} : {});
const reports = [];
const sizes = [[1024, 768], [1366, 768], [1440, 900], [1280, 720]];
const screens = [
  ["login", null, "/login"],
  ["company", "Company", "/company/overview"],
  ["port", "Port", "/port/overview"],
  ["vessel", "Vessel", "/vessel/overview"],
  ["admin", "Admin", "/admin/radar"],
  ["twin", "Port", "/port/twin"],
  ["research", null, "/research"],
];

function watch(page, report) {
  page.on("pageerror", (error) => report.errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") report.errors.push(message.text());
  });
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith("/api/") && response.status() >= 400) {
      report.errors.push(`${response.status()} ${url.pathname}`);
    }
  });
}

async function checkMap(page, name, report) {
  const labels = page.locator("[data-map-port-label]");
  if (name !== "vessel") await expect(labels.first()).toBeVisible({ timeout: 25_000 });
  report.labels = await labels.evaluateAll((nodes) => nodes.map((label) => {
    const { left, top, width, height } = label.getBoundingClientRect();
    const hit = document.elementFromPoint(left + width / 2, top + height / 2);
    return { name: label.textContent.trim(), visible: label.contains(hit) };
  }));
  assert(report.labels.every((label) => label.visible), `${name} contains a covered label`);
}

async function screenShot(width, height, [name, role, path]) {
  const context = await browser.newContext({ viewport: { width, height } });
  const report = { name, width, height, errors: [] };
  reports.push(report);
  try {
    const page = await context.newPage();
    watch(page, report);
    await page.goto(origin + "/login");
    await expect(page.getByText("Reachable", { exact: true })).toBeVisible({ timeout: 25_000 });
    if (role) {
      await page.getByRole("button", { name: role + " demo", exact: true }).click();
      await page.waitForURL("**" + (name === "twin" ? "/port/overview" : path));
      await expect(page.getByTestId("live-pulse")).toBeVisible();
    }
    if (name === "twin") {
      await page.goto(origin + path);
      await page.getByRole("button", { name: "Compare policies" }).click();
      const pane = page.getByTestId("twin-pane-baseline");
      await expect(pane.locator("canvas")).toBeVisible({ timeout: 25_000 });
      await expect(page.getByTestId("twin-pane-lookahead").locator("canvas")).toBeVisible();
      const position = page.getByTestId("twin-simulation-hour");
      const initial = await position.textContent();
      await expect(page.getByRole("button", { name: "×60" })).toHaveAttribute("aria-pressed", "true");
      await expect(position).not.toHaveText(initial ?? "");
      const metrics = page.getByTestId("twin-metrics-baseline");
      await expect.poll(() => metrics.getAttribute("data-hour")).not.toBe("0");
      report.height = height;
      report.paneRatio = (await pane.boundingBox()).height / height;
      assert(report.paneRatio >= 0.65, `Split pane uses ${report.paneRatio} of viewport`);
      const divider = page.getByRole("separator", { name: "Resize policy comparison panes" });
      const original = await pane.boundingBox();
      const handle = await divider.boundingBox();
      await page.mouse.move(handle.x + handle.width / 2, handle.y + 100);
      await page.mouse.down();
      await page.mouse.move(handle.x + handle.width / 2 + 45, handle.y + 100);
      await page.mouse.up();
      assert((await pane.boundingBox()).width > original.width + 20);
      await divider.focus();
      await divider.press("ArrowLeft");
      await page.getByRole("button", { name: "Pause simulation" }).click();
      await page.getByRole("heading", { name: /Digital Twin/ }).scrollIntoViewIfNeeded();
    } else if (name === "research") {
      await page.goto(origin + path);
      await expect(page.getByRole("region", { name: "Decision policy benchmark" })).toBeVisible();
      if (mode !== "research") {
        const findings = page.getByRole("region", { name: "What the study found" });
        await expect(findings.getByText("SYNTHETIC CORPUS", { exact: true })).toHaveCount(3);
        await expect(findings.getByText(/0 choices changed/)).toBeVisible();
        const pdf = await context.request.get(origin + "/portwatch-study.pdf");
        assert.equal(pdf.status(), 200);
        assert.equal((await pdf.body()).subarray(0, 5).toString(), "%PDF-");
        await findings.scrollIntoViewIfNeeded();
      }
    } else if (role) {
      await checkMap(page, name, report);
    }
    await page.screenshot({ path: join(output, `${width}x${height}-${name}.png`) });
    if (role && name !== "twin") {
      await page.keyboard.press("Control+k");
      const palette = page.getByRole("dialog", { name: "Command palette" });
      await expect(palette).toBeVisible();
      await palette.getByRole("combobox").fill("KDL");
      const result = palette.getByRole("option", { name: /Kandla|Deendayal/i }).first();
      await expect(result).toBeVisible();
      await page.keyboard.press("Enter");
      const kdl = page.locator("[data-map-port-label]").filter({ hasText: /KDL|Kandla|Deendayal/i });
      await expect(kdl.first()).toBeVisible({ timeout: 15_000 });
      await page.waitForURL(/port=INIXY/);
      await expect(kdl.filter({ hasText: "schematic" }).first()).toBeVisible({ timeout: 20_000 });
      const chart = {};
      await checkMap(page, name + " KDL", chart);
      report.focusedLabels = chart.labels;
      await page.screenshot({ path: join(output, `${width}x${height}-${name}-kdl.png`) });
    }
    console.log(`${width}×${height} ${name}`, JSON.stringify(report));
  } finally {
    await context.close();
  }
}

async function story() {
  const report = { name: "story", errors: [], beats: [] };
  reports.push(report);
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
    recordVideo: { dir: output, size: { width: 1366, height: 768 } },
  });
  const page = await context.newPage();
  const video = page.video();
  watch(page, report);
  const start = Date.now();
  const steps = [
    "Calculate S10", "Approve 10 kn", "Review proposal", "Approve and issue to vessel",
    "Acknowledge receipt", "Accept advisory", "Run simulated outcome", "Open Research benchmark",
  ];
  try {
    await page.goto(origin + "/login");
    await page.getByRole("button", { name: "Start the 3-minute demo" }).click();
    const coach = page.getByTestId("story-coach");
    for (const [index, action] of steps.entries()) {
      const button = coach.getByRole("button", { name: action, exact: true });
      await expect(button).toBeVisible({ timeout: 25_000 });
      if (index === 4) {
        await page.reload();
        await expect(button).toBeVisible({ timeout: 25_000 });
        report.resumedAfterReload = true;
      }
      report.beats.push({ action, second: Math.round((Date.now() - start) / 1000) });
      await page.waitForTimeout(3_500);
      await button.click();
    }
    await expect(coach.getByRole("heading", { name: "Passage review complete" })).toBeVisible({ timeout: 25_000 });
    await expect(page.getByRole("region", { name: "Decision policy benchmark" })).toBeVisible();
    await page.waitForTimeout(Math.max(4000, 60_000 - (Date.now() - start)));
    report.seconds = Math.round((Date.now() - start) / 1000);
    console.log("Story", JSON.stringify(report));
  } finally {
    await context.close();
    await video.saveAs(join(output, "story-mode.webm"));
    await video.delete();
  }
}

async function measureTwin({ record = false, suppressWeather = false } = {}) {
  const report = { name: "twin-weather", record, suppressWeather, errors: [] };
  reports.push(report);
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
    ...(record ? { recordVideo: { dir: output, size: { width: 1366, height: 768 } } } : {}),
  });
  if (suppressWeather) {
    await context.route("**/api/intelligence/current?*", async (route) => {
      const url = new URL(route.request().url());
      if (url.searchParams.get("view") !== "provider") return route.continue();
      const response = await route.fetch();
      const data = await response.json();
      data.sources.surface.status = "STALE";
      await route.fulfill({ response, json: data });
    });
  }
  const page = await context.newPage();
  const video = page.video();
  watch(page, report);
  try {
    await page.goto(origin + "/login");
    await page.getByRole("button", { name: "Port demo", exact: true }).click();
    await page.waitForURL("**/port/overview");
    await page.goto(origin + "/port/twin");
    await expect(page.getByTestId("twin-weather-status")).toHaveText(suppressWeather
      ? /stale · effects off/ : /Current hourly forecast · Open-Meteo/, { timeout: 25_000 });
    await page.getByRole("button", { name: "Compare policies" }).click();
    const panes = page.getByTestId("port-twin-scene");
    const start = () => panes.evaluateAll((nodes) => nodes.map((node) => Number(node.dataset.frameCount)));
    await expect(panes).toHaveCount(2);
    await expect.poll(async () => (await start()).every((value) => value > 2)).toBe(true);
    await page.bringToFront();
    assert.equal(await page.evaluate(() => document.visibilityState), "visible");
    const before = await start();
    const at = performance.now();
    await page.waitForTimeout(5000);
    const after = await start();
    const elapsed = (performance.now() - at) / 1000;
    report.fps = after.map((frames, index) => (frames - before[index]) / elapsed);
    report.gpu = await panes.first().locator("canvas").evaluate((canvas) => {
      const gl = canvas.getContext("webgl2");
      const extension = gl?.getExtension("WEBGL_debug_renderer_info");
      return extension ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL) : null;
    });
    if (record) {
      await page.screenshot({ path: join(output, "1366x768-twin-current-weather.png") });
      await page.waitForTimeout(20_000);
    }
    console.log("Twin weather", JSON.stringify(report));
  } finally {
    await context.close();
    if (video) {
      await video.saveAs(join(output, "twin-current-weather.webm"));
      await video.delete();
    }
  }
}

try {
  await mkdir(output, { recursive: true });
  if (mode === "all" || mode === "screens" || mode === "research") {
    for (const [width, height] of sizes) {
      const selected = width === 1280 ? screens.filter(([name]) => name === "twin") : screens;
      for (const screen of mode === "research" ? selected.filter(([name]) => name === "research") : selected) {
        await screenShot(width, height, screen);
      }
    }
  }
  if (mode === "all" || mode === "story") await story();
  if (mode === "twin-weather") {
    await measureTwin();
    await measureTwin({ suppressWeather: true });
    await measureTwin({ record: true });
    assert(reports.slice(0, 2).every((report) => report.fps.every((fps) => fps >= 50)), "Twin rendered under 50 fps");
  }
  assert(reports.every((report) => report.errors.length === 0), "Browser or API errors in evidence");
} finally {
  await writeFile(join(output, `receipt-${mode}.json`), JSON.stringify({ origin, sha, reports }, null, 2));
  await browser.close();
}
