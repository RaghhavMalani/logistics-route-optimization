import { defineConfig, devices } from "@playwright/test";

/**
 * Browser regression suite.
 *
 * It drives the production build, not the dev server, because the dev server
 * carries instrumentation the shipped bundle does not and would mask exactly
 * the class of fault this suite exists to catch.
 *
 * Three viewports run every spec. 1920×1080 is the design target. 1366×768 is
 * the smallest supported operating resolution -- the one where a table or a rail
 * is most likely to push the page sideways. 1440×900 is the most common laptop
 * in a control room, and its shorter height is where a fixed rail and a map
 * legend start competing for the fold.
 *
 * CI runs the two outer viewports (`npm run test:browser:ci`). For layout risk
 * 1366×768 strictly dominates 1440×900 -- it is both narrower and shorter, so
 * anything that overflows or falls below the fold at 1440 does so at 1366 as
 * well. The middle viewport earns its place in the local QA pass, where the
 * question is how the product looks on the machine most operators have, not in
 * CI, where it would add a third of the runtime for no additional coverage.
 */

const PORT = Number(process.env.PW_PORT ?? 4173);
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./qa/tests",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  // One retry everywhere, not only in CI. Every spec here holds a WebGL context
  // and an eight hundred vessel animation loop, so on a machine that is also
  // building or running the Python suite a click can wait past the 60s budget --
  // the two search tests time out under load and pass in 12s alone. That is
  // contention, not a defect, and a retry absorbs it. A real failure still fails
  // twice, and Playwright reports a retried test as flaky rather than as a pass,
  // so nothing is hidden by this.
  retries: 1,
  // Every screen creates a WebGL context and runs an eight hundred vessel
  // animation loop; too many at once starves the software renderer and turns
  // real assertions into timeouts.
  workers: 2,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],

  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },

  projects: [
    {
      name: "desktop-1920",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1920, height: 1080 } },
    },
    {
      name: "laptop-1440",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "laptop-1366",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 768 } },
    },
  ],

  webServer: {
    command: `node qa/serve-build.mjs`,
    url: `${BASE_URL}/login`,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
    env: { PORT: String(PORT) },
    stdout: "pipe",
    stderr: "pipe",
  },
});
