# Deployment

How PortWatch X runs in production, what state it holds, where that state
lives, and what was tested. The short version: the backend is a long-running
process with a world in memory, a freshness coordinator on a schedule and a
durable ledger on disk; it runs on a container host with a persistent volume,
never on a request-scoped function platform.

## 1. Shape

```
  browser ── https://india-portwatch.vercel.app
                │   the terminal: Vercel project `india-portwatch`, root directory
                │   india-portwatch-terminal, framework tanstack-start, SSR in a
                │   Vercel function, assets on the CDN; nothing stateful lives here
                │
                │  https, VITE_PORTWATCH_API_BASE = https://<api host>/api  (baked in at build)
                ▼
  API service ── uvicorn, ONE worker, long-running  (Dockerfile, port $PORT)
                 Render (render.yaml) or Railway (railway.json): one instance,
                 a persistent disk at /app/state, PORTWATCH_LICENCE_MODE stated
      │  in memory: world graph + cascades, freshness coordinator, branch
      │  registry, decision engine (last 64 problems), mission replays,
      │  agent runs, telemetry, AIS client
      ├── /app/state        MUST PERSIST   persistent volume (PORTWATCH_STATE_DIR)
      ├── /app/data/cache   CACHE          volume; rebuilt by the coordinator
      ├── /app/outputs      REBUILDABLE    volume or a pipeline run
      └── providers         GDELT/GDACS, Open-Meteo, IMF PortWatch, FRED, AISStream
```

Why not Vercel for the API: a function is created per request and discarded;
it cannot hold the world, run the coordinator's schedule, keep a websocket to
AISStream open, or write a ledger that the next request reads. Until
2026-09-16 the Vercel project `india-portwatch` built the root Dockerfile as
a container function, and the public domain answered with the API's JSON --
`degraded`, `not_ready`, no caches, the mode defaulting to COMMERCIAL. That
project now serves the terminal and nothing else (section 4.1); the API is
not deployed on Vercel at all.

The two halves are on different origins, so the API's CORS is pinned to the
terminal's: `PORTWATCH_CORS_REGEX` allows `https://india-portwatch.vercel.app`
and this team's preview URLs (`india-portwatch-*-flash2404s-projects.vercel.app`)
and nothing wider -- a regex, never `*`, with credentials. The terminal never
calls a relative `/api`: `VITE_PORTWATCH_API_BASE` is the API host, inlined
at build time, and a terminal built without it is a misconfiguration the
status strip shows as the API being unreachable.

## 2. State audit

| state | where | category | restart | concurrent workers | corruption |
|---|---|---|---|---|---|
| decision ledger (problems as computed, decisions, policies, event outcomes, learning rows, audit trail) | `$PORTWATCH_STATE_DIR/portwatch_ledger.db` (SQLite, WAL) | **MUST PERSIST** | survives | one connection under an RLock per process; WAL tolerates a second *reader* process, not a second writer -- hence one worker | refused at open by `PRAGMA quick_check`; `/api/health.durableStores.ledger.error` names the file; ledger routes answer 503; nothing is started in its place |
| advisory register + audit trail | `$PORTWATCH_STATE_DIR/portwatch_advisories.db` (SQLite, WAL) | **MUST PERSIST** | survives | as above | as above (`durableStores.advisories`) |
| operator cost assumptions (`POST /finance/assumptions`) | `$PORTWATCH_STATE_DIR/cost_assumptions.jsonl`, append-only | **MUST PERSIST** | reloaded into the engine's basis at start, still labelled ASSUMPTION with who entered them | append under the request; one writer | an unreadable line fails the probe with its line number |
| AIS observation recorder | `PORTWATCH_AIS_RECORD_PATH` (JSON lines) when set | MUST PERSIST when recording is on | survives | one client per process | n/a |
| mission runs (replay clock, choices, reveal) | process memory (`_REPLAYS`) | EPHEMERAL OK | lost; the operator reopens the mission. Every replay decision is in the ledger | per process | n/a |
| decision engine memory (last 64 problems, branch registry) | process memory | EPHEMERAL OK | lost; `GET /decisions/problems[/{id}]` serves the ledger's record (`restoredFromLedger: true`); a restored problem cannot be moved through the workflow (409: recompute on the world as it is now) because it was pinned to a world revision this process has not rebuilt | per process | n/a |
| world graph, cascades, attention queue | process memory, built from the caches | REBUILDABLE | rebuilt from `data/cache` to the same revision fingerprint (tested) | per process | a corrupt cache file is a 503 with the file named; freshness says MISSING with the reason |
| provider caches (event register `news_bundle.json`, marine grid, port forecasts, macro, weather) | `data/cache/` | CACHE | survive on a volume; otherwise refetched by the coordinator within each artifact's SLA | one coordinator per process | as above |
| pipeline artefacts (forecasts, regimes, benchmark) | `outputs/` | REBUILDABLE | a pipeline run recreates them | n/a | verified by `scripts/verify_artefacts.py` |
| telemetry, agent runs | process memory | EPHEMERAL OK | lost | per process | n/a |

Set `PORTWATCH_STATE_DIR` to a mounted volume. Unset, it is `outputs/`, which
works for a checkout and is a warning on `/api/admin/readiness`
(`storage:state_dir`). `/api/health.durableStores` reports the directory in
force, how it was chosen, and each store's probe.

## 3. Concurrency

One uvicorn worker per deployment, stated in the Dockerfile's `CMD` and the
compose file. The world, the coordinator, the branch registry and the
engine's memory are per process; two workers would hold two worlds and
answer the same question differently, and two SQLite writers on one file are
a lock contest. Scale vertically. A read replica of the ledger is possible
(WAL allows readers) but is not part of this release.

