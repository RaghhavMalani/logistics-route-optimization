/**
 * Stop whatever is holding the preview port.
 *
 * `qa/serve-build.mjs` keeps running between test runs on purpose -- the
 * Playwright config sets `reuseExistingServer` outside CI, so a local run does
 * not pay for a rebuild every time. The cost is that the running server holds a
 * handle on `.output`, and on Windows `vite build` then fails with EBUSY while
 * trying to clear it.
 *
 * So: before a rebuild, stop the server. `pkill` matching on the command line is
 * unreliable through Git Bash on Windows, so this asks the OS which process owns
 * the port and stops that one, which is exact.
 *
 *   node qa/stop-preview.mjs
 */

import { execSync } from "node:child_process";

const PORT = Number(process.env.PW_PORT ?? 4173);

function pidsOnPort(port) {
  try {
    if (process.platform === "win32") {
      const out = execSync(`netstat -ano -p tcp`, { encoding: "utf8" });
      return [
        ...new Set(
          out
            .split(/\r?\n/)
            .filter((line) => line.includes("LISTENING") && line.includes(`:${port} `))
            .map((line) => line.trim().split(/\s+/).pop())
            .filter((pid) => pid && pid !== "0"),
        ),
      ];
    }
    const out = execSync(`lsof -ti tcp:${port}`, { encoding: "utf8" });
    return out.split(/\s+/).filter(Boolean);
  } catch {
    // No listener, or the tool is unavailable. Either way there is nothing to do.
    return [];
  }
}

const pids = pidsOnPort(PORT);
if (!pids.length) {
  console.log(`nothing listening on ${PORT}`);
  process.exit(0);
}

for (const pid of pids) {
  try {
    if (process.platform === "win32") {
      execSync(`taskkill /PID ${pid} /F /T`, { stdio: "ignore" });
    } else {
      process.kill(Number(pid), "SIGTERM");
    }
    console.log(`stopped ${pid} on port ${PORT}`);
  } catch (error) {
    console.warn(`could not stop ${pid}: ${error.message}`);
  }
}
