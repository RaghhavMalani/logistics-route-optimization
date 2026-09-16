// Screenshots for the productisation review, against the running stack
// (frontend :8080, backend :8000). Every major workflow the milestone asks to
// review, at the three operating resolutions:
//
//   node qa/shots-productization.mjs ../docs/qa/productization 1920x1080,1440x900,1366x768
//
// The pages are driven exactly as a buyer would drive them: sign-in seeded,
// then clicks. Nothing is injected into the page and no API is mocked.

import fs from "node:fs";
import { chromium } from "playwright";

const OUT = process.argv[2] ?? "../docs/qa/productization";
const SIZES = (process.argv[3] ?? "1920x1080,1440x900,1366x768")
  .split(",")
  .map((s) => s.split("x").map(Number));
const BASE = process.env.PW_BASE ?? "http://localhost:8080";
const ONLY = process.env.PW_ONLY ? process.env.PW_ONLY.split(",") : null;
const PORT = process.env.PW_PORT_CODE ?? "INNSA";

fs.mkdirSync(OUT, { recursive: true });

const USERS = {
  NATIONAL_ADMIN: {
    id: "demo-admin",
    email: "admin@portwatch.demo",
    displayName: "A. Deshmukh",
    role: "NATIONAL_ADMIN",
    organisation: "Ministry of Ports, Shipping and Waterways",
    portCode: null,
    companyId: null,
    vesselIds: [],
  },
  PORT_AUTHORITY: {
    id: "demo-port",
    email: "port@portwatch.demo",
    displayName: "S. Iyer",
    role: "PORT_AUTHORITY",
    organisation: "Jawaharlal Nehru Port Authority",
    portCode: PORT,
    companyId: null,
    vesselIds: [],
  },
  SHIPPING_COMPANY: {
    id: "demo-company",
    email: "company@portwatch.demo",
    displayName: "M. Fernandes",
    role: "SHIPPING_COMPANY",
    organisation: "PortWatch Demo Shipping",
    portCode: null,
    companyId: "PWD",
    vesselIds: [],
  },
  VESSEL_OPERATOR: {
    id: "demo-vessel",
    email: "vessel@portwatch.demo",
    displayName: "R. Nayar",
    role: "VESSEL_OPERATOR",
    organisation: "PortWatch Demo Shipping",
    portCode: null,
    companyId: "PWD",
    vesselIds: ["PWD-001"],
  },
};

const browser = await chromium.launch();

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
  page.on("pageerror", (error) => console.log("  pageerror:", error.message));
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

async function settle(page, ms = 1800) {
  await page.waitForTimeout(ms);
}

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
}

function wants(flow) {
  return !ONLY || ONLY.includes(flow);
}

