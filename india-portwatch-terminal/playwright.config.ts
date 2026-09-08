import { defineConfig, devices } from "@playwright/test";

/**
 * Browser regression suite.
 *
 * It drives the production build, not the dev server, because the dev server
 * carries instrumentation the shipped bundle does not and would mask exactly
 * the class of fault this suite exists to catch.
 *
 * Two viewports run every spec: 1920×1080 is the design target, and 1366×768
 * is the smallest supported operating resolution -- the one where a table or a
 * rail is most likely to push the page sideways.
 */

const PORT = Number(process.env.PW_PORT ?? 4173);
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./qa/tests",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  // Every screen creates a WebGL context; too many at once starves the
  // software renderer and turns real assertions into timeouts.
  workers: process.env.CI ? 2 : 3,
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
