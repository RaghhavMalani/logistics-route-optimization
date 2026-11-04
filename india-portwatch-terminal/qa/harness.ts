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
import { randomUUID } from "node:crypto";
import { test as base, type BrowserContext, type Page } from "@playwright/test";

const FIXTURES = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "fixtures",
);

export type Role =
  "VESSEL_OPERATOR" | "SHIPPING_COMPANY" | "PORT_AUTHORITY" | "NATIONAL_ADMIN";

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

function fixtureSession(role: Role, mode: "production" | "demo") {
  return {
    user: ACCOUNTS[role],
    mode,
    issuedAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 12 * 3_600_000).toISOString(),
    accessToken: `playwright-${randomUUID()}`,
    ...(mode === "demo" ? { demoId: randomUUID() } : {}),
  };
}

/**
 * Routes whose last segment is an identifier the backend generated.
 *
 * A cascade is addressed by event id and an attention item by a composite key,
 * neither of which is stable across an ingest. Recording one file per id would
 * make the fixture set a matrix that goes stale the first time the feed moves,
 * so one representative response is recorded and served for the shape.
 */
const GET_FALLBACKS: Array<[RegExp, string]> = [
  [/\/world\/cascades\/.+$/, "world_cascade_detail.json"],
  [/\/attention\/.+$/, "attention_item.json"],
];

function fixtureFor(pathname: string): string | null {
  const route = pathname.replace(/^.*\/api(?:\/demo\/terminal)?/, "");
  const file = path.join(
    FIXTURES,
    `${route.replace(/^\//, "").replace(/\//g, "_") || "root"}.json`,
  );
  if (fs.existsSync(file)) return file;

  const fallback = GET_FALLBACKS.find(([pattern]) => pattern.test(route));
  if (!fallback) return null;
  const shaped = path.join(FIXTURES, fallback[1]);
  return fs.existsSync(shaped) ? shaped : null;
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
  const demos = new Map<string, ReturnType<typeof fixtureSession>>();
  await context.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const token = request.headers().authorization?.replace(/^Bearer /, "");
    if (url.pathname.endsWith("/api/auth/login") && method === "POST") {
      await route.fulfill({
        status: 401,
        json: { detail: "Invalid credentials" },
      });
      return;
    }
    if (url.pathname.endsWith("/api/demo/session")) {
      if (method === "POST") {
        const role = request.postDataJSON()?.role as Role;
        if (Object.hasOwn(ACCOUNTS, role)) {
          const session = fixtureSession(role, "demo");
          demos.set(session.accessToken, session);
          await route.fulfill({ json: session });
          return;
        }
      }
      const session = token && demos.get(token);
      await route.fulfill(
        session
          ? { json: session }
          : { status: 401, json: { detail: "Invalid demo session" } },
      );
      return;
    }
    if (url.pathname.endsWith("/api/demo/logout") && method === "POST") {
      if (token) demos.delete(token);
      await route.fulfill({ json: {} });
      return;
    }

    if (method === "POST") {
      const match = POST_FIXTURES.find(([pattern]) =>
        pattern.test(url.pathname),
      );
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
        body: JSON.stringify({
          detail: `No fixture recorded for ${url.pathname}`,
        }),
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

/**
 * Replace one recorded route with another fixture, from now on.
 *
 * Playwright serves the most recently registered matching route first, so a
 * test can move the API from one recorded state to the next -- the replay
 * deployment to a live feed to a stale one -- without restarting anything.
 * The fixture is a real recording of the real API in that state; see
 * `qa/record-ais-states.py`.
 */
export async function withFixture(
  context: BrowserContext,
  pathname: string,
  file: string,
): Promise<void> {
  const body = fs.readFileSync(path.join(FIXTURES, file), "utf8");
  await context.route(
    (url) => url.pathname.endsWith(pathname),
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body,
      });
    },
  );
}

/**
 * Ask the terminal to re-read its polled sources now.
 *
 * The health strip and the observed tracks refetch whenever the tab becomes
 * visible, so the suite does not have to wait out a thirty-second poll to see
 * a state change land.
 */
export async function refocus(page: Page): Promise<void> {
  await page.evaluate(() => {
    window.dispatchEvent(new Event("portwatch:signals-refresh"));
  });
}

/** Make every API call fail, the way a stopped backend does. */
export async function killApi(context: BrowserContext): Promise<void> {
  await context.unrouteAll({ behavior: "ignoreErrors" });
  await context.route("**/api/**", (route) => route.abort("connectionrefused"));
}

export async function seedSession(
  context: BrowserContext,
  role: Role,
): Promise<void> {
  // Recorded operational fixtures use verified account routes. Visitor demo
  // entry, role switching and expiry are covered separately via normal sign-in.
  const session = fixtureSession(role, "production");
  const authorization = `Bearer ${session.accessToken}`;
  let active = true;
  await context.route("**/api/auth/session", async (route) => {
    const request = route.request();
    const verified =
      active &&
      request.method() === "GET" &&
      request.headers().authorization === authorization;
    await route.fulfill(
      verified
        ? { json: session }
        : { status: 401, json: { detail: "Invalid fixture session" } },
    );
  });
  await context.route("**/api/auth/logout", (route) => {
    const request = route.request();
    if (
      request.method() === "POST" &&
      request.headers().authorization === authorization
    ) {
      active = false;
    }
    return route.fulfill({ json: {} });
  });
  await context.addInitScript(
    ({ session, role }) => {
      // Both storage keys are seeded because Playwright can drive either the
      // local fixture build or the production-auth build of the same client.
      for (const storage of [window.localStorage, window.sessionStorage]) {
        storage.setItem("portwatch.session.v1", JSON.stringify(session));
        storage.setItem("portwatch.viewAs.v1", JSON.stringify(role));
      }
    },
    { session, role },
  );
}

export interface Recorder {
  consoleErrors: string[];
  failedRequests: string[];
  pageErrors: string[];
}

export function record(page: Page): Recorder {
  const recorder: Recorder = {
    consoleErrors: [],
    failedRequests: [],
    pageErrors: [],
  };
  page.on("console", (message) => {
    if (message.type() === "error")
      recorder.consoleErrors.push(message.text().slice(0, 300));
  });
  page.on("pageerror", (error) =>
    recorder.pageErrors.push(String(error).slice(0, 300)),
  );
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
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
}

/** `test` with the API replayed for every case. */
export const test = base.extend<{ recorder: Recorder }>({
  context: async ({ context }, provide) => {
    await mockApi(context);
    await provide(context);
  },
  recorder: async ({ page }, provide) => {
    await provide(record(page));
  },
});

export { expect } from "@playwright/test";
