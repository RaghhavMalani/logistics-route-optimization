// The two-minute executive demo, driven exactly as a buyer would see it and
// timed. Against the running stack (frontend :8080, backend :8000), started by
// `python -m portwatch.demo start`. No API is mocked, nothing is refreshed by
// hand, and the devtools stay closed: if a beat cannot be reached the run
// fails with the beat's name, which is the honest result.
//
//   node qa/executive-demo.mjs [../docs/qa/executive-demo] [1920x1080]
//
// Every beat of docs/FLAGSHIP_DEMO.md is a step here; the script prints the
// wall-clock time each beat took to reach and writes the table as JSON next to
// the screenshots so the doc can quote it.

import fs from "node:fs";
import { chromium } from "playwright";

const OUT = process.argv[2] ?? "../docs/qa/executive-demo";
const [WIDTH, HEIGHT] = (process.argv[3] ?? "1920x1080").split("x").map(Number);
// The URLs the start command prints. It binds 127.0.0.1; "localhost" would
// try ::1 first on some hosts and pay for it on every module request.
const BASE = process.env.PW_BASE ?? "http://127.0.0.1:8080";
const API = process.env.PW_API ?? "http://127.0.0.1:8000/api";

fs.mkdirSync(OUT, { recursive: true });

const ADMIN = {
  id: "demo-admin",
  email: "admin@portwatch.demo",
  displayName: "A. Deshmukh",
  role: "NATIONAL_ADMIN",
  organisation: "Ministry of Ports, Shipping and Waterways",
  portCode: null,
  companyId: null,
  vesselIds: [],
};

// Headless Chromium renders WebGL in software (SwiftShader) and can run the
// chart at a few frames a second; a buyer's browser has a GPU. PW_HEADED=1
// opens a real window and is the run the timings in docs/FLAGSHIP_DEMO.md
// come from.
const HEADED = process.env.PW_HEADED === "1";
const browser = await chromium.launch({ headless: !HEADED });
const context = await browser.newContext({
  viewport: { width: WIDTH, height: HEIGHT },
  deviceScaleFactor: 1,
});
await context.addInitScript(
  ([session, viewAs]) => {
    window.localStorage.setItem("portwatch.session.v1", session);
    window.localStorage.setItem("portwatch.viewAs.v1", viewAs);
  },
  [
    JSON.stringify({
      user: ADMIN,
      mode: "demo",
      issuedAt: new Date().toISOString(),
      expiresAt: new Date(Date.now() + 12 * 3600000).toISOString(),
    }),
    JSON.stringify("NATIONAL_ADMIN"),
  ],
);
const page = await context.newPage();
const pageErrors = [];
page.on("pageerror", (error) => pageErrors.push(error.message));

const t0 = Date.now();
let last = t0;
const beats = [];
let shotIndex = 0;

async function beat(name, work, { shot = true } = {}) {
  const started = Date.now();
  let detail = "";
  try {
    detail = (await work()) ?? "";
  } catch (error) {
    beats.push({
      name,
      ok: false,
      error: String(error.message ?? error),
      sinceStartMs: started - t0,
    });
    throw new Error(`beat "${name}" failed: ${error.message ?? error}`);
  }
  const now = Date.now();
  const row = {
    name,
    ok: true,
    tookMs: now - started,
    sinceLastMs: now - last,
    sinceStartMs: now - t0,
    detail,
  };
  last = now;
  beats.push(row);
  if (shot) {
    shotIndex += 1;
    const file = `${String(shotIndex).padStart(2, "0")}-${name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.png`;
    await page.screenshot({ path: `${OUT}/${file}` });
    row.screenshot = file;
  }
  console.log(
    `  ${String(row.sinceStartMs / 1000).padStart(6)}s  +${String(row.tookMs / 1000).padStart(5)}s  ${name}${detail ? `  — ${detail}` : ""}`,
  );
}

const panel = () => page.locator('[data-testid="decision-panel"]');
// Tabs may carry a count ("Options4" as the accessible name); match on the
// label prefix.
const tab = (label) =>
  panel().getByRole("tab", { name: new RegExp(`^${label}`) });

// A health read is what the start command does; the demo begins from a
// verified stack, and the run records what the stack said it was.
const health = await (await fetch(`${API}/health`)).json();
console.log(
  `stack: licence ${health.licenceMode?.mode} (${health.licenceMode?.source}); world clock ${health.worldClock?.mode}; server ${health.serverTimeUtc}`,
);

