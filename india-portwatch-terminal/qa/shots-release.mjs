// The release candidate's canonical screenshots, at the three operating
// resolutions, against the running servers (production build on :4173 or the
// dev server on :8080 via PW_BASE, API on :8000):
//
//   node qa/shots-release.mjs ../docs/qa/release [1920x1080,1440x900,1366x768]
//
// One file per screen the freeze names: National Command, the Global Eye
// cascade, the attention queue, decision alternatives, the robust
// recommendation, the Pareto frontier, a port scenario, a cargo scenario, a
// financial assumption, weather, signal health, security unavailable, a
// mission replay, a mission reveal, and the failure state when the API is
// gone. Every shot reports horizontal overflow and text under 9.5px so a
// layout regression is a number, not an impression.
import { chromium } from "@playwright/test";
import fs from "node:fs";

const OUT = process.argv[2] ?? "../docs/qa/release";
const SIZES = (process.argv[3] ?? "1920x1080,1440x900,1366x768")
  .split(",")
  .map((s) => s.split("x").map(Number));
const BASE = process.env.PW_BASE ?? "http://127.0.0.1:4173";
const PORT = process.env.PW_PORT_CODE ?? "INNSA";
fs.mkdirSync(OUT, { recursive: true });

const USERS = {
  NATIONAL_ADMIN: {
    id: "demo-admin",
    email: "admin@portwatch.demo",
    displayName: "A. Deshmukh",
    role: "NATIONAL_ADMIN",
    organisation: "National Maritime Operations Centre",
    portCode: null,
    companyId: null,
    vesselIds: [],
  },
  PORT_AUTHORITY: {
    id: "demo-port",
    email: "port@portwatch.demo",
    displayName: "S. Iyer",
    role: "PORT_AUTHORITY",
    organisation: "Port Authority — Control Room (demo)",
    portCode: PORT,
    companyId: null,
    vesselIds: [],
  },
};

const browser = await chromium.launch();
const findings = [];

