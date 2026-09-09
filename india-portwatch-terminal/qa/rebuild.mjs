/**
 * Stop the preview server, rebuild, start it again.
 *
 * Windows holds `.output` open while the node server is running, so a rebuild
 * fails with EBUSY unless the server is stopped first. This does the three
 * steps in the right order so an iteration loop is one command.
 *
 *   node qa/rebuild.mjs
 */

import { spawn, spawnSync } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PORT = Number(process.env.PW_PORT ?? 4173);

function stopPortOwners(port) {
  if (process.platform !== "win32") return;
  // PowerShell rather than parsing netstat: the table's columns and the word
  // "LISTENING" are locale-dependent, and this has to work on any install.
  const script = `Get-NetTCPConnection -State Listen -LocalPort ${port} -ErrorAction SilentlyContinue | ` +
    `Select-Object -ExpandProperty OwningProcess -Unique | ` +
    `ForEach-Object { Write-Output $_; Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }`;
  const result = spawnSync("powershell", ["-NoProfile", "-Command", script], { encoding: "utf8" });
  const stopped = (result.stdout ?? "").trim();
  if (stopped) console.log(`stopped pid(s) ${stopped.split(/\s+/).join(", ")} on port ${port}`);
}

stopPortOwners(PORT);

await new Promise((resolve) => setTimeout(resolve, 500));

const build = spawnSync("npm", ["run", "build"], {
  cwd: ROOT,
  env: {
    ...process.env,
    NITRO_PRESET: "node-server",
    // `.env.local` points a developer's build at a live backend on :8000. The
    // QA build must talk to whatever is serving it, so the replayed fixtures in
    // `serve-mock.mjs` answer instead of a machine-specific service.
    VITE_PORTWATCH_API_BASE: process.env.VITE_PORTWATCH_API_BASE ?? "/api",
  },
  stdio: "inherit",
  shell: process.platform === "win32",
});
if (build.status !== 0) process.exit(build.status ?? 1);

const server = spawn(process.execPath, ["./server/index.mjs"], {
  cwd: path.join(ROOT, ".output"),
  env: { ...process.env, PORT: String(PORT), HOST: "127.0.0.1" },
  detached: true,
  stdio: "ignore",
});
server.unref();

const waitFor = async () => {
  for (let i = 0; i < 60; i += 1) {
    const open = await new Promise((resolve) => {
      const socket = net.connect(PORT, "127.0.0.1");
      socket.on("connect", () => {
        socket.end();
        resolve(true);
      });
      socket.on("error", () => resolve(false));
    });
    if (open) return true;
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  return false;
};

console.log((await waitFor()) ? `server up on ${PORT}` : `server never came up on ${PORT}`);
