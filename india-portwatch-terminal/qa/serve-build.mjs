/**
 * Serve the production build for the browser regression suite.
 *
 * The default build targets Cloudflare, whose output cannot be started by
 * node, so the suite builds with the node-server preset first. That keeps the
 * tests honest: they drive the same server-rendered bundle that ships, not the
 * dev server with its extra instrumentation.
 *
 * `PW_SKIP_BUILD=1` reuses an existing .output when iterating locally.
 */

import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outDir = path.join(root, ".output");
const nitroJson = path.join(outDir, "nitro.json");

function currentPreset() {
  try {
    return JSON.parse(fs.readFileSync(nitroJson, "utf8")).preset;
  } catch {
    return null;
  }
}

function run(command, args, env) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: root,
      env: { ...process.env, ...env },
      stdio: "inherit",
      shell: process.platform === "win32",
    });
    child.on("exit", (code) =>
      code === 0 ? resolve() : reject(new Error(`${command} exited ${code}`)),
    );
    child.on("error", reject);
  });
}

const skip = process.env.PW_SKIP_BUILD === "1" && currentPreset() === "node-server";
if (!skip) {
  await run("npm", ["run", "build"], { NITRO_PRESET: "node-server" });
}

const server = spawn(process.execPath, ["./server/index.mjs"], {
  cwd: outDir,
  env: { ...process.env, PORT: process.env.PORT ?? "4173", HOST: "127.0.0.1" },
  stdio: "inherit",
});

const stop = () => {
  server.kill();
  process.exit(0);
};
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
server.on("exit", (code) => process.exit(code ?? 0));
