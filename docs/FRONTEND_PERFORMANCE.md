# Frontend performance

Measured 2026-09-15 with `qa/perf-session.mjs` against the production build
(`NITRO_PRESET=node-server`, API base baked in, served by `qa/serve-build.mjs`
on :4173) and the real API on :8000, in headed Chromium at 1920×1080 on the
same workstation as `PERFORMANCE.md` (i7-14650HX, GPU rendering). Headless
Chromium renders the WebGL chart in software at a few frames a second, so
none of the interaction figures below can be taken headless.

Raw reports: `docs/qa/perf/session.json` (the run that stands) and
`docs/qa/perf/session-before-gcTime.json` (the run that found the retention).

## Initial load — Global Eye

| measure | figure |
|---|---:|
| TTFB | 5–15 ms |
| DOMContentLoaded | 169–272 ms |
| load event | 269–366 ms |
| map first render (style loaded, "INITIALISING CHART" gone) | 362–597 ms |
| scripts fetched | 35 files, 2.8 MB transferred (2.8 MB decoded) |
| all resources | 50 files, 2.98 MB |

The bundle is served uncompressed by the node preset: transferred equals
decoded. Behind a CDN or a reverse proxy with compression the script
transfer is roughly a third of that; the largest chunks are `maplibre-gl`
(1,003 KB), the traffic context and replay (787 KB), the port twin scene
(545 KB, lazy) and the map component (448 KB).

## Interactions

| interaction | latency |
|---|---:|
| open a decision (click on the action rail → panel drawn) | 292–321 ms |
| switch option (branch redraw on the water) | 165–172 ms |
| Robust tab (regret table, picks, gate) | 200–219 ms |
| cascade play | 2.5 s animation by design; the button responds at once |
| scenario screen (navigate) | 119–170 ms |
| mission screen + switch to the second mission | 260–329 ms |

Decision latency is dominated by `POST /api/decisions/problems` (p95 64 ms
in-process; the rest is the fetch, the render and the branch geometry on the
chart).

## The fifteen-minute session

The loop: select an event row → open the first decision → switch to another
option → toggle Compare → close → repeat, sampling every 30 s: JS heap, DOM
nodes, JS event listeners (CDP `Performance.getMetrics`), and the chart's
layer and source counts (`__portwatchMap.getStyle()`).

**Run 1 (no forced GC, decision cache kept for 30 min):** 318 cycles. Heap
78 → 125 MB with a 4.3 MB/min slope after warm-up; listeners 4k → 15k in a
sawtooth with the heap; DOM nodes 1,100–1,800; **map layers 39 → 39, sources
20 → 20**. The chart leaked nothing. The climb was the query cache: a decision
problem is ~80 KB of JSON and `gcTime` kept every opened problem for thirty
minutes.

**Run 2 (forced GC before every sample, `gcTime` 5 min):** 828 cycles.
Post-GC heap 22 MB at the start, climbing ~110 KB per opened decision to
**53.9 MB at five minutes and flat from there** (53.7 MB at 5:36, 6:07,
6:37, 7:07 … to the end); listeners 309–372 throughout; DOM nodes
1,127–1,156; layers 39, sources 20. The retention is bounded by the cache's
own lifetime and plateaus at the number of decisions an operator can open in
five minutes — here one every second, which no operator does.

What was changed from the finding: `src/services/decisions.ts` keeps a
closed decision problem for five minutes instead of thirty (it is pinned to
a world revision and never changes while on screen; reopening it is one
round trip the API answers from memory or the ledger).

## Budgets

Set from the figures above, checked by re-running the session script:

| budget | ceiling | measured |
|---|---:|---:|
| load event | 1,000 ms | 269–366 ms |
| map first render | 1,500 ms | 362–597 ms |
| open a decision | 750 ms | 292–321 ms |
| switch option | 400 ms | 165–172 ms |
| 15-minute session, post-GC heap slope after the cache warms | 0 MB/min | 0 MB/min (plateau at 5 min) |
| map layers and sources over the session | unchanged | unchanged |

These are not in ordinary CI: they need a GPU and the real API. Run
`node qa/perf-session.mjs --gc` before a release.