console.log(
  `\n== executive demo at ${WIDTH}x${HEIGHT}, ${HEADED ? "headed (GPU)" : "headless (software GL)"}\n`,
);

// ---------------------------------------------------------------- 00:00 --
await beat("Global Eye opens with the chart drawn", async () => {
  await page.goto(`${BASE}/admin/global-eye`);
  await page.waitForFunction(
    () => !/Restoring session|Checking session/i.test(document.body.innerText),
    undefined,
    { timeout: 60000 },
  );
  await page.waitForFunction(
    () =>
      window.__portwatchMap &&
      window.__portwatchMap.isStyleLoaded !== undefined &&
      !/INITIALISING CHART/.test(document.body.innerText),
    undefined,
    { timeout: 180000 },
  );
});

await beat("The live register lists corroborated events", async () => {
  await page.waitForSelector('[data-testid="cascade-row"]', { timeout: 90000 });
  const rows = await page.locator('[data-testid="cascade-row"]').count();
  return `${rows} cascades`;
});

await beat("The action rail ranks what needs intervention", async () => {
  await page.waitForSelector('[data-testid="decide-item"]', { timeout: 60000 });
  const items = await page.locator('[data-testid="attention-item"]').count();
  const actionable = await page.locator('[data-testid="decide-item"]').count();
  return `${items} items, ${actionable} with a decision open`;
});

// ---------------------------------------------------------------- 00:20 --
await beat("What should we do? — the decision computed", async () => {
  await page.locator('[data-testid="decide-item"]').first().click();
  await page.waitForSelector('[data-testid="decision-panel"]', {
    timeout: 120000,
  });
  await page.waitForSelector('[data-testid="decision-option"]', {
    timeout: 30000,
  });
  const options = await page.locator('[data-testid="decision-option"]').count();
  const notOffered = await page.locator('[data-testid="not-offered"]').count();
  return `${options} options on the table, ${notOffered} not offered with a reason`;
});

await beat("Compare — every option's world on the chart", async () => {
  await panel().getByRole("button", { name: "Compare" }).click();
  await page.waitForTimeout(600);
  // The script says: option B, then A. Row 0 is the current plan.
  const options = page.locator('[data-testid="decision-option"]');
  const count = await options.count();
  if (count > 2) await options.nth(2).click();
  await page.waitForTimeout(400);
  if (count > 1) await options.nth(1).click();
  await page.waitForTimeout(400);
  const selected = (await options.nth(1).innerText()).split("\n")[0].trim();
  return `selected ${selected}`;
});

await beat("Frontier — filled nondominated, hollow named", async () => {
  await tab("Frontier").click();
  await page.waitForSelector('[data-testid="pareto-chart"]', {
    timeout: 15000,
  });
  const points = await page.locator('[data-testid="pareto-point"]').count();
  return `${points} evaluated points`;
});

await beat("Why — the Critic names what it read", async () => {
  await tab("Why").click();
  await page.waitForSelector('[data-testid="critic-view"]', { timeout: 15000 });
  const checks = await page.locator('[data-testid="critic-check"]').count();
  return `${checks} checks`;
});

// ---------------------------------------------------------------- 00:50 --
await beat("Money — unknown is never zero", async () => {
  await tab("Money").click();
  await page.waitForSelector('[data-testid="financial-evidence"]', {
    timeout: 15000,
  });
  const components = await page
    .locator('[data-testid="cost-component"]')
    .count();
  const text = await page
    .locator('[data-testid="financial-evidence"]')
    .innerText();
  const unknown = (text.match(/unknown/gi) ?? []).length;
  return `${components} cost components, "unknown" appears ${unknown} times`;
});

await beat("Re-price with the operator's own assumptions", async () => {
  await page.waitForSelector('[data-testid="assumption-form"]', {
    timeout: 15000,
  });
  const charter = page.locator('[data-testid="assume-charter"]');
  const grt = page.locator('[data-testid="assume-grt"]');
  if (await charter.count()) await charter.fill("28000");
  if (await grt.count()) await grt.fill("95000");
  await page.locator('[data-testid="assume-submit"]').click();
  await page.waitForFunction(
    () => /USER_ASSUMPTION/.test(document.body.innerText),
    undefined,
    { timeout: 60000 },
  );
  const text = await page
    .locator('[data-testid="financial-evidence"]')
    .innerText();
  const priced = (text.match(/KNOWN/g) ?? []).length;
  const tariff = /PUBLIC_TARIFF/.test(text)
    ? "a public tariff cited"
    : "no public tariff applies";
  return `${priced} components now priced as labelled assumptions; ${tariff}`;
});

