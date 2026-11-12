import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { chromium, expect } from "@playwright/test";

const [origin, sha, output, mode = "all"] = process.argv.slice(2);
if (!/^https:\/\/india-portwatch-[a-z0-9]+-flash2404s-projects\.vercel\.app$/.test(origin) ||
    !/^[a-f0-9]{40}$/.test(sha) || !output ||
    !["all", "screens", "story"].includes(mode)) {
  throw new Error("Pass the isolated preview origin, full SHA, evidence directory and optional mode.");
}
const health = await fetch(origin + "/api/health").then((response) => response.json());
assert.equal(health.release?.sha, sha);
assert.equal(health.service?.status, "ok");

const browser = await chromium.launch();
const reports = [];
const sizes = [[1024, 768], [1366, 768], [1440, 900], [1280, 720]];
const screens = [
  ["login", null, "/login"],
  ["company", "Company", "/company/overview"],
  ["port", "Port", "/port/overview"],
  ["vessel", "Vessel", "/vessel/overview"],
  ["admin", "Admin", "/admin/radar"],
  ["twin", "Port", "/port/twin"],
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
  await expect(labels.first()).toBeVisible({ timeout: 25_000 });
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
      assert(report.paneRatio >= 0.649, `Split pane uses ${report.paneRatio} of viewport`);
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
    } else if (role) {
      await checkMap(page, name, report);
    }
    await page.screenshot({ path: join(output, `${width}x${height}-${name}.png`) });
    if (width === 1366 && name === "port") {
      await page.keyboard.press("Control+k");
      const palette = page.getByRole("dialog", { name: "Command palette" });
      await expect(palette).toBeVisible();
      await palette.getByRole("combobox").fill("KDL");
      const result = palette.getByRole("option", { name: /Kandla|Deendayal/i }).first();
      await expect(result).toBeVisible();
      await result.click();
      const kdl = page.locator("[data-map-port-label]").filter({ hasText: /KDL|Kandla|Deendayal/i });
      await expect(kdl.first()).toBeVisible({ timeout: 15_000 });
      await checkMap(page, "port KDL", report);
      await page.screenshot({ path: join(output, "1366x768-port-kdl.png") });
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

try {
  await mkdir(output, { recursive: true });
  if (mode !== "story") {
    for (const [width, height] of sizes) {
      for (const screen of (width === 1280 ? screens.filter(([name]) => name === "twin") : screens)) {
        await screenShot(width, height, screen);
      }
    }
  }
  if (mode !== "screens") await story();
  assert(reports.every((report) => report.errors.length === 0), "Browser or API errors in evidence");
} finally {
  await writeFile(join(output, `receipt-${mode}.json`), JSON.stringify({ origin, sha, reports }, null, 2));
  await browser.close();
}
