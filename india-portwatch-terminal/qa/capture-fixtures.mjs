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

/**
 * Query-string routes are recorded under a slug that includes the query, so the
 * replayer can key on the pathname alone. The company and cargo surfaces all
 * take a port or a horizon, and recording one representative call each is what
 * keeps the fixture set a snapshot rather than a matrix.
 */
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
  // The agentic maritime OS surfaces.
  "/global-eye/events",
  "/global-eye/exposure",
  "/global-eye/calibration",
  "/company",
  "/company/fleet",
  "/company/risk",
  "/company/routes",
  "/advisories/policy",
  "/agents",
  // The boundary screen lists every level, including the one no agent may
  // reach, so the catalogue is captured at the EXECUTE ceiling.
  "/agents/tools?max_access=EXECUTE",
  "/agents/intents",
  "/learning/summary",
  "/learning/reliability",
  "/learning/misses",
  "/learning/policies",
  "/learning/calibration",
  ...PORTS.flatMap((code) => [
    `/port-twin/${code}`,
    `/port-twin/${code}/simulate`,
    `/port-twin/${code}/optimize`,
  ]),
  "/cargo/optimize?port_code=INMAA",
  "/cargo/opportunities?port_code=INMAA",
  ...PORTS.flatMap((code) => [
    `/ports/${code}`,
    `/model/${code}/forecast`,
    `/model/${code}/regime`,
    `/model/${code}/decision`,
    `/model/${code}/chain`,
  ]),
];

function slug(route) {
  // The replayer keys on the pathname, so the query is dropped here. Only one
  // representative call per route is recorded; a fixture set that varied by
  // query string would be a matrix rather than a snapshot.
  const [pathname] = route.split("?");
  return pathname.replace(/^\//, "").replace(/\//g, "_") || "root";
}

fs.mkdirSync(OUT, { recursive: true });

/**
 * POST routes recorded with one representative body each. The agent console is
 * an interface test, not a model test: one recorded run proves the trace, the
 * critic block and the agent chain render.
 */
const POSTS = [
  ["/agents/run", { question: "Which vessels require action because of Red Sea risk?" }],
  ["/learning/run", {}],
];

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

/**
 * The advisory register is identity-scoped, so it is captured as the demo port
 * controller. The replayer serves the same file to every role, which is fine
 * for an interface test: what the suite asserts is that the register renders
 * and that the action buttons match the state machine, not that the server
 * filtered correctly -- that is a Python test.
 */
const advisories = await fetch(`${BASE}/advisories`, {
  headers: {
    Accept: "application/json",
    "X-PortWatch-Actor": "S. Iyer",
    "X-PortWatch-Role": "PORT_AUTHORITY",
    "X-PortWatch-Port": "INMAA",
  },
});
if (advisories.ok) {
  fs.writeFileSync(
    path.join(OUT, "advisories.json"),
    JSON.stringify(await advisories.json()),
  );
  manifest["/advisories"] = "advisories.json";
  console.log("/advisories -> advisories.json");
}

for (const [route, body] of POSTS) {
  const response = await fetch(BASE + route, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    console.warn(`skip POST ${route}: ${response.status}`);
    continue;
  }
  const file = `${slug(route)}.json`;
  fs.writeFileSync(path.join(OUT, file), JSON.stringify(await response.json()));
  manifest[`POST ${route}`] = file;
  console.log(`POST ${route} -> ${file}`);
}

fs.writeFileSync(path.join(OUT, "manifest.json"), JSON.stringify(manifest, null, 2));
console.log(`\n${Object.keys(manifest).length} fixtures written to ${OUT}`);
