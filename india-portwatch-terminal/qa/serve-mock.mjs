/**
 * The production build, with the API replayed from fixtures.
 *
 * The browser suite intercepts requests inside the page, which is right for a
 * test but useless for looking at the thing. This serves the same recorded
 * artefacts over HTTP in front of the real server-rendered bundle, so a browser
 * -- or a screenshot run -- sees exactly what CI sees without a Python backend,
 * a network, or a live pipeline.
 *
 *   node qa/serve-build.mjs            # the bundle, port 4173
 *   node qa/serve-mock.mjs             # this proxy, port 4180
 */

import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const FIXTURES = path.join(ROOT, "qa", "fixtures");

const PORT = Number(process.env.MOCK_PORT ?? 4180);
const UPSTREAM_PORT = Number(process.env.PW_PORT ?? 4173);
const UPSTREAM_HOST = process.env.PW_HOST ?? "127.0.0.1";

function fixtureFor(pathname) {
  const route = pathname.replace(/^.*\/api/, "");
  const name = route.replace(/^\//, "").replace(/\//g, "_") || "root";
  const file = path.join(FIXTURES, `${name}.json`);
  return fs.existsSync(file) ? file : null;
}

const server = http.createServer((request, response) => {
  const url = new URL(request.url ?? "/", `http://${request.headers.host ?? "localhost"}`);

  if (url.pathname.startsWith("/api/")) {
    if (request.method === "POST" && url.pathname.endsWith("/scenarios/simulate")) {
      const body = fs.readFileSync(path.join(FIXTURES, "scenarios_simulate.json"));
      response.writeHead(200, { "content-type": "application/json" });
      response.end(body);
      return;
    }
    const file = fixtureFor(url.pathname);
    if (!file) {
      response.writeHead(404, { "content-type": "application/json" });
      response.end(JSON.stringify({ detail: `No fixture recorded for ${url.pathname}` }));
      return;
    }
    response.writeHead(200, { "content-type": "application/json" });
    response.end(fs.readFileSync(file));
    return;
  }

  const proxied = http.request(
    {
      host: UPSTREAM_HOST,
      port: UPSTREAM_PORT,
      method: request.method,
      path: request.url,
      headers: { ...request.headers, host: `${UPSTREAM_HOST}:${UPSTREAM_PORT}` },
    },
    (upstream) => {
      response.writeHead(upstream.statusCode ?? 502, upstream.headers);
      upstream.pipe(response);
    },
  );
  proxied.on("error", (error) => {
    response.writeHead(502, { "content-type": "text/plain" });
    response.end(`upstream ${UPSTREAM_HOST}:${UPSTREAM_PORT} unreachable: ${error.message}`);
  });
  request.pipe(proxied);
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`mock API + build proxy on http://127.0.0.1:${PORT} (upstream ${UPSTREAM_PORT})`);
});
