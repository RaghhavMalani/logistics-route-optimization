// Dev-only screenshots of the decision engine on the running dev servers
// (frontend :8080, backend :8000). Every view the milestone asks to inspect,
// at the three operating resolutions:
//
//   node qa/shots-decision.mjs ../docs/qa/decision [1920x1080,1440x900,1366x768]
//
// Nothing here is a test of correctness; it is how the eyes get on the
// screens. The backend must be in DEMO licence mode with a fresh register.
import { chromium } from "@playwright/test";
import fs from "node:fs";

const OUT = process.argv[2] ?? "../docs/qa/decision";
const SIZES = (process.argv[3] ?? "1920x1080,1440x900,1366x768")
  .split(",")
  .map((s) => s.split("x").map(Number));
const BASE = process.env.PW_BASE ?? "http://localhost:8080";
fs.mkdirSync(OUT, { recursive: true });

// The port the port-authority screens open on. Nhava Sheva's demo manifest
// holds a consignment that misses its booking with two sailings that can
// take it; Chennai's holds one with no alternative, which is a poorer look
// at the engine. The session's user carries the port, because a restored
// session takes its port from the user, not from the stored preference.
const PORT = process.env.PW_PORT_CODE ?? "INNSA";

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

async function open(role, path, [width, height]) {
  const context = await browser.newContext({ viewport: { width, height } });
  const now = Date.now();
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
        issuedAt: new Date(now).toISOString(),
        expiresAt: new Date(now + 12 * 3600000).toISOString(),
      }),
      JSON.stringify(role),
      JSON.stringify(PORT),
    ],
  );
  const page = await context.newPage();
  page.on("pageerror", (error) => console.log("  pageerror:", error.message));
  await page.goto(`${BASE}${path}`);
  await page.waitForFunction(
    () => !/Restoring session|Checking session/i.test(document.body.innerText),
    undefined,
    { timeout: 60000 },
  );
  return { context, page };
}

// The chart is up once its style is in and the first frame has drawn. The
// map's own loaded() stays false in headless Chromium, where the weather
// raster's placeholder image never decodes, so the overlay is the signal.
async function mapReady(page) {
  await page.waitForFunction(
    () =>
      window.__portwatchMap &&
      window.__portwatchMap.isStyleLoaded !== undefined &&
      !/INITIALISING CHART/.test(document.body.innerText),
    undefined,
    // The dev server transforms a screen's modules on first visit; the
    // budget covers a cold one.
    { timeout: 180000 },
  );
}

async function settle(page, ms = 1800) {
  await page.waitForTimeout(ms);
}

