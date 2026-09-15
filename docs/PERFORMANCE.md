# Performance

Measured 2026-09-15T14:47:50+00:00 on supercomputer (Intel64 Family 6 Model 183 Stepping 1, GenuineIntel, 24 cores, Python 3.12.0, Windows 11). Produced by `python scripts/benchmark_performance.py`; power-throttling opt-out applied, reference loop 63.5 ms at the start and 70.2 ms at the end (drift x1.11); every figure below is a measurement from that run, not a target.

Wall time is `time.perf_counter()` around the call; CPU is process time over the same block; peak memory is `tracemalloc`'s peak during the block (the work's own allocations, not the interpreter's). Synthetic worlds are seeded from the real lane catalogue and port registry so the graph has the shape the product's own graph has.

## World State build

| vessels | median | p95 | CPU | peak memory | nodes | edges |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 4.95 ms | 5.26 ms | 0.0 ms | 0.52 MB | 167 | 378 |
| 1000 | 39.36 ms | 39.66 ms | 31.25 ms | 1.91 MB | 1067 | 3008 |
| 5000 | 218.88 ms | 234.97 ms | 218.75 ms | 9.16 MB | 5067 | 14638 |
| 10000 | 473.51 ms | 474.63 ms | 453.12 ms | 18.25 MB | 10067 | 29176 |

| events (500 vessels) | median | p95 | CPU | peak memory | nodes |
|---:|---:|---:|---:|---:|---:|
| 100 | 22.86 ms | 23.89 ms | 15.62 ms | 1.04 MB | 627 |
| 1000 | 44.17 ms | 44.93 ms | 46.88 ms | 1.99 MB | 1527 |

## Cascade query

| vessels | one chokepoint: median | reached | every chokepoint (fanout): median | reached | peak memory |
|---:|---:|---:|---:|---:|---:|
| 100 | 0.05 ms | 1 | 5.75 ms | 85 | 0.18 MB |
| 1000 | 0.05 ms | 1 | 51.6 ms | 711 | 1.55 MB |
| 5000 | 0.04 ms | 1 | 109.07 ms | 2018 | 3.26 MB |
| 10000 | 0.05 ms | 1 | 175.04 ms | 2929 | 5.1 MB |

## Attention, decisions, scenarios, Critic

| stage | size | median | p95 | CPU | peak memory | note |
|---|---:|---:|---:|---:|---:|---|
| attention (NATIONAL, fanout cascade) | 100 vessels | 12.46 ms | 14.0 ms | 15.62 ms | 0.16 MB | 77 items ranked |
| attention (NATIONAL, fanout cascade) | 1000 vessels | 144.76 ms | 149.29 ms | 156.25 ms | 1.49 MB | 703 items ranked |
| attention (NATIONAL, fanout cascade) | 5000 vessels | 378.09 ms | 378.73 ms | 359.38 ms | 4.08 MB | 2010 items ranked |
| attention (NATIONAL, fanout cascade) | 10000 vessels | 818.0 ms | 881.74 ms | 796.88 ms | 5.88 MB | 2921 items ranked |
| DecisionProblem (vessel routing) | 100 vessels | 207.18 ms | 210.21 ms | 203.12 ms | 0.72 MB | 6 options, 6 feasible |
| DecisionProblem (vessel routing) | 1000 vessels | 423.02 ms | 424.22 ms | 421.88 ms | 13.59 MB | 6 options, 6 feasible |
| scenario branch + cascade | 1000 vessels | 29.02 ms | 31.89 ms | 31.25 ms | 0.92 MB | 308 nodes reached |
| Critic, every option | 6 options | 0.27 ms | 0.27 ms | 0.0 ms | 0.01 MB | 0.045 ms per option |

## Pareto frontier

| options | median | p95 | peak memory |
|---:|---:|---:|---:|
| 50 | 1.11 ms | 1.12 ms | 0.0 MB |
| 500 | 25.82 ms | 25.93 ms | 0.03 MB |
| 5000 | 477.38 ms | 479.06 ms | 0.79 MB |

## Historical mission replay

| mission | hulls | decide every hull + reveal: median | p95 | peak memory |
|---|---:|---:|---:|---:|
| suez-ever-given-2021 | 3 | 417.99 ms | 418.87 ms | 1.26 MB |
| gulf-of-kutch-biparjoy-2023 | 3 | 233.89 ms | 234.32 ms | 0.78 MB |