## 4. Running it

Docker Compose, the reference long-running deployment:

```bash
PORTWATCH_LICENCE_MODE=DEMO docker compose up --build -d pipeline api terminal
docker compose --profile live up -d refresher      # optional: pipeline refresh on a cadence
```

The `state` volume is the one to back up. `pipeline` runs once and exits;
`api` waits for it; `terminal` is the node preset of the build with
`VITE_PORTWATCH_API_BASE` baked in.

Any container host that runs one always-on container with a persistent
volume works the same way: mount the volume at `/app/state`, set
`PORTWATCH_LICENCE_MODE`, `PORTWATCH_CORS_REGEX` (the exact terminal origin)
and, for RESEARCH, `AISSTREAM_API_KEY`; keep one instance; point the health
check at `/api/health`. A scale-to-zero platform must be configured not to
scale to zero (min instances 1, CPU always allocated) or the coordinator and
the AIS client stop between requests.

Without a container runtime, the same process runs under any supervisor:

```bash
PORTWATCH_STATE_DIR=/var/lib/portwatch PORTWATCH_LICENCE_MODE=DEMO \
  uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

`python -m portwatch.demo start --mode DEMO --detach` is the local form of
the same thing (validation, cache refresh, API on :8000, terminal on :8080).

### 4.1 The public deployment

**Terminal -- Vercel project `india-portwatch`** (owns
`india-portwatch.vercel.app`; git-linked to `main`):

| setting | value |
|---|---|
| Root Directory | `india-portwatch-terminal` |
| Framework Preset | TanStack Start (`india-portwatch-terminal/vercel.json` says the same, and sets `NITRO_PRESET=vercel` for the build) |
| Build | the framework default (`vite build` through `npm run build`); Nitro's Vercel preset writes `.vercel/output`: static assets on the CDN, one `__server` function for SSR |
| `VITE_PORTWATCH_API_BASE` | `https://india-portwatch-api.onrender.com/api` on production and preview |

The terminal makes every API call from the browser; the SSR function renders
shells and never talks to the API, so it holds nothing and needs no
credentials. A direct load of any route (`/admin/global-eye`, a refresh) is
answered by that function.

**API -- one long-running host.** `render.yaml` is the reference: a Docker
web service on the Starter plan (a Free instance sleeps after fifteen idle
minutes and takes the coordinator and the AIS client with it), one instance,
a 1 GB disk at `/app/state`, health check `/api/health`, region Singapore,
and the environment:

```
PORTWATCH_LICENCE_MODE=DEMO
PORTWATCH_STATE_DIR=/app/state
PORTWATCH_CORS_REGEX=^https://india-portwatch(-[a-z0-9-]+-flash2404s-projects)?\.vercel\.app$
```

`railway.json` is the same service for Railway (Dockerfile build, one
replica, health check, no sleeping); the volume at `/app/state` and the
three variables are set in Railway's dashboard, which has no file form for
them. On either host the first minutes after a deploy are `not ready`
while the coordinator fetches the register and the marine grid and runs the
port-forecast pipeline; `/api/admin/readiness` says which artefact is still
missing.

If the host assigns a different URL, set `VITE_PORTWATCH_API_BASE` on the
Vercel project to it and redeploy the terminal; nothing else refers to the
API's address.

## 5. What was tested

`scripts/demo_restart.py` starts a throwaway API on a fresh state directory,
operates it through the terminal's own routes, stops it and starts it again:

1. **Restart.** A port authority's decision is approved and handed off (one
   DRAFT advisory); a shipping company's decision is approved and its outcome
   recorded; a cost assumption is entered. After the restart: the ledger
   holds both problems with their workflow columns (`PROPOSED`, `OBSERVED`),
   the advisory is in the register, `/decisions/learning` still scores the
   outcome, the assumption is back in the basis with its author, and the
   world rebuilds from the same caches to the same revision fingerprint. The
   restored problem is served with `restoredFromLedger: true` and refuses a
   workflow move with 409 and the instruction to recompute.
2. **Corrupt ledger.** A state directory whose ledger file is not a database:
   `/api/health` is `degraded` with the fault and the path, every ledger
   route answers 503 saying nothing was substituted, `/api/admin/readiness`
   fails `store:ledger`, and the file is left untouched.
3. **Corrupt cache.** An event register cache that is not JSON: freshness
   reports the register MISSING with the reason, `/world/state` and
   `/world/cascades` answer 503 naming the file; no world is built from it.

`scripts/demo_failure.py` covers the provider failures (AIS credential
refused, financial rate missing, marine grid missing and unfetchable), and
the browser suite's `degraded.spec.ts` covers the terminal when the API is
unreachable. Together with `demo_restart.py` that is the fault matrix the
release candidate claims: provider down, backend restart, stale cache,
corrupt cache, database unavailable, frontend cut off from the API.

## 6. Not done in this release

- The API host is prepared, not provisioned: `render.yaml` and
  `railway.json` are ready to apply, but creating the service is a billable
  action on the owner's account. Until it exists the public terminal shows
  the API as unreachable on its status strip -- it does not fall back to the
  old Vercel container function, which was never a production backend. The
  workstation's Docker Desktop would not start (a stale `sailor-ingest.sock`
  it cannot remove without a reboot); the restart and failure tests ran
  against the same process under the same environment on this machine.
- PostgreSQL is not used. The ledger's SQL is SQLite's and the write volume
  is small; a migration would be a project of its own and nothing here needs
  it. The compose file's `infra` profile (PostgreSQL + Kafka) backs the
  research pipeline's optional path, not the ledger.
