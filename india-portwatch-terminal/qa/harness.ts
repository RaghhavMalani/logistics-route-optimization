/**
 * Browser regression harness.
 *
 * Three things every test gets:
 *
 *   a replayed API, so a run never depends on a live backend or the network;
 *   a seeded session, so a role can be put on screen without a sign-in flow;
 *   a console and network recorder, so "the screen rendered" is not mistaken
 *   for "the screen worked".
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test as base, type BrowserContext, type Page } from "@playwright/test";

const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "fixtures");

export type Role =
  | "VESSEL_OPERATOR"
  | "SHIPPING_COMPANY"
  | "PORT_AUTHORITY"
  | "NATIONAL_ADMIN";

const DEMO_COMPANY_ID = "portwatch-demo-shipping";
const DEMO_COMPANY_NAME = "PortWatch Demo Shipping";

export const ACCOUNTS: Record<Role, Record<string, unknown>> = {
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
    organisation: "Chennai Port Authority — Control Room",
    portCode: "INMAA",
    companyId: null,
    vesselIds: [],
  },
  SHIPPING_COMPANY: {
    id: "demo-company",
    email: "company@portwatch.demo",
    displayName: "M. Fernandes",
    role: "SHIPPING_COMPANY",
    organisation: DEMO_COMPANY_NAME,
    portCode: null,
    companyId: DEMO_COMPANY_ID,
    vesselIds: [],
  },
  VESSEL_OPERATOR: {
    id: "demo-vessel",
    email: "vessel@portwatch.demo",
    displayName: "R. Nayar",
    role: "VESSEL_OPERATOR",
    organisation: DEMO_COMPANY_NAME,
    portCode: null,
    companyId: DEMO_COMPANY_ID,
    vesselIds: ["PWD-001"],
  },
};

function fixtureFor(pathname: string): string | null {
  const route = pathname.replace(/^.*\/api/, "");
  const file = path.join(FIXTURES, `${route.replace(/^\//, "").replace(/\//g, "_") || "root"}.json`);
  return fs.existsSync(file) ? file : null;
}

/**
 * POST routes the suite replays.
 *
 * An agent run is a POST with a body, and recording one response per question
 * would make the fixture set a transcript. One recorded run is enough to assert
 * that the console renders a trace, a critic verdict and an agent chain -- which
 * is what the interface test is about.
 */
const POST_FIXTURES: Array<[RegExp, string]> = [
  [/\/scenarios\/simulate$/, "scenarios_simulate.json"],
  [/\/agents\/run$/, "agents_run.json"],
  [/\/learning\/run$/, "learning_run.json"],
];

/** Replay the recorded API. Anything not recorded answers 404, as the real one would. */
export async function mockApi(context: BrowserContext): Promise<void> {
  await context.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (request.method() === "POST") {
      const match = POST_FIXTURES.find(([pattern]) => pattern.test(url.pathname));
      const file = match ? path.join(FIXTURES, match[1]) : null;
      if (file && fs.existsSync(file)) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: fs.readFileSync(file, "utf8"),
        });
        return;
      }
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({
          detail: `No POST fixture recorded for ${url.pathname}`,
        }),
      });
      return;
    }

    const file = fixtureFor(url.pathname);
    if (!file) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: `No fixture recorded for ${url.pathname}` }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: fs.readFileSync(file, "utf8"),
    });
  });
}

/** Make every API call fail, the way a stopped backend does. */
export async function killApi(context: BrowserContext): Promise<void> {
  await context.unrouteAll({ behavior: "ignoreErrors" });
  await context.route("**/api/**", (route) => route.abort("connectionrefused"));
}

export async function seedSession(context: BrowserContext, role: Role): Promise<void> {
  const now = Date.now();
  await context.addInitScript(
    ([session, viewAs]) => {
      window.localStorage.setItem("portwatch.session.v1", session as string);
      window.localStorage.setItem("portwatch.viewAs.v1", viewAs as string);
    },
    [
      JSON.stringify({
        user: ACCOUNTS[role],
        mode: "demo",
        issuedAt: new Date(now).toISOString(),
        expiresAt: new Date(now + 12 * 3_600_000).toISOString(),
      }),
      JSON.stringify(role),
    ],
  );
}

export interface Recorder {
  consoleErrors: string[];
  failedRequests: string[];
  pageErrors: string[];
}

export function record(page: Page): Recorder {
  const recorder: Recorder = { consoleErrors: [], failedRequests: [], pageErrors: [] };
  page.on("console", (message) => {
    if (message.type() === "error") recorder.consoleErrors.push(message.text().slice(0, 300));
  });
  page.on("pageerror", (error) => recorder.pageErrors.push(String(error).slice(0, 300)));
  page.on("requestfailed", (request) => {
    const reason = request.failure()?.errorText ?? "";
    // An aborted request is the browser cancelling work the page no longer
    // needs (a navigation away, a prefetch); it is not a fault.
    if (reason.includes("ERR_ABORTED")) return;
    recorder.failedRequests.push(`${request.url()} ${reason}`);
  });
  return recorder;
}

/**
 * Wait for hydration. Every guarded route server-renders a session gate, so a
 * screenshot or an assertion before the effects run tests nothing.
 */
export async function settle(page: Page): Promise<void> {
  await page.waitForFunction(
    () => !/Restoring session|Checking session/i.test(document.body.innerText),
    undefined,
    { timeout: 30_000 },
  );
  await page.waitForTimeout(400);
}

export async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
}

/** `test` with the API replayed for every case. */
export const test = base.extend<{ recorder: Recorder }>({
  context: async ({ context }, use) => {
    await mockApi(context);
    await use(context);
  },
  recorder: async ({ page }, use) => {
    await use(record(page));
  },
});

export { expect } from "@playwright/test";