## API latency (in-process, real cache on disk)

| route | status | p50 | p95 | p99 | max | payload |
|---|---:|---:|---:|---:|---:|---:|
| `GET /api/health` | 200 | 2.1 ms | 2.9 ms | 3.1 ms | 43.3 ms | 2,407 B |
| `GET /api/world/state` | 200 | 5.6 ms | 6.3 ms | 6.6 ms | 13.1 ms | 37,894 B |
| `GET /api/world/cascades` | 200 | 6.1 ms | 7.0 ms | 7.5 ms | 7.8 ms | 53,341 B |
| `GET /api/attention` | 200 | 6.1 ms | 7.0 ms | 7.0 ms | 11.2 ms | 11,835 B |
| `GET /api/global-eye/events` | 200 | 4.9 ms | 6.1 ms | 6.3 ms | 6.7 ms | 32,511 B |
| `GET /api/fabric/health?mode=DEMO` | 200 | 2.6 ms | 3.7 ms | 5.0 ms | 73.3 ms | 3,324 B |
| `GET /api/admin/freshness` | 200 | 4.0 ms | 4.9 ms | 6.1 ms | 24.2 ms | 8,220 B |
| `GET /api/missions` | 200 | 0.9 ms | 1.2 ms | 1.2 ms | 1.5 ms | 1,423 B |
| `GET /api/decisions/actions` | 200 | 1.0 ms | 1.4 ms | 1.4 ms | 1.5 ms | 7,307 B |
| `POST /api/decisions/problems` | 200 | 53.7 ms | 63.8 ms | 65.6 ms | 91.6 ms | 82,663 B |

## Budgets

Each ceiling was set from the figure measured when the budget was written (`src/portwatch_os/perf_budgets.py`); `python scripts/benchmark_performance.py --gate` exits non-zero on a breach, and `tests/test_perf_budgets.py` holds the small-size subset in ordinary CI at three times the ceiling.

| budget | statistic | ceiling | this run | set from | headroom |
|---|---|---:|---:|---:|---:|
| World State build, 10,000 vessels | median | 1000 ms | 473.5 ms | 503.6 ms | 53% |
| World State build, 1,000 vessels | median | 150 ms | 39.4 ms | 49.7 ms | 74% |
| Cascade query, every chokepoint, 10,000 vessels | median | 400 ms | 175.0 ms | 187.2 ms | 56% |
| Attention queue, 10,000 vessels | median | 1000 ms | 818.0 ms | 703.3 ms | 18% |
| Attention queue, 1,000 vessels | median | 400 ms | 144.8 ms | 154.7 ms | 64% |
| DecisionProblem, vessel routing, 1,000-vessel world | median | 750 ms | 423.0 ms | 404.5 ms | 44% |
| DecisionProblem, vessel routing, 100-vessel world | median | 500 ms | 207.2 ms | 158.1 ms | 59% |
| Scenario branch and cascade, 1,000 vessels | median | 100 ms | 29.0 ms | 30.0 ms | 71% |
| Pareto frontier, 500 options | median | 100 ms | 25.8 ms | 26.6 ms | 74% |
| Mission replay, decide every hull and reveal (Ever Given) | median | 750 ms | 418.0 ms | 338.6 ms | 44% |
| Read API, p95 across the read routes | p95 | 25 ms | 7.0 ms | 7.3 ms | 72% |
| POST /api/decisions/problems, p95 | p95 | 250 ms | 63.8 ms | 70.9 ms | 74% |

## Reading the numbers

- World build scales close to linearly in vessels: 100x the hulls cost 95.7x the time.
- The large-fanout cascade over 10000 hulls reaches 2929 nodes in 175.04 ms; the cascade is bounded by the graph it can reach, not by the fleet.
- `POST /api/decisions/problems` is the slowest call at p95 63.8 ms (82,663 B); it computes a decision problem, simulating every option on its own branch.
- `GET /api/world/cascades` is the slowest read at p95 7.0 ms (53,341 B); reads are served from the versioned live world, so repeated calls at one revision reuse the build.
- Timings move with host load: the previous publication of this page, taken while a browser suite ran on the same machine, was three to five times slower on every row. Compare runs on an idle host.
- Decision problems, scenarios and the Critic are all under the interactive budget on this machine; the pipeline (minutes) is the only slow path and it runs out of process under the freshness coordinator.