for (const size of SIZES) {
  const tag = `${size[0]}x${size[1]}`;
  console.log(`== ${tag}`);

  // ---------------------------------------------------- vessel decision --
  {
    const { context, page } = await open(
      "NATIONAL_ADMIN",
      "/admin/global-eye",
      size,
    );
    await mapReady(page);
    await page.waitForSelector('[data-testid="decide-item"]', {
      timeout: 60000,
    });
    await page.locator('[data-testid="decide-item"]').first().click();
    await page.waitForSelector('[data-testid="decision-panel"]', {
      timeout: 90000,
    });
    await settle(page, 2600);
    await page.screenshot({ path: `${OUT}/01-decision-compare-${tag}.png` });
    console.log(
      "  options:",
      await page.locator('[data-testid="decision-option"]').count(),
    );

    // A different option: the world should move.
    const other = page.locator(
      '[data-testid="decision-option"][data-selected="false"]',
    );
    if ((await other.count()) > 0) {
      await other.last().click();
      await settle(page, 1600);
      await page.screenshot({
        path: `${OUT}/02-decision-alternative-${tag}.png`,
      });
    }

    // The frontier.
    await page
      .getByRole("tab", { name: /frontier/i })
      .click()
      .catch(async () => {
        await page
          .locator('[data-testid="decision-panel"] button', {
            hasText: /frontier/i,
          })
          .first()
          .click();
      });
    await page.waitForSelector('[data-testid="pareto-chart"]', {
      timeout: 10000,
    });
    await settle(page, 800);
    await page.screenshot({ path: `${OUT}/03-pareto-frontier-${tag}.png` });

    // The money: first as the engine finds it, then re-priced with the
    // operator's own figures, every one of them labelled ASSUMPTION. On the
    // recommended option, where the figures have something to price.
    await page.getByRole("tab", { name: /options/i }).click();
    const recommended = page
      .locator('[data-testid="decision-option"]', { hasText: /Recommended/ })
      .first();
    if (await recommended.count()) await recommended.click();
    const money = page
      .locator('[data-testid="decision-panel"] button', { hasText: /^money$/i })
      .first();
    if (await money.count()) {
      await money.click();
      await page.waitForSelector('[data-testid="financial-evidence"]', {
        timeout: 10000,
      });
      await settle(page, 600);
      await page.screenshot({
        path: `${OUT}/06-financial-evidence-${tag}.png`,
      });
      const form = page.locator('[data-testid="assumption-form"]');
      if (await form.count()) {
        const fill = async (id, value) => {
          const field = page.locator(`[data-testid="assume-${id}"]`);
          if (await field.count()) await field.fill(String(value));
        };
        await fill("charter", 28000);
        await fill("bunker", 610);
        await fill("burn", 95);
        await fill("grt", 52000);
        const before = await page
          .locator('[data-testid="decision-panel"]')
          .getAttribute("data-decision");
        await page.locator('[data-testid="assume-submit"]').click();
        await page.waitForFunction(
          (prev) =>
            document
              .querySelector('[data-testid="decision-panel"]')
              ?.getAttribute("data-decision") !== prev,
          before,
          { timeout: 90000 },
        );
        await page
          .locator('[data-testid="decision-panel"] button', {
            hasText: /^money$/i,
          })
          .first()
          .click();
        await page.waitForSelector('[data-testid="financial-evidence"]', {
          timeout: 10000,
        });
        await settle(page, 800);
        await page.screenshot({
          path: `${OUT}/06b-financial-assumptions-${tag}.png`,
        });
        console.log(
          "  assumption label:",
          await page
            .locator('[data-testid="financial-evidence"]')
            .innerText()
            .then((s) => /ASSUMPTION/.test(s)),
        );
      }
    }
    await context.close();
  }

  // ---------------------------------------------------- copilot decision --
  // "What should MV <name> do?" -- the copilot computes through the engine
  // and opens the same panel on the same problem; nothing is answered from
  // prose. The hull is whichever the action rail names first.
  {
    const { context, page } = await open(
      "NATIONAL_ADMIN",
      "/admin/global-eye",
      size,
    );
    await mapReady(page);
    await page.waitForSelector('[data-testid="decide-item"]', {
      timeout: 60000,
    });
    const item = page
      .locator('[data-testid="attention-item"]')
      .filter({ has: page.locator('[data-testid="decide-item"]') })
      .first();
    const name = (
      await item.locator("span.truncate").first().innerText()
    ).trim();
    await page.locator('[data-testid="command-bar-open"]').click();
    await page
      .locator('[data-testid="command-input"]')
      .fill(`What should ${name} do?`);
    await page.locator('[data-testid="command-input"]').press("Enter");
    await page.waitForSelector('[data-testid="decision-panel"]', {
      timeout: 180000,
    });
    await settle(page, 2600);
    await page.screenshot({ path: `${OUT}/10-copilot-decision-${tag}.png` });
    console.log(
      "  copilot:",
      name,
      "->",
      await page
        .locator('[data-testid="decision-panel"]')
        .getAttribute("data-decision"),
    );
    await context.close();
  }

  // ------------------------------------------------------- port scenario --
  {
    const { context, page } = await open("PORT_AUTHORITY", "/port/twin", size);
    await page.waitForSelector('[data-testid="port-decide"]', {
      timeout: 60000,
    });
    await settle(page, 2500);
    await page.locator('[data-testid="port-decide"]').click();
    await page.waitForSelector('[data-testid="decision-panel"]', {
      timeout: 90000,
    });
    await settle(page, 2600);
    await page.screenshot({ path: `${OUT}/04-port-scenario-${tag}.png` });
    await context.close();
  }

  // ------------------------------------------------------- cargo decision --
  {
    const { context, page } = await open("PORT_AUTHORITY", "/port/cargo", size);
    await page.waitForSelector('[data-testid="cargo-decide"]', {
      timeout: 60000,
    });
    await page.locator('[data-testid="cargo-decide"]').click();
    await page.waitForSelector('[data-testid="decision-panel"]', {
      timeout: 90000,
    });
    await settle(page, 1500);
    await page.screenshot({ path: `${OUT}/05-cargo-decision-${tag}.png` });
    await context.close();
  }

  // ------------------------------------------------------ mission replay --
  {
    const { context, page } = await open(
      "NATIONAL_ADMIN",
      "/admin/missions",
      size,
    );
    await mapReady(page);
    await page.waitForSelector('[data-testid="mission-panel"]', {
      timeout: 60000,
    });
    await page.waitForSelector('[data-testid="mission-decide"]', {
      timeout: 60000,
    });
    await settle(page, 2400);
    await page.screenshot({ path: `${OUT}/07-mission-replay-${tag}.png` });

    await page.locator('[data-testid="mission-decide"]').first().click();
    await page.waitForSelector('[data-testid="mission-decision"]', {
      timeout: 90000,
    });
    await settle(page, 2600);
    await page.screenshot({ path: `${OUT}/08-mission-decision-${tag}.png` });

    await page.locator('[data-testid="mission-choose"]').click();
    await page.waitForFunction(
      () => /Chosen:/.test(document.body.innerText),
      undefined,
      { timeout: 30000 },
    );
    await page.locator('[data-testid="mission-reveal"]').click();
    await page.waitForSelector('[data-testid="mission-scorecard"]', {
      timeout: 90000,
    });
    await settle(page, 2000);
    await page.screenshot({ path: `${OUT}/09-outcome-reveal-${tag}.png` });
    await context.close();
  }
}

await browser.close();
console.log("done:", OUT);
