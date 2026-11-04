import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium, expect } from "@playwright/test";

const replay = process.argv.includes("--replay");
const panelMode = process.argv.includes("--panel");
if (replay && panelMode) throw new Error("Choose the legacy replay smoke or the connected panel smoke.");
const offline = replay || panelMode;
const origin = process.env.PORTWATCH_PANEL_ORIGIN ?? (offline ? "http://127.0.0.1:4262" : "http://127.0.0.1:4263");
const api = process.env.PORTWATCH_PANEL_API ?? (offline ? "http://127.0.0.1:9297/api" : "http://127.0.0.1:9298/api");
const originUrl = new URL(origin);
const apiUrl = new URL(api);
const local = [originUrl, apiUrl].every((url) => ["127.0.0.1", "localhost"].includes(url.hostname));
if (offline && !local) throw new Error("The panel backend and frontend must both be local.");
if (process.argv.includes("preview") && local) throw new Error("Preview target needs a verified HTTPS origin.");
if (!local) {
  const sha = process.env.PORTWATCH_PANEL_EXPECTED_SHA;
  const previewHost = /^india-portwatch-[a-z0-9]+-flash2404s-projects[.]vercel[.]app$/;
  if (!sha || !/^[a-f0-9]{40}$/.test(sha) || originUrl.protocol !== "https:" ||
      !previewHost.test(originUrl.hostname) || apiUrl.origin !== originUrl.origin || apiUrl.pathname !== "/api") {
    throw new Error("Set an exact SHA and a same-origin API on a generated isolated preview.");
  }
  const health = await fetch(api + "/health").then((response) => response.json());
  const receiptPath = process.env.PORTWATCH_PANEL_BINDING;
  if (!receiptPath) throw new Error("Set PORTWATCH_PANEL_BINDING to the verified Vercel/Railway receipt.");
  const receipt = JSON.parse((await readFile(receiptPath, "utf8")).replace(/^\uFEFF/, ""));
  assert.equal(receipt.origin, origin);
  assert.equal(receipt.frontendSha, sha);
  assert.equal(receipt.backendSha, sha);
  assert.equal(health.artifact.applicationSha, sha);
  assert.equal(health.release.provider.serviceId, "c7dfe1db-2fd0-4c24-8a59-dde1d34239c2");
}
const browser = await chromium.launch({ headless: !process.argv.includes("--headed") });
const open = (page, path) => page.goto(origin + path, { waitUntil: "domcontentloaded" });

async function blockOutbound(context, blocked) {
  const localOrigins = new Set([originUrl.origin, apiUrl.origin]);
  await context.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (!["http:", "https:"].includes(url.protocol) || localOrigins.has(url.origin)) return route.continue();
    blocked.push(url.hostname);
    return route.abort("internetdisconnected");
  });
}

