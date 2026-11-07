import { expect, seedSession, settle, test, type Role } from "../harness";
import fs from "node:fs";

for (const [role, path] of [
  ["SHIPPING_COMPANY", "/company/overview"],
  ["PORT_AUTHORITY", "/port/overview"],
  ["VESSEL_OPERATOR", "/vessel/overview"],
  ["NATIONAL_ADMIN", "/admin/radar"],
] as [Role, string][]) {
  test(`${role} shows one source pulse with honest retained states`, async ({ context, page }) => {
    await page.clock.setFixedTime(new Date("2026-11-06T12:00:00Z"));
    await seedSession(context, role);
    await page.goto(path);
    await settle(page);
    const pulse = page.getByTestId("live-pulse");
    await expect(pulse).toHaveCount(1);
    await expect(pulse.locator('[data-source="imf-portwatch-data"]')).toHaveAttribute("data-status", "stale");
    await expect(pulse.locator('[data-source="aisstream-websocket"]')).toHaveAttribute("data-status", "unavailable");
    await expect(page.getByTestId("weather-offset")).toHaveText("Latest available");
    await expect(page.getByRole("button", { name: "NOW", exact: true })).toHaveCount(0);
    await expect(page.getByTestId('dated-source-imf-portwatch-data').first()).toContainText('Latest available');
  });
}

test("login and Sources expose degradation, source dates and unmeasured rates", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-11-06T12:00:00Z"));
  await page.goto("/login");
  await expect(page.getByTestId("login-source-freshness")).toHaveText("Degraded · latest available data");
  await page.goto("/sources");
  await expect(page.getByTestId("source-latest-available")).toHaveCount(3);
  await expect(page.getByText("Unmeasured", { exact: true }).first()).toBeVisible();
});

test("leaving the last workspace stream resumes Sources polling", async ({ context, page }) => {
  const sources = JSON.parse(fs.readFileSync(new URL('../fixtures/public_sources.json', import.meta.url), 'utf8'));
  await page.clock.install({ time: new Date('2026-11-06T12:00:00Z') });
  let reads = 0;
  let documents = 0;
  page.on('request', (request) => { if (request.isNavigationRequest() && request.resourceType() === 'document') documents += 1; });
  await context.route('**/api/public/sources', (route) => {
    reads += 1;
    return route.fulfill({ json: sources });
  });
  await page.addInitScript((payload) => {
    const original = window.fetch.bind(window);
    window.fetch = (input, options) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.endsWith('/handoffs/stream')) {
        const stream = new ReadableStream({ start(controller) {
          const frame = 'event: handoffs\ndata: {"items":[]}\n\nevent: sources\ndata: ' + JSON.stringify(payload) + '\n\n';
          controller.enqueue(new TextEncoder().encode(frame));
          options?.signal?.addEventListener('abort', () => controller.close(), { once: true });
        } });
        return Promise.resolve(new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } }));
      }
      return original(input, options);
    };
  }, sources);
  await seedSession(context, 'SHIPPING_COMPANY');
  await page.goto('/company/overview');
  await settle(page);
  await expect(page.getByTestId('live-pulse')).toBeVisible();
  const connectedReads = reads;
  await page.clock.fastForward(31_000);
  expect(reads).toBe(connectedReads);
  // Client navigation preserves the document/query cache, then tears down SSE.
  await page.getByTestId('live-pulse').getByRole('link', { name: 'Sources', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Sources', exact: true })).toBeVisible();
  expect(documents).toBe(1);
  const before = reads;
  await page.clock.fastForward(31_000);
  await expect.poll(() => reads).toBeGreaterThan(before);
});
