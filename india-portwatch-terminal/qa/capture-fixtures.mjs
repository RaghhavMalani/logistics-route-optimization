/**
 * Capture the API surface the browser tests replay.
 *
 * The regression suite must not need a live backend, a live pipeline or a
 * network: it asserts that the *interface* behaves, and a test that fails
 * because GDELT was slow tells you nothing about the interface. So the
 * fixtures are a snapshot of a real run, recorded once and replayed by
 * `qa/mock-api.ts`.
 *
 * Re-record against a running backend with:
 *   node qa/capture-fixtures.mjs
 */

import fs from "node:fs";
import path from "node:path";

const BASE = process.env.PORTWATCH_API ?? "http://127.0.0.1:8000/api";
const OUT = path.join(import.meta.dirname, "fixtures");

/** Ports the suite navigates to; per-port artefacts are captured for these. */
const PORTS = ["INMAA", "INNSA", "INCOK"];

const GETS = [
  "/health",
  "/provenance",
  "/ports",
  "/ports/registry",
  "/model/pipeline",
  "/model/benchmark",
  "/weather",
  "/weather/intelligence",
  "/news",
  "/sar/vessels",
  "/sar/feed-adapters",
  "/fleet",
  "/scenarios",
  ...PORTS.flatMap((code) => [
    `/ports/${code}`,
    `/model/${code}/forecast`,
    `/model/${code}/regime`,
    `/model/${code}/decision`,
    `/model/${code}/chain`,
  ]),
];

function slug(route) {
  return route.replace(/^\//, "").replace(/\//g, "_") || "root";
}

fs.mkdirSync(OUT, { recursive: true });

const manifest = {};
for (const route of GETS) {
  const response = await fetch(BASE + route, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    console.warn(`skip ${route}: ${response.status}`);
    continue;
  }
  const body = await response.json();
  const file = `${slug(route)}.json`;
  fs.writeFileSync(path.join(OUT, file), JSON.stringify(body));
  manifest[route] = file;
  console.log(`${route} -> ${file}`);
}

// One propagated scenario, so the Scenario Room has an outcome to render.
const scenario = await fetch(`${BASE}/scenarios/simulate`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ scenarioKey: "HORMUZ", intensity: 1, runId: 0 }),
});
if (scenario.ok) {
  fs.writeFileSync(
    path.join(OUT, "scenarios_simulate.json"),
    JSON.stringify(await scenario.json()),
  );
  manifest["POST /scenarios/simulate"] = "scenarios_simulate.json";
  console.log("POST /scenarios/simulate -> scenarios_simulate.json");
}

fs.writeFileSync(path.join(OUT, "manifest.json"), JSON.stringify(manifest, null, 2));
console.log(`\n${Object.keys(manifest).length} fixtures written to ${OUT}`);