async function call(path, token, body, expected = 200) {
  const res = await fetch(api + path, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  assert.equal(res.status, expected, JSON.stringify(data));
  return data;
}

async function role(page, name) {
  await page.getByRole("button", { name: /Demo role/i }).click();
  const item = page.getByRole("menuitem", { name });
  await expect(item).toBeVisible();
  await Promise.all([
    page.waitForResponse((response) => response.url().endsWith("/demo/role") &&
      response.request().method() === "POST" && response.ok()),
    item.click(),
  ]);
}

async function run(width, height) {
  const videoDir = process.env.PORTWATCH_PANEL_VIDEO_DIR;
  const context = await browser.newContext({
    viewport: { width, height },
    reducedMotion: videoDir ? "no-preference" : "reduce",
    ...(panelMode ? { serviceWorkers: "block" } : {}),
    ...(videoDir ? { recordVideo: { dir: videoDir, size: { width: 1280, height: 720 } } } : {}),
  });
  const page = await context.newPage();
  page.setDefaultTimeout(35_000);
  const evidence = process.env.PORTWATCH_PANEL_EVIDENCE_DIR;
  let token;
  let beat = "Company";
  const checks = [];
  const errors = [];
  const results = { origin, width, height, checks, errors };
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const source = message.location().url;
    if (panelMode && source && ![originUrl.origin, apiUrl.origin].some((base) => source.startsWith(base + "/"))) return;
    errors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 400 && new URL(response.url()).pathname.startsWith("/api/")) {
      errors.push(`${response.status()} ${new URL(response.url()).pathname}`);
    }
  });
  page.on("requestfailed", (request) => {
    const failure = request.failure()?.errorText;
    if (new URL(request.url()).pathname.startsWith("/api/") && failure !== "net::ERR_ABORTED") {
      errors.push(`${failure} ${new URL(request.url()).pathname}`);
    }
  });
  const shot = async (name) => {
    if (videoDir) await page.waitForTimeout(1700);
    if (!evidence) return;
    await mkdir(evidence, { recursive: true });
    await page.screenshot({ path: join(evidence, `${width}-${name}.png`), timeout: 15_000 });
  };
  const passed = (next) => {
    checks.push({ beat, result: "PASS" });
    console.log(`PASS ${width}×${height} · ${beat}`);
    beat = next;
  };
  const postResponse = (suffix) => page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith(suffix) && response.request().method() === "POST");
  const read = async (pending) => {
    const response = await pending;
    if (!response.ok()) throw new Error(`${response.status()} ${await response.text()}`);
    return response.json();
  };
  async function approve(panel, choice, capturePrefix) {
    await panel.getByRole("button", { name: "Continue to Decide", exact: true }).click();
    await shot(`${capturePrefix}-decide`);
    const reviewing = postResponse("/transition");
    await panel.getByTestId("decision-review").click();
    await read(reviewing);
    await shot(`${capturePrefix}-reviewed`);
    const changed = postResponse("/transition");
    await panel.getByTestId("decision-approve").click();
    const result = await read(changed);
    assert.equal(result.humanChoice, choice);
    return result;
  }
  async function advisoryAction(card, state, id) {
    const changed = postResponse("/advisories/" + id + "/transition");
    await card.getByTestId("advisory-action-" + state).click();
    const result = await read(changed);
    assert.equal(result.state, state);
    assert.equal(result.advisoryId, id);
  }
  try {
    if (panelMode) {
      results.blockedOutbound = [];
      await blockOutbound(context, results.blockedOutbound);
      assert.equal((await call("/health")).worldClock.mode, "REPLAY");
    }
    if (evidence || videoDir) {
      await open(page, "/tour");
      await page.getByRole("list", { name: "Voyage chapters" }).waitFor();
      if (videoDir) {
        await page.locator(".pw-tour canvas").waitFor({ timeout: 15_000 });
        await page.getByRole("list", { name: "Voyage chapters" }).getByRole("button").nth(2).click();
        await page.waitForTimeout(1000);
        await page.evaluate(() => new Promise((resolve) => {
          const scroller = document.querySelector(".pw-tour .scroller");
          scroller.scrollTop = 0;
          const start = performance.now();
          const distance = (scroller.scrollHeight - scroller.clientHeight) * 0.4;
          const frame = (time) => {
            const fraction = Math.min(1, (time - start) / 8500);
            scroller.scrollTop = distance * fraction;
            if (fraction < 1) requestAnimationFrame(frame);
            else resolve();
          };
          requestAnimationFrame(frame);
        }));
      }
      await shot("00-tour");
    }
    await open(page, "/login");
    const login = postResponse("/demo/session");
    await page.getByRole("button", { name: "Company demo", exact: true }).click();
    token = (await read(login)).accessToken;
    await page.waitForURL("**/company/overview");
    const companyHandoffs = page.getByRole("region", { name: "Fleet handoffs" });
    await page.getByRole("button", { name: "Scenarios", exact: true }).click();
    const scenarios = page.getByTestId("demonstration-scenarios");
    await scenarios.getByLabel("Shipping demonstration scenario").selectOption("S10");
    await scenarios.getByRole("checkbox").check();
    const calculation = postResponse("/demonstrations/select");
    await scenarios.getByRole("button", { name: "Calculate selected demonstration" }).click();
    const scenario = await read(calculation);
    const problem = scenario.problem;
    assert(problem);
    if (panelMode) assert.equal(problem.evidence.currentEnvironment.scenario.panelReplay, true);
    const choice = problem.options.find((option) => option.status === "FEASIBLE" && /10(?:\.0)? kn/i.test(option.label));
    assert(choice);
    await expect(scenarios.getByRole("button", { name: "Show on map" })).toBeDisabled();
    await expect(scenarios.getByRole("button", { name: "Propose to port" })).toHaveCount(0);
    await expect(scenarios).not.toContainText(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
    await shot("00a-scenario");
    await page.getByRole("button", { name: "Fleet intelligence", exact: true }).click();
    await page.getByRole("button", { name: /Fleet review queue.*3 voyages/ }).click();
    const queue = page.getByTestId("company-fleet-triage");
    await queue.getByRole("button", { name: "Inspect review for PW Meridian" }).click();
    const sourceLeads = queue.getByText("Coverage, policy and separate source leads", { exact: true });
    await sourceLeads.click();
    await expect(sourceLeads.locator("..")).not.toContainText(/NAVCEN_MSI|Houston|Chesapeake|Lake Michigan|Pascagoula/);
    await shot("00b-fleet-review");
    await queue.getByRole("link", { name: "Open saved comparison" }).click();
    const decision = page.getByTestId("decision-panel");
    await decision.getByRole("tab", { name: /^Options/ }).click();
    await decision.getByRole("button", { name: /Propose 10 kn on the declared passage/ }).first().click();
    await shot("00c-alternative");
    await approve(decision, choice.optionId, "00d-company");
    await shot("01-company");
    await open(page, "/company/overview");
    await expect(companyHandoffs).toContainText("Waiting on Port");
    await expect(companyHandoffs.getByRole("link", { name: "Open Company comparison" })).toHaveAttribute("href", new RegExp(problem.decisionId));
    await queue.getByRole("button", { name: "Close fleet review" }).click();
    await expect(queue).toBeHidden();
    await shot("01a-waiting-on-port");
    passed("Port home");
    await role(page, /Port Authority/);
    await page.waitForURL("**/port/overview");
    const inbox = page.getByRole("region", { name: "Needs your action" });
    await expect(inbox).toContainText("PW Meridian", { timeout: 30_000 });
    await shot("02-port-home");
    await inbox.getByRole("link", { name: "Review proposal" }).click();
    assert.equal(new URL(page.url()).searchParams.get("proposal"), problem.decisionId);
    passed("Port approves and issues");
    const panel = page.getByTestId("current-proposal-review");
    await expect(panel).toContainText("Assumed anchorage wait", { timeout: 25_000 });
    await expect(page.getByRole("button", { name: /Needs action\s*1\b/ })).toBeVisible();
    const passage = problem.evidence.currentEnvironment.passageComparison.options;
    const baseline = passage[0];
    const selected = passage.find(option => option.optionId === choice.optionId);
    results.assumedWaitHours = { baseline: baseline.anchorageWaitHours, selected: selected.anchorageWaitHours };
    assert.equal((baseline.anchorageWaitHours - selected.anchorageWaitHours).toFixed(2), "4.00");
    await shot("03-frozen-comparison");
    const reviewPending = postResponse("/current-proposals/review");
    await panel.getByRole("button", { name: "Review Company weather proposal" }).click();
    const review = await read(reviewPending);
    await approve(panel, choice.optionId, "03a-port");
    await shot("03a-port-approved");
    const issuePending = postResponse("/handoff");
    await panel.getByTestId("decision-handoff").click();
    const issue = await read(issuePending);
    const advisoryId = issue.advisories[0].advisoryId;
    results.advisoryId = advisoryId;
    await page.getByRole("button", { name: /Needs action/ }).click();
    let card = page.getByTestId("advisory-card").filter({ hasText: "PW Meridian" }).first();
    await card.locator("button").first().click();
    await expect(panel.getByRole("button", { name: "Run frozen demo outcome" })).toBeDisabled();
    await shot("03a-port-draft");
    await advisoryAction(card, "under_review", advisoryId);
    await expect(card.locator("button").first()).toHaveAttribute("aria-expanded", "true");
    await expect(card.getByTestId("advisory-action-issued")).toBeVisible();
    await shot("03b-port-open-for-review");
    await advisoryAction(card, "issued", advisoryId);
    await expect(panel.getByRole("button", { name: "Run frozen demo outcome" })).toBeDisabled();
    await shot("04-port-issued");
    passed("Vessel acknowledges and accepts");
    await role(page, /Vessel Bridge/);
    await page.waitForURL("**/vessel/overview");
    const bridge = page.getByRole("region", { name: "Needs your action" });
    const advisoryLink = bridge.getByRole("link", { name: "Open advisory" });
    await expect(advisoryLink).toHaveAttribute("href", "/vessel/advisories?advisory=" + advisoryId, { timeout: 25_000 });
    await expect(page.getByRole("region", { name: "Passage at a glance" })).toBeVisible();
    await shot("05-bridge");
    await advisoryLink.click();
    card = page.getByTestId("advisory-card").filter({ hasText: "PW Meridian" }).first();
    const recommendation = card.getByRole("region", { name: "Issued recommendation" });
    await expect(recommendation).toContainText("12 → 10 kn");
    await expect(recommendation).toContainText(`${baseline.anchorageWaitHours.toFixed(2)} → ${selected.anchorageWaitHours.toFixed(2)} h`);
    await expect(recommendation).toContainText("Same modeled approach window");
    await expect(card.getByTestId("advisory-action-accepted")).toHaveCount(0);
    await shot("05a-vessel-open-advisory");
    await advisoryAction(card, "acknowledged", advisoryId);
    await expect(card.getByRole("region", { name: "Audit trail" })).toContainText(/acknowledged/i);
    await shot("06-vessel-acknowledged");
    await advisoryAction(card, "accepted", advisoryId);
    await expect(card.getByRole("region", { name: "Audit trail" })).toContainText(/accepted/i);
    await shot("07-vessel-accepted");
    passed("Acceptance returns to Company and Port");
    await role(page, /Fleet Command|Shipping Company/);
    await page.waitForURL("**/company/overview");
    await expect(companyHandoffs).toContainText("Accepted by Vessel", { timeout: 20_000 });
    await shot("07a-company-accepted");
    await role(page, /Port Authority/);
    await page.waitForURL("**/port/overview");
    await expect(page.getByRole("region", { name: "Needs your action" })).toContainText("Accepted by Vessel", { timeout: 20_000 });
    passed("Port records outcome");
    await inbox.getByRole("link", { name: "Review accepted proposal" }).click();
    await panel.getByRole("tab", { name: /^Decide/ }).click();
    await shot("07b-port-ready-for-outcome");
    const outcomePending = postResponse("/" + review.decisionId + "/demo-outcome");
    const runOutcome = page.getByRole("button", { name: "Run frozen demo outcome" });
    await expect(runOutcome).toBeEnabled({ timeout: 20_000 });
    await runOutcome.click();
    const outcome = (await read(outcomePending)).outcome;
    assert.equal(outcome.kind, "SIMULATED_DEMO_OUTCOME");
    assert.equal(outcome.eligibleForRealTarget, false);
    await expect(page.getByTestId("current-demo-outcome")).toContainText("Simulated demo outcome");
    await expect(panel.getByTestId("decision-panel")).toContainText("Outcome completed");
    await expect(panel.getByTestId("decision-countdown")).toHaveCount(0);
    await shot("08-port-outcome");
    await role(page, /Fleet Command|Shipping Company/);
    await page.waitForURL("**/company/overview");
    await expect(companyHandoffs).toContainText("Outcome completed");
    await expect(companyHandoffs.getByRole("link", { name: "Open advisory" })).toHaveAttribute("href", "/company/advisories?advisory=" + advisoryId);
    await shot("08a-company-outcome");
    await companyHandoffs.getByRole("link", { name: "Open advisory" }).click();
    await expect(page.getByTestId("advisory-card").filter({ hasText: advisoryId }).locator("button").first()).toHaveAttribute("aria-expanded", "true");
    passed("Admin");
    await role(page, /National Command/);
    await page.waitForURL("**/admin/radar");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await shot("09-admin");
    passed("Research");
    await open(page, "/research");
    await expect(page.getByRole("main").first()).toBeVisible();
    const benchmark = page.getByRole("region", { name: "Decision policy benchmark" });
    await expect(benchmark).toContainText("12.14 → 1.05 h");
    await expect(benchmark).toContainText("42.1 → 0.0 h");
    await shot("10-research");
    assert.deepEqual(errors, []);
    passed("Done");
  } catch (error) {
    checks.push({ beat, result: "FAIL", message: error.message });
    await shot("failure").catch(() => {});
    throw new Error(`${width}×${height} · ${beat}: ${error.message}`, { cause: error });
  } finally {
    if (evidence) {
      await mkdir(evidence, { recursive: true });
      await writeFile(join(evidence, `${width}-report.json`), JSON.stringify(results, null, 2));
    }
    if (token) await call("/demo/logout", token, {}).catch(() => {});
    await context.close();
  }
}