// ---------------------------------------------------------------- 01:10 --
await beat("Decide — mark reviewed", async () => {
  await tab("Decide").click();
  await page.waitForSelector('[data-testid="decision-workflow"]', {
    timeout: 15000,
  });
  await page.locator('[data-testid="decision-review"]').click();
  await page.waitForSelector('[data-testid="decision-approve"]', {
    timeout: 30000,
  });
});

await beat("Approve the recommended option", async () => {
  // Re-pricing made a new problem; select the recommendation on it before
  // approving, the way the talk track does ("I approve option A").
  await tab("Options").click();
  await page.locator('[data-testid="decision-option"]').nth(1).click();
  await tab("Decide").click();
  const approve = page.locator('[data-testid="decision-approve"]');
  const label = (await approve.innerText()).trim();
  await approve.click();
  await page.waitForFunction(
    () => /Approved:/.test(document.body.innerText),
    undefined,
    { timeout: 30000 },
  );
  return label;
});

await beat("Hand into the advisory boundary (DRAFT)", async () => {
  const handoff = page.locator('[data-testid="decision-handoff"]');
  if (!(await handoff.count()))
    return "no handoff offered: the approved option is the current plan";
  await handoff.click();
  await page.waitForSelector('[data-testid="handoff-advisories"]', {
    timeout: 30000,
  });
  const advisories = await page
    .locator('[data-testid="handoff-advisories"] li')
    .count();
  return `${advisories} DRAFT advisor${advisories === 1 ? "y" : "ies"}`;
});

// ---------------------------------------------------------------- 01:30 --
await beat("Mission — the clock reads March 2021", async () => {
  await page.goto(`${BASE}/admin/missions`);
  await page.waitForFunction(
    () =>
      window.__portwatchMap &&
      window.__portwatchMap.isStyleLoaded !== undefined &&
      !/INITIALISING CHART/.test(document.body.innerText),
    undefined,
    { timeout: 180000 },
  );
  await page.waitForSelector('[data-testid="mission-decide"]', {
    timeout: 90000,
  });
  const clock = (
    await page.locator('[data-testid="mission-clock"]').first().innerText()
  ).trim();
  const hidden = (
    await page
      .locator('[data-testid="mission-hidden-count"]')
      .first()
      .innerText()
  ).trim();
  return `${clock}; ${hidden}`;
});

await beat("Decide on the illustrative hull", async () => {
  await page.locator('[data-testid="mission-decide"]').first().click();
  await page.waitForSelector('[data-testid="mission-decision"]', {
    timeout: 120000,
  });
});

await beat("Choose this option", async () => {
  await page.locator('[data-testid="mission-choose"]').click();
  await page.waitForFunction(
    () => /Chosen:/.test(document.body.innerText),
    undefined,
    {
      timeout: 30000,
    },
  );
});

await beat("Reveal the outcome — the scorecard", async () => {
  await page.locator('[data-testid="mission-reveal"]').click();
  await page.waitForSelector('[data-testid="mission-scorecard"]', {
    timeout: 120000,
  });
  const regret = (
    await page.locator('[data-testid="scorecard-regret"]').first().innerText()
  )
    .replace(/\s+/g, " ")
    .trim();
  return regret;
});

const total = Date.now() - t0;
console.log(
  `\ntotal ${(total / 1000).toFixed(1)}s; page errors: ${pageErrors.length}`,
);
for (const error of pageErrors) console.log(`  pageerror: ${error}`);

fs.writeFileSync(
  `${OUT}/timings.json`,
  JSON.stringify(
    {
      recordedAt: new Date().toISOString(),
      viewport: `${WIDTH}x${HEIGHT}`,
      browser: HEADED
        ? "chromium headed (GPU)"
        : "chromium headless (software GL)",
      stack: {
        licenceMode: health.licenceMode,
        worldClock: health.worldClock,
        serverTimeUtc: health.serverTimeUtc,
      },
      totalMs: total,
      pageErrors,
      beats,
    },
    null,
    2,
  ) + "\n",
);

await browser.close();
if (pageErrors.length) process.exit(2);