async function open(role, path, size) {
  const context = await browser.newContext({
    viewport: { width: size[0], height: size[1] },
    deviceScaleFactor: 1,
  });
  await context.addInitScript(
    ([session, viewAs, port]) => {
      window.localStorage.setItem("portwatch.session.v1", session);
      window.localStorage.setItem("portwatch.viewAs.v1", viewAs);
      window.localStorage.setItem("portwatch.port.v1", port);
    },
    [
      JSON.stringify({
        user: USERS[role],
        mode: "demo",
        issuedAt: new Date().toISOString(),
        expiresAt: new Date(Date.now() + 12 * 3600000).toISOString(),
      }),
      JSON.stringify(role),
      JSON.stringify(PORT),
    ],
  );
  const page = await context.newPage();
  page.on("pageerror", (error) =>
    findings.push(`${path}: pageerror ${error.message}`),
  );
  await page.goto(`${BASE}${path}`);
  await page.waitForFunction(
    () => !/Restoring session|Checking session/i.test(document.body.innerText),
    undefined,
    { timeout: 60000 },
  );
  return { context, page };
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

const settle = (page, ms = 1800) => page.waitForTimeout(ms);

async function shot(page, name, tag) {
  await page.screenshot({ path: `${OUT}/${name}-${tag}.png` });
  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  const tiny = await page.evaluate(() => {
    let count = 0;
    for (const el of document.querySelectorAll("body *")) {
      const size = parseFloat(getComputedStyle(el).fontSize);
      if (size && size < 9.5 && el.childNodes.length && el.textContent?.trim())
        count += 1;
    }
    return count;
  });
  console.log(
    `  ${name}: overflow ${overflow}px, elements under 9.5px: ${tiny}`,
  );
  if (overflow > 0)
    findings.push(`${name}-${tag}: horizontal overflow ${overflow}px`);
}

async function tab(page, pattern) {
  await page
    .locator('[data-testid="decision-panel"] button', { hasText: pattern })
    .first()
    .click();
}

for (const size of SIZES) {
  const tag = `${size[0]}x${size[1]}`;
  console.log(`== ${tag}`);

  // 01 national command ------------------------------------------------------
  {
    const { context, page } = await open(
      "NATIONAL_ADMIN",
      "/admin/radar",
      size,
    );
    await settle(page, 4000);
    await shot(page, "01-national-command", tag);
    await context.close();
  }

  // 02-06, 10-12 the global eye ----------------------------------------------
  {
    const { context, page } = await open(
      "NATIONAL_ADMIN",
      "/admin/global-eye",
      size,
    );
    await mapReady(page);
    await page.waitForSelector('[data-testid="cascade-row"]', {
      timeout: 90000,
    });
    await settle(page, 2600);
    await shot(page, "03-attention", tag);

    // The cascade, mid-play.
    const play = page.locator('[data-testid="play-cascade"]');
    if (await play.count()) {
      await play.first().click();
      await settle(page, 1400);
      await shot(page, "02-global-eye-cascade", tag);
      const reset = page.locator('[data-testid="reset-cascade"]');
      if (await reset.count()) await reset.first().click();
      await settle(page, 600);
    }

    // The lenses: weather, security unavailable.
    await page
      .locator('[data-testid="lens-option"][data-lens="WEATHER"]')
      .click();
    await settle(page, 2200);
    await shot(page, "10-weather", tag);
    await page
      .locator('[data-testid="lens-option"][data-lens="SECURITY"]')
      .click();
    await page.waitForSelector('[data-testid="lens-security"]', {
      timeout: 30000,
    });
    await settle(page, 1200);
    await shot(page, "12-security-unavailable", tag);
    await page
      .locator('[data-testid="lens-option"][data-lens="OPERATIONS"]')
      .click();

    // The decision: alternatives, the robust recommendation, the frontier, the money.
    await page.waitForSelector('[data-testid="decide-item"]', {
      timeout: 60000,
    });
    await page.locator('[data-testid="decide-item"]').first().click();
    await page.waitForSelector('[data-testid="decision-panel"]', {
      timeout: 120000,
    });
    await settle(page, 2600);
    await shot(page, "04-decision-alternatives", tag);
    const kind = await page
      .locator('[data-testid="robust-headline"]')
      .getAttribute("data-kind");
    console.log(`  robust recommendation: ${kind}`);
    await tab(page, /^robust$/i);
    await page.waitForSelector('[data-testid="robust-view"]', {
      timeout: 10000,
    });
    await settle(page, 800);
    await shot(page, "05-robust-recommendation", tag);
    await tab(page, /^frontier$/i);
    await page.waitForSelector('[data-testid="pareto-chart"]', {
      timeout: 10000,
    });
    await settle(page, 800);
    await shot(page, "06-pareto-frontier", tag);
    const money = page
      .locator('[data-testid="decision-panel"] button', { hasText: /^money$/i })
      .first();
    if (await money.count()) {
      await money.click();
      await page.waitForSelector('[data-testid="financial-evidence"]', {
        timeout: 15000,
      });
      const form = page.locator('[data-testid="assumption-form"]');
      if (await form.count()) {
        for (const [id, value] of [
          ["charter", 28000],
          ["bunker", 610],
          ["burn", 95],
          ["grt", 52000],
        ]) {
          const field = page.locator(`[data-testid="assume-${id}"]`);
          if (await field.count()) await field.fill(String(value));
        }
        const before = await page
          .locator('[data-testid="decision-panel"]')
          .getAttribute("data-decision");
        await page.locator('[data-testid="assume-submit"]').click();
        await page
          .waitForFunction(
            (prev) =>
              document
                .querySelector('[data-testid="decision-panel"]')
                ?.getAttribute("data-decision") !== prev,
            before,
            { timeout: 90000 },
          )
          .catch(() =>
            findings.push(`${tag}: the priced decision did not recompute`),
          );
        const moneyAgain = page
          .locator('[data-testid="decision-panel"] button', {
            hasText: /^money$/i,
          })
          .first();
        if (await moneyAgain.count()) await moneyAgain.click();
        await page
          .waitForSelector('[data-testid="financial-evidence"]', {
            timeout: 15000,
          })
          .catch(() => {});
      }
      await settle(page, 800);
      await shot(page, "09-financial-assumption", tag);
    }
    await context.close();
  }

  // 07 port scenario ---------------------------------------------------------
  {
    const { context, page } = await open("PORT_AUTHORITY", "/port/twin", size);
    await page.waitForSelector('[data-testid="port-decide"]', {
      timeout: 90000,
    });
    await settle(page, 3000);
    const bunch = page.locator('[data-testid="port-bunch"]');
    if (await bunch.count()) await bunch.first().click();
    await page.locator('[data-testid="port-decide"]').first().click();
    await page.waitForSelector('[data-testid="decision-panel"]', {
      timeout: 120000,
    });
    await settle(page, 2400);
    await shot(page, "07-port-scenario", tag);
    await context.close();
  }

  // 08 cargo scenario --------------------------------------------------------
  {
    const { context, page } = await open("PORT_AUTHORITY", "/port/cargo", size);
    await page.waitForSelector('[data-testid="cargo-decide"]', {
      timeout: 90000,
    });
    await settle(page, 1500);
    await page.locator('[data-testid="cargo-decide"]').click();
    await page.waitForSelector('[data-testid="decision-panel"]', {
      timeout: 120000,
    });
    await settle(page, 1500);
    await shot(page, "08-cargo-scenario", tag);
    await context.close();
  }

  // 11 signal health ---------------------------------------------------------
  {
    const { context, page } = await open(
      "NATIONAL_ADMIN",
      "/admin/system",
      size,
    );
    await page.waitForSelector('[data-testid="freshness-row"]', {
      timeout: 60000,
    });
    await settle(page, 1500);
    await shot(page, "11-signal-health", tag);
    await context.close();
  }

  // 13-14 mission replay and reveal -----------------------------------------
  {
    const { context, page } = await open(
      "NATIONAL_ADMIN",
      "/admin/missions",
      size,
    );
    await mapReady(page);
    await page.waitForSelector('[data-testid="mission-decide"]', {
      timeout: 90000,
    });
    await settle(page, 2400);
    await shot(page, "13-mission-replay", tag);
    await page.locator('[data-testid="mission-decide"]').first().click();
    await page.waitForSelector('[data-testid="mission-decision"]', {
      timeout: 120000,
    });
    await settle(page, 2000);
    await page.locator('[data-testid="mission-choose"]').click();
    await page.waitForFunction(
      () => /Chosen:/.test(document.body.innerText),
      undefined,
      { timeout: 30000 },
    );
    await page.locator('[data-testid="mission-reveal"]').click();
    await page.waitForSelector('[data-testid="mission-scorecard"]', {
      timeout: 120000,
    });
    await settle(page, 2000);
    await shot(page, "14-mission-reveal", tag);
    await context.close();
  }

  // 15 the failure state: the API goes away under a loaded screen -----------
  {
    const { context, page } = await open(
      "NATIONAL_ADMIN",
      "/admin/global-eye",
      size,
    );
    await mapReady(page);
    await page.waitForSelector('[data-testid="cascade-row"]', {
      timeout: 90000,
    });
    await context.route("**/api/**", (route) =>
      route.abort("connectionrefused"),
    );
    await page.evaluate(() =>
      window.dispatchEvent(new Event("portwatch:signals-refresh")),
    );
    await page
      .waitForFunction(
        () => /API down/i.test(document.body.innerText),
        undefined,
        { timeout: 60000 },
      )
      .catch(() =>
        findings.push(
          `${tag}: the strip did not say API down within a minute of the API going away`,
        ),
      );
    await settle(page, 1200);
    await shot(page, "15-failure-state", tag);
    await context.close();
  }
}

await browser.close();
if (findings.length) {
  console.log("FINDINGS:");
  for (const line of findings) console.log("  - " + line);
  process.exit(1);
}
console.log("ok");