async function projectorContext(width, height, zoom) {
  const options = { viewport: { width, height }, serviceWorkers: "block", reducedMotion: "reduce" };
  if (zoom === 100) return { context: await browser.newContext(options) };
  const root = await mkdtemp(join(tmpdir(), "portwatch-panel-zoom-"));
  const extension = join(root, "extension");
  await mkdir(extension);
  await writeFile(join(extension, "manifest.json"), JSON.stringify({
    manifest_version: 3, name: "Panel QA browser zoom", version: "1.0",
    background: { service_worker: "worker.js" }, permissions: ["tabs"],
  }));
  await writeFile(join(extension, "worker.js"), "chrome.runtime.onInstalled.addListener(() => {});");
  const context = await chromium.launchPersistentContext(join(root, "profile"), {
    ...options, channel: "chromium", headless: true,
    args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
  });
  const worker = context.serviceWorkers()[0] ?? await context.waitForEvent("serviceworker", { timeout: 15_000 });
  return { context, setZoom: () => worker.evaluate(async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    await chrome.tabs.setZoom(tab.id, 1.25);
    return chrome.tabs.getZoom(tab.id);
  }) };
}

async function runReplay(width, height, zoom) {
  const { context, setZoom } = await projectorContext(width, height, zoom);
  const blocked = [];
  await blockOutbound(context, blocked);
  const page = context.pages()[0] ?? await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.setDefaultTimeout(30_000);
  let token;
  let beat = "Opening";
  const times = [];
  let start = performance.now();
  function next(name) {
    times.push({ beat, ms: Math.round(performance.now() - start) });
    start = performance.now();
    beat = name;
  }
  try {
    await open(page, "/tour");
    if (setZoom) {
      await page.bringToFront();
      assert.equal(await setZoom(), 1.25);
      await expect.poll(() => page.evaluate(() => devicePixelRatio)).toBe(1.25);
    }
    await expect(page.locator(".pw-tour")).toHaveAttribute("data-reduced-motion", "true", { timeout: 20_000 });
    const chapters = page.getByRole("list", { name: "Voyage chapters" }).getByRole("button");
    await expect(chapters).toHaveCount(6, { timeout: 20_000 });
    for (let index = 0; index < 6; index++) {
      await chapters.nth(index).click();
      await expect(chapters.nth(index)).toHaveAttribute("aria-current", "step");
    }
    next("Sign-in");
    await open(page, "/login");
    const login = page.waitForResponse((response) => response.url().endsWith("/demo/session") &&
      response.request().method() === "POST" && response.ok());
    await page.getByRole("button", { name: "Company demo", exact: true }).click();
    token = (await (await login).json()).accessToken;
    await expect(page).toHaveURL(/company\/overview/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    const clock = await call("/demo/terminal/world/clock", token);
    assert.equal(clock.mode, "REPLAY");
    next("Company decision");
    const vesselId = "PWD-001";
    const first = await call("/demo/scenario", token, { vesselId, closureHours: 72 });
    const later = await call("/demo/scenario", token, { vesselId, closureHours: 120 });
    assert.notDeepEqual(first.result.options, later.result.options);
    const option = later.result.options.find((row) => row.feasible && !row.isBaseline);
    assert(option);
    const proposal = await call("/demo/proposal", token, { comparisonId: later.id, optionId: option.optionId });
    next("Port");
    await role(page, /Port Authority/);
    await open(page, "/port/twin");
    await expect(page.getByTestId("twin-inspector")).toBeVisible({ timeout: 30_000 });
    const world = await call("/demo/workspace", token);
    const vessel = world.twin.calls.find((row) => row.vessel_id === vesselId);
    assert.equal(vessel.effectiveEta, 180 + proposal.etaShiftHours);
    const plan = await call("/demo/port-scenario", token, {});
    assert.equal(plan.options.length, 2);
    assert.deepEqual(plan.proposalInput, proposal);
    const advisory = await call("/demo/advisories", token, { policy: "Constrained lookahead" });
    next("Vessel");
    await role(page, /Vessel Bridge/);
    await expect(page).toHaveURL(/vessel\/overview/);
    const ack = await call(`/demo/advisories/${advisory.id}/ack`, token, {});
    assert.equal(ack.state, "ACKNOWLEDGED");
    next("Outcome");
    await role(page, /Port Authority/);
    const result = await call(`/demo/advisories/${advisory.id}/outcome`, token, { reportedWaitingHours: 3.4 });
    assert.equal(result.outcome.source, "DEMONSTRATOR_ENTRY");
    assert.equal(result.state, "RESOLVED");
    next("National view");
    await role(page, /National Command/);
    await expect(page).toHaveURL(/admin\/radar/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    assert.equal((await call("/demo/workspace", token)).world.advisories[0].state, "RESOLVED");
    next("Evidence");
    await open(page, "/research");
    await expect(page.getByRole("main").first()).toBeVisible({ timeout: 20_000 });
    await open(page, "/tour");
    const decide = page.getByRole("button", { name: "2: Decide" });
    await decide.click();
    await expect(decide).toHaveAttribute("aria-current", "step");
    await expect(page.getByText("12.14 h", { exact: true })).toBeAttached({ timeout: 20_000 });
    await expect(page.getByText("1.05 h", { exact: true })).toBeAttached();
    assert.deepEqual(errors, []);
    next("Done");
    console.log(JSON.stringify({ width, height, zoom, blocked: [...new Set(blocked)], times,
      verification: "browser route checks and real Suez API workflow; Company controls require integration" }));
    console.log(`PASS replay ${width}×${height} ${zoom}%`);
  } catch (error) {
    throw new Error(`${width}×${height} ${zoom}% · ${beat}: ${error.message}`, { cause: error });
  } finally {
    if (token) await call("/demo/logout", token, {}).catch(() => {});
    await context.close();
  }
}

const failures = [];
try {
  const matrix = replay ? [[1920, 1080, 100], [1366, 768, 100], [1280, 720, 100], [1280, 720, 125]]
    : [[1366, 768, 100], [1280, 720, 100]];
  const only = Number(process.env.PORTWATCH_PANEL_WIDTH || 0);
  if (only && !matrix.some(([width]) => width === only)) throw new Error("Unknown panel viewport width");
  for (const [width, height, zoom] of matrix.filter(([width]) => !only || width === only)) {
    try {
      if (replay) await runReplay(width, height, zoom);
      else await run(width, height);
    } catch (error) {
      failures.push(error);
      console.error(`FAIL ${width}×${height}`, error.message);
    }
  }
} finally {
  await browser.close();
}
if (failures.length) throw new AggregateError(failures, "Panel acceptance failed");
