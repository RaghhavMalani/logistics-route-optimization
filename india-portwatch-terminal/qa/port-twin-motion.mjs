import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium, expect } from "@playwright/test";

const [origin, directory] = process.argv.slice(2);
if (!origin || !directory)
  throw new Error(
    "Use node qa/port-twin-motion.mjs <origin> <output-directory> [--record]",
  );
const output = resolve(directory);
await mkdir(output, { recursive: true });
const recording = process.argv.includes("--record");
const browser = await chromium.launch({
  headless: false,
  args:
    process.platform === "win32"
      ? ["--use-angle=d3d11", "--disable-software-rasterizer"]
      : [],
});
const context = await browser.newContext({
  viewport: { width: 1366, height: 768 },
  ...(recording
    ? { recordVideo: { dir: output, size: { width: 1280, height: 720 } } }
    : {}),
});
const started = performance.now();
const page = await context.newPage();
const problems = [];
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("console", (entry) => {
  if (
    entry.type() === "error" &&
    !(
      process.argv.includes("--dev") && entry.text().includes("data-tsd-source")
    )
  )
    errors.push(entry.text());
});
page.on("response", (response) => {
  if (
    new URL(response.url()).pathname.includes("/api/") &&
    response.status() >= 400
  )
    problems.push(`${response.status()} ${new URL(response.url()).pathname}`);
});
const result = {
  origin,
  viewport: { width: 1366, height: 768 },
  errors,
  problems,
};
const scenes = page.getByTestId("port-twin-scene");
const toggle = page.getByTestId("twin-compare-toggle");
const transport = page.getByRole("region", {
  name: "Modelled simulation timeline",
});
const play = transport.getByRole("button", {
  name: "Play simulation",
  exact: true,
});
const pause = transport.getByRole("button", {
  name: "Pause simulation",
  exact: true,
});
const samples = () =>
  scenes.evaluateAll((elements) =>
    elements.map((element) => ({
      hour: Number(element.dataset.modelHour),
      calls: Number(element.dataset.drawCalls),
      frames: Number(element.dataset.frameCount),
      lowDetailBlocks: Number(element.dataset.lowDetailBlocks),
    })),
  );
const shot = (name) =>
  page.screenshot({ path: resolve(output, name + ".png") });

async function expectMetrics(lane, metrics) {
  const strip = page.getByTestId(`twin-metrics-${lane}`);
  await expect(strip).toHaveAttribute("data-hour", String(metrics.hour));
  await expect(strip.locator("dd")).toHaveText([
    metrics.meanWaitHours == null
      ? "—"
      : metrics.meanWaitHours.toFixed(1) + " h",
    metrics.meanTurnaroundHours == null
      ? "—"
      : metrics.meanTurnaroundHours.toFixed(1) + " h",
    String(metrics.missedDepartures),
  ]);
}

async function checkPick(snapshot) {
  const rect = await scenes.first().locator("canvas").boundingBox();
  const inspector = page.getByTestId("twin-inspector");
  const hits = new Set();
  const seen = new Set();
  for (const y of [0.61, 0.49, 0.45, 0.58, 0.66, 0.73, 0.37, 0.27]) {
    for (const x of [0.475, 0.463, 0.527, 0.563, 0.609, 0.66, 0.41, 0.378]) {
      await page.mouse.click(rect.x + rect.width * x, rect.y + rect.height * y);
      await page.evaluate(
        () => new Promise((done) => requestAnimationFrame(() => done())),
      );
      const label = (
        await inspector.locator(".panel-head > span").first().textContent()
      ).trim();
      seen.add(label);
      const berth = snapshot.berths.find((entry) => entry.name === label);
      const crane = snapshot.cranes.find((entry) => entry.name === label);
      const yard = snapshot.yardBlocks.find((entry) => entry.name === label);
      if (berth) {
        await expect(inspector).toContainText(berth.depth_m.toFixed(1) + " m");
        hits.add("berth");
      }
      if (crane) {
        await expect(inspector).toContainText(
          crane.moves_per_hour.toFixed(1) + " moves/h",
        );
        hits.add("crane");
      }
      if (yard) {
        await expect(inspector).toContainText(
          yard.capacityTeu.toLocaleString() + " TEU",
        );
        hits.add("yard");
      }
      if (hits.size >= 2) {
        await expect(
          inspector.getByTestId("twin-inspector-source"),
        ).toContainText("Port twin state");
        result.picked = [...hits];
        await shot("inspector");
        return;
      }
    }
  }
  throw new Error(
    "Ray-picking did not hit two known fixture object types. Picked " +
      [...seen].join(", "),
  );
}

