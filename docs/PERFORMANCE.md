# Performance

Measured 2026-09-15T08:44:52+00:00 on supercomputer (Intel64 Family 6 Model 183 Stepping 1, GenuineIntel, 24 cores, Python 3.12.0, Windows 11). Produced by `python scripts/benchmark_performance.py`; every figure below is a measurement from that run, not a target.

Wall time is `time.perf_counter()` around the call; CPU is process time over the same block; peak memory is `tracemalloc`'s peak during the block (the work's own allocations, not the interpreter's). Synthetic worlds are seeded from the real lane catalogue and port registry so the graph has the shape the product's own graph has.

## World State build

| vessels | median | p95 | CPU | peak memory | nodes | edges |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 5.24 ms | 5.29 ms | 0.0 ms | 0.52 MB | 167 | 378 |
| 1000 | 49.7 ms | 51.61 ms | 46.88 ms | 1.91 MB | 1067 | 3008 |
| 5000 | 238.16 ms | 249.65 ms | 234.38 ms | 9.16 MB | 5067 | 14638 |
| 10000 | 503.57 ms | 505.36 ms | 500.0 ms | 18.25 MB | 10067 | 29176 |

| events (500 vessels) | median | p95 | CPU | peak memory | nodes |
|---:|---:|---:|---:|---:|---:|
| 100 | 22.54 ms | 23.29 ms | 31.25 ms | 1.04 MB | 627 |
| 1000 | 45.06 ms | 45.18 ms | 46.88 ms | 1.99 MB | 1527 |

## Cascade query

| vessels | one chokepoint: median | reached | every chokepoint (fanout): median | reached | peak memory |
|---:|---:|---:|---:|---:|---:|
| 100 | 0.05 ms | 1 | 5.79 ms | 85 | 0.18 MB |
| 1000 | 0.04 ms | 1 | 66.66 ms | 711 | 1.55 MB |
| 5000 | 0.05 ms | 1 | 122.49 ms | 2018 | 3.26 MB |
| 10000 | 0.05 ms | 1 | 187.15 ms | 2929 | 5.1 MB |

## Attention, decisions, scenarios, Critic

| stage | size | median | p95 | CPU | peak memory | note |
|---|---:|---:|---:|---:|---:|---|
| attention (NATIONAL, fanout cascade) | 100 vessels | 12.08 ms | 12.23 ms | 15.62 ms | 0.14 MB | 77 items ranked |
| attention (NATIONAL, fanout cascade) | 1000 vessels | 154.73 ms | 170.83 ms | 156.25 ms | 1.37 MB | 703 items ranked |
| attention (NATIONAL, fanout cascade) | 5000 vessels | 392.88 ms | 393.89 ms | 390.62 ms | 3.71 MB | 2010 items ranked |
| attention (NATIONAL, fanout cascade) | 10000 vessels | 703.25 ms | 782.67 ms | 687.5 ms | 5.36 MB | 2921 items ranked |
| DecisionProblem (vessel routing) | 100 vessels | 158.11 ms | 160.42 ms | 140.62 ms | 0.67 MB | 6 options, 6 feasible |
| DecisionProblem (vessel routing) | 1000 vessels | 404.5 ms | 409.15 ms | 390.62 ms | 13.55 MB | 6 options, 6 feasible |
| scenario branch + cascade | 1000 vessels | 30.0 ms | 30.33 ms | 15.62 ms | 0.88 MB | 308 nodes reached |
| Critic, every option | 6 options | 0.34 ms | 0.38 ms | 0.0 ms | 0.01 MB | 0.057 ms per option |

## Pareto frontier

| options | median | p95 | peak memory |
|---:|---:|---:|---:|
| 50 | 1.15 ms | 1.17 ms | 0.0 MB |
| 500 | 26.6 ms | 26.74 ms | 0.08 MB |
| 5000 | 499.86 ms | 501.06 ms | 0.79 MB |

## Historical mission replay

| mission | hulls | decide every hull + reveal: median | p95 | peak memory |
|---|---:|---:|---:|---:|
| suez-ever-given-2021 | 3 | 338.55 ms | 339.61 ms | 1.19 MB |
| gulf-of-kutch-biparjoy-2023 | 3 | 177.4 ms | 182.79 ms | 0.8 MB |

## API latency (in-process, real cache on disk)

| route | status | p50 | p95 | p99 | max | payload |
|---|---:|---:|---:|---:|---:|---:|
| `GET /api/health` | 200 | 2.1 ms | 3.1 ms | 3.2 ms | 3.4 ms | 1,464 B |
| `GET /api/world/state` | 200 | 5.7 ms | 6.4 ms | 6.4 ms | 6.6 ms | 37,894 B |
| `GET /api/world/cascades` | 200 | 6.1 ms | 6.7 ms | 7.2 ms | 12.7 ms | 53,341 B |
| `GET /api/attention` | 200 | 6.7 ms | 7.3 ms | 7.6 ms | 8.3 ms | 10,910 B |
| `GET /api/global-eye/events` | 200 | 5.2 ms | 5.5 ms | 5.5 ms | 5.8 ms | 32,511 B |
| `GET /api/fabric/health?mode=DEMO` | 200 | 2.8 ms | 3.1 ms | 4.1 ms | 43.0 ms | 3,323 B |
| `GET /api/admin/freshness` | 200 | 4.6 ms | 5.3 ms | 5.5 ms | 23.6 ms | 8,222 B |
| `GET /api/missions` | 200 | 1.0 ms | 1.3 ms | 1.3 ms | 1.6 ms | 1,423 B |
| `GET /api/decisions/actions` | 200 | 1.0 ms | 1.2 ms | 1.2 ms | 1.5 ms | 7,287 B |
| `POST /api/decisions/problems` | 200 | 55.6 ms | 70.9 ms | 88.0 ms | 104.1 ms | 72,441 B |

## Reading the numbers

- World build scales close to linearly in vessels: 100x the hulls cost 96.1x the time.
- The large-fanout cascade over 10000 hulls reaches 2929 nodes in 187.15 ms; the cascade is bounded by the graph it can reach, not by the fleet.
- `POST /api/decisions/problems` is the slowest call at p95 70.9 ms (72,441 B); it computes a decision problem, simulating every option on its own branch.
- `GET /api/attention` is the slowest read at p95 7.3 ms (10,910 B); reads are served from the versioned live world, so repeated calls at one revision reuse the build.
- Timings move with host load: the previous publication of this page, taken while a browser suite ran on the same machine, was three to five times slower on every row. Compare runs on an idle host.
- Decision problems, scenarios and the Critic are all under the interactive budget on this machine; the pipeline (minutes) is the only slow path and it runs out of process under the freshness coordinator.
