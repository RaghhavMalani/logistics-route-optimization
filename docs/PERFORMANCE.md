# Performance

Measured 2026-09-14T14:21:01+00:00 on supercomputer (Intel64 Family 6 Model 183 Stepping 1, GenuineIntel, 24 cores, Python 3.12.0, Windows 11). Produced by `python scripts/benchmark_performance.py`; every figure below is a measurement from that run, not a target.

Wall time is `time.perf_counter()` around the call; CPU is process time over the same block; peak memory is `tracemalloc`'s peak during the block (the work's own allocations, not the interpreter's). Synthetic worlds are seeded from the real lane catalogue and port registry so the graph has the shape the product's own graph has.

## World State build

| vessels | median | p95 | CPU | peak memory | nodes | edges |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 3.87 ms | 4.09 ms | 0.0 ms | 0.49 MB | 167 | 281 |
| 1000 | 31.19 ms | 31.61 ms | 31.25 ms | 1.6 MB | 1067 | 2046 |
| 5000 | 183.57 ms | 186.03 ms | 187.5 ms | 7.66 MB | 5067 | 9861 |
| 10000 | 355.65 ms | 357.45 ms | 343.75 ms | 15.26 MB | 10067 | 19630 |

| events (500 vessels) | median | p95 | CPU | peak memory | nodes |
|---:|---:|---:|---:|---:|---:|
| 100 | 88.4 ms | 90.15 ms | 93.75 ms | 0.89 MB | 627 |
| 1000 | 196.47 ms | 203.61 ms | 187.5 ms | 1.84 MB | 1527 |

## Cascade query

| vessels | one chokepoint: median | reached | every chokepoint (fanout): median | reached | peak memory |
|---:|---:|---:|---:|---:|---:|
| 100 | 0.22 ms | 1 | 29.76 ms | 85 | 0.18 MB |
| 1000 | 0.23 ms | 1 | 267.83 ms | 711 | 1.55 MB |
| 5000 | 0.25 ms | 1 | 574.06 ms | 2018 | 3.25 MB |
| 10000 | 0.21 ms | 1 | 865.43 ms | 2929 | 5.1 MB |

## Attention, decisions, scenarios, Critic

| stage | size | median | p95 | CPU | peak memory | note |
|---|---:|---:|---:|---:|---:|---|
| attention (NATIONAL, fanout cascade) | 10000 vessels | 3256.83 ms | 3358.43 ms | 2968.75 ms | 5.36 MB | 2921 items ranked |
| DecisionProblem (vessel routing) | 100 vessels | 695.11 ms | 700.7 ms | 625.0 ms | 0.65 MB | 6 options, 6 feasible |
| DecisionProblem (vessel routing) | 1000 vessels | 1585.54 ms | 1617.76 ms | 1453.12 ms | 13.51 MB | 6 options, 6 feasible |
| scenario branch + cascade | 1000 vessels | 143.49 ms | 144.47 ms | 125.0 ms | 0.93 MB | 308 nodes reached |
| Critic, every option | 6 options | 1.33 ms | 1.39 ms | 0.0 ms | 0.01 MB | 0.222 ms per option |

## Pareto frontier

| options | median | p95 | peak memory |
|---:|---:|---:|---:|
| 50 | 5.96 ms | 6.05 ms | 0.0 MB |
| 500 | 130.77 ms | 131.39 ms | 0.03 MB |
| 5000 | 2591.72 ms | 2592.68 ms | 0.79 MB |

## Historical mission replay

| mission | hulls | decide every hull + reveal: median | p95 | peak memory |
|---|---:|---:|---:|---:|
| suez-ever-given-2021 | 3 | 1555.52 ms | 1565.17 ms | 1.17 MB |

## API latency (in-process, real cache on disk)

| route | status | p50 | p95 | p99 | max | payload |
|---|---:|---:|---:|---:|---:|---:|
| `GET /api/health` | 200 | 9.9 ms | 11.6 ms | 12.4 ms | 12.8 ms | 1,391 B |
| `GET /api/world/state` | 200 | 27.2 ms | 29.9 ms | 30.3 ms | 30.9 ms | 34,643 B |
| `GET /api/world/cascades` | 200 | 29.7 ms | 32.3 ms | 32.3 ms | 37.0 ms | 52,445 B |
| `GET /api/attention` | 200 | 33.0 ms | 36.4 ms | 36.5 ms | 37.3 ms | 10,910 B |
| `GET /api/global-eye/events` | 200 | 23.3 ms | 26.9 ms | 27.7 ms | 30.0 ms | 32,217 B |
| `GET /api/fabric/health?mode=DEMO` | 200 | 12.9 ms | 15.7 ms | 122.2 ms | 195.4 ms | 3,245 B |
| `GET /api/admin/freshness` | 200 | 20.5 ms | 24.8 ms | 24.9 ms | 105.9 ms | 8,179 B |
| `GET /api/missions` | 200 | 4.9 ms | 6.1 ms | 6.2 ms | 6.7 ms | 575 B |
| `GET /api/decisions/actions` | 200 | 4.6 ms | 5.1 ms | 5.2 ms | 6.2 ms | 7,287 B |
| `POST /api/decisions/problems` | 200 | 269.7 ms | 297.0 ms | 298.3 ms | 397.7 ms | 73,461 B |

## Reading the numbers

- World build scales close to linearly in vessels: 100x the hulls cost 91.9x the time.
- The large-fanout cascade over 10000 hulls reaches 2929 nodes in 865.43 ms; the cascade is bounded by the graph it can reach, not by the fleet.
- `POST /api/decisions/problems` is the slowest route at p95 297.0 ms (73,461 B); it is served from the versioned live world, so repeated calls at one revision reuse the build.
- `GET /api/attention` is the slowest route at p95 36.4 ms (10,910 B); it is served from the versioned live world, so repeated calls at one revision reuse the build.
- Decision problems, scenarios and the Critic are all under the interactive budget on this machine; the pipeline (minutes) is the only slow path and it runs out of process under the freshness coordinator.
