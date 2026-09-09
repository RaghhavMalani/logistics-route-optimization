/**
 * The review set.
 *
 * Three workspaces at the three supported resolutions, against the production
 * build with the API replayed from fixtures. This is the artefact a visual
 * review looks at, and it is reproducible because the traffic replay is
 * anchored to the pipeline's forecast origin rather than the wall clock: the
 * same command a week from now produces the same fleet in the same places.
 *
 *   node qa/serve-build.mjs      # or qa/rebuild.mjs
 *   node qa/serve-mock.mjs
 *   node qa/shots.mjs
 */

import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const SIZES = process.env.SHOT_SIZES ?? "1920x1080,1440x900,1366x768";
const BASE = process.env.SHOT_BASE ?? "http://127.0.0.1:4180";
const OUT = process.env.SHOT_OUT ?? "qa/shots";

const RUNS = [
  { role: "ADMIN", routes: { "national-command": "/admin/radar" } },
  { role: "PORT_OPERATOR", routes: { "port-chennai": "/port/overview" } },
  { role: "VESSEL_OPERATOR", routes: { "vessel-konkan": "/vessel/overview" } },
];

for (const run of RUNS) {
  const result = spawnSync(process.execPath, ["qa/shoot.mjs"], {
    cwd: ROOT,
    stdio: "inherit",
    env: {
      ...process.env,
      SHOT_BASE: BASE,
      SHOT_OUT: OUT,
      SHOT_ROLE: run.role,
      SHOT_SIZES: SIZES,
      SHOT_SETTLE: process.env.SHOT_SETTLE ?? "5200",
      SHOT_ROUTES: JSON.stringify(run.routes),
    },
  });
  if (result.status !== 0) process.exit(result.status ?? 1);
}
