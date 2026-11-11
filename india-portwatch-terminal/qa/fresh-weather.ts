import fs from "node:fs";
import { fileURLToPath } from "node:url";
import type { BrowserContext, Page } from "@playwright/test";

/** Pin the browser clock to the recorded observation when testing the current cursor. */
export async function freshWeatherFixture(page: Page, context: BrowserContext) {
  const weather = JSON.parse(fs.readFileSync(fileURLToPath(new URL("./fixtures/weather.json", import.meta.url)), "utf8"));
  const at = new Date(weather[0].observedAt + "Z");
  await page.clock.setFixedTime(at);
  const sources = JSON.parse(fs.readFileSync(fileURLToPath(new URL("./fixtures/public_sources.json", import.meta.url)), "utf8"));
  sources.checkedAt = at.toISOString();
  sources.degraded = false;
  for (const source of sources.sources) {
    if (source.core) {
      source.status = "live";
      source.dataAgeSeconds = 0;
      source.portsCurrent = source.portsTotal;
    }
  }
  await context.route("**/api/public/sources", (route) => route.fulfill({ json: sources }));
}