try {
  await page.goto(origin + "/login");
  await page.getByRole("button", { name: "Port demo", exact: true }).click();
  await page.waitForURL("**/port/overview");
  const stateResponse = page.waitForResponse((response) =>
    /\/port-twin\/[^/?]+$/.test(new URL(response.url()).pathname),
  );
  await page.goto(origin + "/port/twin");
  await expect(scenes.first()).toBeVisible({ timeout: 45_000 });
  await expect.poll(async () => (await samples())[0]?.calls).toBeGreaterThan(0);
  const snapshot = await (await stateResponse).json();
  await expect(page.getByTestId("twin-schematic-banner")).toContainText(
    "modelled",
  );
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
    "No horizontal overflow",
  );
  if (!recording) {
    await shot("single");
    await checkPick(snapshot);
    for (const name of [
      "dwell",
      "workload",
      "queue",
      "storage",
      "utilisation",
    ]) {
      const button = page.getByTestId(`twin-overlay-${name}`);
      await button.click();
      await expect(button).toHaveAttribute("aria-pressed", "true");
    }
  }

  const compareResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith("/compare"),
  );
  await toggle.click();
  const comparison = await (await compareResponse).json();
  await expect(page.getByTestId("twin-comparison")).toBeVisible({
    timeout: 45_000,
  });
  await expect(scenes).toHaveCount(2);
  assert.equal(comparison.baseline.policy.policyId, "fcfs");
  assert.equal(comparison.lookahead.policy.policyId, "lookahead");
  assert.deepEqual(
    comparison.baseline.timeline.map((step) => step.hour),
    comparison.lookahead.timeline.map((step) => step.hour),
  );
  const expectedWinner =
    comparison.baseline.reward === comparison.lookahead.reward
      ? null
      : comparison.baseline.reward > comparison.lookahead.reward
        ? "fcfs"
        : "lookahead";
  assert.equal(comparison.winner, expectedWinner);
  await expect(page.getByTestId("twin-comparison-winner")).toContainText(
    expectedWinner === null
      ? "tie"
      : expectedWinner === "fcfs"
        ? "First come, first served wins"
        : "Constrained lookahead wins",
  );
  await expectMetrics("baseline", comparison.baseline.timeline[0].metrics);
  await expectMetrics("lookahead", comparison.lookahead.timeline[0].metrics);
  await page.getByTestId("twin-horizon-24").click();
  await expectMetrics("baseline", comparison.baseline.timeline.at(-1).metrics);
  await expectMetrics(
    "lookahead",
    comparison.lookahead.timeline.at(-1).metrics,
  );
  if (!recording) await shot("comparison-result");

  const scrubber = transport.getByRole("slider", { name: "Modelled hour" });
  await scrubber.press("Home");
  await expect(transport.getByTestId("twin-simulation-hour")).toHaveText(
    "+00:00",
  );
  await transport.getByRole("button", { name: "×10", exact: true }).click();
  await expect(
    transport.getByRole("button", { name: "×10", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await transport.getByRole("button", { name: "×60", exact: true }).click();
  await expect(
    transport.getByRole("button", { name: "×60", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");

  if (recording) {
    result.captureStart = (performance.now() - started) / 1000;
    result.video = await page.video().path();
    await page.waitForTimeout(1700);
    await play.click();
    await expect(play).toBeVisible({ timeout: 45_000 });
    await expect(transport.getByTestId("twin-simulation-hour")).toHaveText(
      "+24:00",
    );
    await page.waitForTimeout(4200);
    await shot("split-screen");
  } else {
    await play.click();
    await expect(pause).toBeVisible();
    await expect
      .poll(async () => (await samples())[0].hour)
      .toBeGreaterThan(0.5);
    const start = performance.now();
    const a = await samples();
    await page.waitForTimeout(4700);
    const b = await samples();
    const seconds = (performance.now() - start) / 1000;
    result.framesPerSecond = b.map(
      (side, index) => +((side.frames - a[index].frames) / seconds).toFixed(1),
    );
    assert(
      result.framesPerSecond.every((fps) => fps >= 50),
      JSON.stringify(result.framesPerSecond),
    );
    assert(
      Math.abs(b[0].hour - b[1].hour) <= 0.05,
      "Both panes use one simulation instant",
    );
    assert(
      b.every((side) => side.calls <= 11),
      "Each object type is rendered in one batch",
    );
    result.drawCalls = b.map((side) => side.calls);
    result.gpu = await scenes
      .first()
      .locator("canvas")
      .evaluate((canvas) => {
        const gl = canvas.getContext("webgl2");
        const ext = gl?.getExtension("WEBGL_debug_renderer_info");
        return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null;
      });
    await shot("comparison-playing");

    // Chromium's automation windows may remain reported as visible after a
    // tab switch. Exercise the same browser visibility event deterministically.
    await page.evaluate(() => {
      Object.defineProperty(document, "hidden", {
        configurable: true,
        value: true,
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    const hidden = await samples();
    await new Promise((done) => setTimeout(done, 800));
    assert.deepEqual(
      await samples(),
      hidden,
      "Hidden tab must hold the timeline and stop drawing",
    );
    result.hiddenPaused = "visibilitychange emulated";
    await page.evaluate(() => {
      delete document.hidden;
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await expect
      .poll(async () => (await samples())[0].frames)
      .toBeGreaterThan(hidden[0].frames);
    await pause.click();
    await page.waitForTimeout(120);
    const frozen = await samples();
    await page.waitForTimeout(450);
    assert.deepEqual(
      await samples(),
      frozen,
      "Paused model must hold its frame",
    );

    await scenes.first().locator("canvas").hover();
    for (let i = 0; i < 8; i++) {
      await page.mouse.wheel(0, 1300);
      await page.waitForTimeout(35);
    }
    await expect
      .poll(async () => (await samples())[0].lowDetailBlocks)
      .toBeGreaterThan(0);
    result.lowDetailBlocks = (await samples())[0].lowDetailBlocks;
    await shot("lod");
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(problems, []);
  console.log(JSON.stringify(result, null, 2));
} finally {
  await context.close();
  await browser.close();
  await writeFile(
    resolve(output, recording ? "capture.json" : "verification.json"),
    JSON.stringify(result, null, 2),
  );
}