for (const size of SIZES) {
  const tag = `${size[0]}x${size[1]}`;
  console.log(`== ${tag}`);

  // ------------------------------------------------------- national command --
  if (wants("radar")) {
    const { context, page } = await open(
      "NATIONAL_ADMIN",
      "/admin/radar",
      size,
    );
    await settle(page, 4000);
    await shot(page, "01-national-command", tag);
    await context.close();
  }

  // ------------------------------------------------ global eye + attention --
  if (wants("globaleye")) {
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
    await shot(page, "02-global-eye-attention", tag);

    // The lenses that now read the backend.
    await page
      .locator('[data-testid="lens-option"][data-lens="SECURITY"]')
      .click();
    await page.waitForSelector('[data-testid="lens-security"]', {
      timeout: 30000,
    });
    await settle(page, 1200);
    await shot(page, "03-lens-security-unavailable", tag);
    await page
      .locator('[data-testid="lens-option"][data-lens="CARGO"]')
      .click();
    await page.waitForSelector('[data-testid="exposure-class"]', {
      timeout: 30000,
    });
    await settle(page, 1200);
    await shot(page, "04-lens-cargo-structural-exposure", tag);
    await page
      .locator('[data-testid="lens-option"][data-lens="OPERATIONS"]')
      .click();

    // The decision from the action rail.
    await page.waitForSelector('[data-testid="decide-item"]', {
      timeout: 60000,
    });
    await page.locator('[data-testid="decide-item"]').first().click();
    await page.waitForSelector('[data-testid="decision-panel"]', {
      timeout: 120000,
    });
    await settle(page, 2600);
    await shot(page, "05-decision-comparison", tag);
    const money = page
      .locator('[data-testid="decision-panel"] button', { hasText: /^money$/i })
      .first();
    if (await money.count()) {
      await money.click();
      await page.waitForSelector('[data-testid="financial-evidence"]', {
        timeout: 15000,
      });
      await settle(page, 800);
      await shot(page, "06-financial", tag);
    }
    await context.close();
  }

  // ---------------------------------------------------------- copilot --
  if (wants("copilot")) {
    const { context, page } = await open(
      "NATIONAL_ADMIN",
      "/admin/global-eye",
      size,
    );
    await mapReady(page);
    await page.waitForSelector('[data-testid="decide-item"]', {
      timeout: 90000,
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
    await shot(page, "07-spatial-copilot", tag);
    await context.close();
  }

  // ------------------------------------------------------ company / vessel --
  if (wants("company")) {
    const { context, page } = await open(
      "SHIPPING_COMPANY",
      "/company/overview",
      size,
    );
    await settle(page, 5000);
    await shot(page, "08-shipping-company", tag);
    await context.close();
  }
  if (wants("vessel")) {
    const { context, page } = await open(
      "VESSEL_OPERATOR",
      "/vessel/overview",
      size,
    );
    await settle(page, 5000);
    await shot(page, "09-vessel-bridge", tag);
    await context.close();
  }

  // --------------------------------------------------------- port authority --
  if (wants("port")) {
    const { context, page } = await open(
      "PORT_AUTHORITY",
      "/port/overview",
      size,
    );
    await settle(page, 5000);
    await shot(page, "10-port-authority", tag);
    await context.close();
  }
  if (wants("twin")) {
    const { context, page } = await open("PORT_AUTHORITY", "/port/twin", size);
    await page.waitForSelector('[data-testid="port-decide"]', {
      timeout: 90000,
    });
    await settle(page, 3500);
    await shot(page, "11-port-twin", tag);
    await page.locator('[data-testid="port-decide"]').click();
    await page.waitForSelector('[data-testid="decision-panel"]', {
      timeout: 120000,
    });
    await settle(page, 2600);
    await shot(page, "12-port-twin-decision", tag);
    await context.close();
  }
  if (wants("cargo")) {
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
    await shot(page, "13-cargo-decision", tag);
    await context.close();
  }

  // ---------------------------------------------------------- missions --
  if (wants("missions")) {
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
    await shot(page, "14-mission-replay-suez", tag);
    await page.locator('[data-testid="mission-decide"]').first().click();
    await page.waitForSelector('[data-testid="mission-decision"]', {
      timeout: 120000,
    });
    await settle(page, 2600);
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
    await shot(page, "15-mission-outcome-reveal", tag);

    // The second mission, then the comparison.
    const option = page.locator(
      '[data-testid="mission-option"][data-mission="gulf-of-kutch-biparjoy-2023"]',
    );
    if (await option.count()) {
      await option.click();
      await page.waitForSelector('[data-testid="mission-decide"]', {
        timeout: 90000,
      });
      await settle(page, 3200);
      await shot(page, "16-mission-replay-biparjoy", tag);
      await page.locator('[data-testid="mission-decide"]').first().click();
      await page.waitForSelector('[data-testid="mission-decision"]', {
        timeout: 120000,
      });
      await settle(page, 2600);
      await shot(page, "17-mission-biparjoy-decision", tag);
    }
    await page.locator('[data-testid="mission-comparison-open"]').click();
    await page.waitForSelector('[data-testid="comparison-row"]', {
      timeout: 120000,
    });
    await settle(page, 1200);
    await shot(page, "18-mission-comparison", tag);
    await context.close();
  }

  // ------------------------------------------------------------ system --
  if (wants("system")) {
    const { context, page } = await open(
      "NATIONAL_ADMIN",
      "/admin/system",
      size,
    );
    await page.waitForSelector('[data-testid="freshness-row"]', {
      timeout: 60000,
    });
    await settle(page, 1500);
    await shot(page, "19-system-freshness", tag);
    await context.close();
  }
}

await browser.close();
