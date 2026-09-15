# India PortWatch

**A maritime operations product that computes consequence and answers "what should we do?" — with every number traced to the measurement it came from, and a written refusal wherever there is none.**

---

## What is PortWatch?

PortWatch is a decision system for Indian ports and the ships bound for them. It builds a live model of the world — chokepoints, trade lanes, hulls, quays, cargo — from public feeds, propagates every event through that world to the ports and vessels it actually reaches, ranks what needs attention now, and, for any hull, quay or consignment, computes the options an operator really has, simulates each on its own branch of the observed world, ranks them on a Pareto frontier, has a Critic check the ranking, and puts the choice in front of a named person. What the person decides is written down before the world answers; when it does, the recommendation is scored against the outcome and the difference feeds the next decision.

```
SENSE → UNDERSTAND → PREDICT → GENERATE OPTIONS → SIMULATE → OPTIMISE → CRITIQUE
  ▲                                                                          │
  │                        HUMAN DECISION → OBSERVE OUTCOME → LEARN          │
  └──────────────────────────────────────────────────────────────────────────┘
```

Four roles share one world: **National Command** (every port, ranked by where intervention matters), a **Port Authority** (its own terminal as a 3D twin, its berth plan, its advisories to arriving ships), a **Shipping Company** (which of its hulls need intervention and by when the option closes) and a **Vessel** (its passage, its destination, the advisories it has been sent).

## Why does it matter?

A blocked canal, a cyclone over a port, a strike, a missile — each arrives as fourteen headlines and one question: *which of our ships, ports and cargoes does this touch, and what do we do about it?* Today that question is answered by people from memory, on the phone, with numbers nobody can audit afterwards. PortWatch answers it from a graph a person can read: the event, the strait it threatens, the lanes that transit it, the hulls on those lanes with their timing at the strait, the ports they are bound for, the yard pressure that follows, and — for a chosen hull — a set of options each simulated, measured, priced where a price exists, and criticised. Then it keeps the record, and tells you where it was wrong.

The product's value is not that it is right. It is that it is **legible** (every figure has a basis), **honest** (an unknown is never a zero; a replay is never called live), **continuous** (its own freshness coordinator keeps the world current) and **scored** (two historical missions and a seeded decision benchmark say, in the engine's own numbers, where the optimiser adds value and where it does not).

## What can it do?

| Ask | PortWatch answers with |
|---|---|
| *What is happening, where, and what does it touch?* | A live event register (GDELT, GDACS) propagated through chokepoints → lanes → vessels → ports, drawn on the chart as it is computed, with the full step trace behind every reached node |
| *Which of our hulls, ports and cargoes need attention now?* | An attention queue ranked by consequence × confidence × urgency, cut when no option remains, with the deadline on every actionable row |
| *What should this hull do?* | A DecisionProblem: every catalogue action marked available or not with a reason, each option simulated on its own branch, hard constraints that reject rather than penalise, a Pareto frontier, a balanced ranking with its weights on the outside, a Critic verdict naming the computation it read, and a recommendation that is never dominated |
| *What should the port do about three ships arriving at once?* | Berth plans run through the port twin — first come first served, reassign by work, stagger arrivals, size the crane gangs, prioritise a commitment — measured on wait, turnaround and missed departures |
| *Will this consignment make its connection?* | Cargo options checked by real feasibility rules: capacity, reefer plugs, dangerous goods, deadweight, the cut-off window |
| *What is it worth?* | A financial twin that prices only from a stated basis — a cited public tariff, a contract, or an operator's assumption labelled ASSUMPTION — and says "unknown" for everything else, never zero |
| *Which Indian cargo categories are structurally exposed to this chokepoint?* | STRUCTURAL EXPOSURE: event → chokepoint → lane → port → commodity class, every link a catalogued fact with its source, no tonnage invented |
| *Is this hull behaving oddly?* | Seven behaviour rules over observed AIS — gaps, impossible jumps, loitering, route deviation, destination inconsistency, abnormal speed state, repeated identity conflict — each detection with rule, evidence, threshold, confidence and instants; UNAVAILABLE under the replay |
| *Would it have got the Ever Given right? The cyclone?* | Two historical missions replayed with only what was knowable at the clock, decided, revealed and scored on regret, calibration and forecast error, side by side |
| *Is the system healthy and current?* | A freshness coordinator with a policy per artefact, a diagnostics surface with latencies and cache hits, a readiness check that refuses a misleading configuration, and a start command that prints the actual mode of every signal |

## What is real?

Every surface in the product says which of these it is standing on. The short version:

| Signal | In the demo | Basis |
|---|---|---|
| Port activity | **Real, lagged** | IMF PortWatch daily satellite-AIS port calls; the export says how old |
| Maritime events | **Real** | GDELT DOC 2.0 and GDACS, deduplicated and corroborated; probabilities withheld until calibrated |
| Weather and sea state | **Real** | Open-Meteo surface and marine forecasts; the marine grid says its fetch age and coverage |
| Vessel traffic | **Simulated, labelled** | A deterministic replay. It becomes `LIVE_AIS` only when a configured AISStream key delivers valid observations, and never by falling through. `scripts/verify_live_ais.py` is the acceptance path for a real key and SKIPs, honestly, without one |
| Port geometry | **Schematic** | The 3D twins are generated layouts; counts and rates are modelled and say so |
| Cargo manifests | **Demo data** | Behind real feasibility rules that a live feed would drive unchanged |
| Tariffs | **Real, cited** | JNPA and Chennai public scales of rates, cited to the page, priced only inside their validity |
| Commodity classes per port | **Real, cited** | The Ministry's Basic Port Statistics 2023-24 table and terminal operators' own statements; presence only, no volume |
| Missions | **Real chronology, illustrative hulls** | Ever Given (Suez, 2021) and Biparjoy (Gulf of Kutch, 2023) transcribed from cited sources with every unstated time marked; the hulls are placeholders and say so |
| Money | **Refused unless based** | No default rupee value exists anywhere in the product |

The long version is [docs/DATA_AUDIT.md](docs/DATA_AUDIT.md) and [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md), which is rendered from the licence catalogue with the evidence for every product's terms.

## How do I run the flagship demo?

Python 3.11+ and Node 24.

```bash
pip install -r requirements.txt
cd india-portwatch-terminal && npm ci && cd ..
python -m portwatch.demo start --mode DEMO
```

`start` validates the environment, refuses a configuration that would mislead (a licence mode nobody stated, a key for a product the mode may not use), refreshes whatever artefact has lapsed, starts the API and the terminal, verifies both, and prints the mode every signal is actually in:

```
Signals
  WORLD            READY              clock LIVE; intelligence cached; 12 ports
  EVENTS           FRESH              age 3.7 h; source lag 43.3 h; 40 events
  MARINE           FRESH              age 29 s; 4560 cells
  AIS              SIMULATED_TRAFFIC  positions are a deterministic replay, not observed AIS ...
  PORT FORECAST    FRESH              age 3.7 h; source lag 11.2 d; adaptive_ensemble; origin STALE
  DECISION ENGINE  READY              22 catalogue actions; Critic runs 11 checks
  MISSION ENGINE   READY              2 missions: Ever Given: the Suez Canal blockage, Mar; Biparjoy: ...
    events         AVAILABLE          gdelt-events; commercial ALLOWED
    marine         AVAILABLE          open-meteo-free; commercial PROHIBITED
    weather        AVAILABLE          open-meteo-free; commercial PROHIBITED
  TERMINAL         READY              http://127.0.0.1:8080
```

That run found the marine grid 3.2 hours old — past its policy — refreshed it, and only then said READY; the operator did nothing. Sign in as `admin@portwatch.demo` (password `portwatch`) and follow [docs/FLAGSHIP_DEMO.md](docs/FLAGSHIP_DEMO.md): two minutes from an alive world to a revealed outcome, with every beat's timing recorded from a real run, and the failure demo — AIS refused, no charter rate, no marine grid — in the product's own words. `python -m portwatch.demo doctor` validates without starting; `status` asks a running deployment; `stop` ends a detached one. `python scripts/demo_acceptance.py` is the acceptance gate — thirty-nine claims the product makes about itself, checked against its own API; a failed claim fails the gate.

Other ways in: `docker compose up --build`, or `uvicorn backend.app.main:app --port 8000` with `PORTWATCH_LICENCE_MODE` set and `npm run dev` in the terminal. The API listens on `$PORT` when a host sets one.

## Proof

| Question | Where the evidence is |
|---|---|
| How fast is it, at what scale? | [docs/PERFORMANCE.md](docs/PERFORMANCE.md) — world builds to 10,000 hulls, cascades, attention, decisions, scenarios, the frontier, the Critic, mission replays and API p50/p95/p99, with CPU and memory |
| Does the optimiser add value? | [docs/DECISION_BENCHMARK.md](docs/DECISION_BENCHMARK.md) — a fixed seeded corpus across vessel, port and cargo, four policies on the same options, scored against a hidden truth, with every case PortWatch lost listed |
| Does it survive attack? | `tests/test_adversarial_decisions.py` — fifteen attacks (no route, every berth taken, missing weather, stale AIS, contested identity, unknown money, lapsed tariffs, no FX, exhausted capacity, closed windows, a world that moved) that must degrade or refuse with a written reason |
| Is time handled honestly? | `tests/test_world_clock.py` — one WorldClock in four modes, every temporal subsystem proven to read it, and a source scan that refuses any other wall-clock read |
| Does it stay current on its own? | `tests/test_freshness.py` — the coordinator's SLA, lead, dedupe, last-known-good, bounded backoff and dependency invalidation, each with a test |
| Does the two-minute demo run as a buyer would see it? | [docs/FLAGSHIP_DEMO.md](docs/FLAGSHIP_DEMO.md#the-recorded-run) — every beat driven by `qa/executive-demo.mjs` against the running stack, no mock and no manual refresh, with the time each took; screenshots in [docs/qa/executive-demo/](docs/qa/executive-demo/) |
| What does it say when a signal is not there? | `scripts/demo_failure.py` — AIS credential refused, no charter rate, no marine grid and the provider unreachable; the product's own words, and a non-zero exit if it ever substitutes or zeroes |
| What does it look like? | [docs/qa/productization/](docs/qa/productization/) — every workflow at 1920×1080, 1440×900 and 1366×768 |

## Documentation

| Page | Covers |
|---|---|
| [docs/PRODUCT_INTERNALS.md](docs/PRODUCT_INTERNALS.md) | The long-form account: product modes, architecture, agents, MCP, Global Eye, the decision engine, the port twin, cargo, advisories, learning, RL safety, data honesty, models, tests, limitations |
| [docs/FLAGSHIP_DEMO.md](docs/FLAGSHIP_DEMO.md) | The two-minute decision demo, its timings, and the failure demo |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The layers, where each one's authority ends, the pipeline, storage, and the seams to extend |
| [docs/DECISION_ENGINE.md](docs/DECISION_ENGINE.md) | The decision model, the action catalogue, hard constraints, the frontier, the Critic, the financial twin, actors, the approval workflow, the ledger, missions |
| [docs/SIGNAL_FABRIC.md](docs/SIGNAL_FABRIC.md) | Licence at product granularity with evidence, the AIS socket and its state machines, entity fusion, observed hulls in the world graph, the sea |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) | Every product, its verified licence state and the evidence — rendered from the catalogue |
| [docs/DATA_AUDIT.md](docs/DATA_AUDIT.md) | Field by field: measured, derived, proxy, simulated, schematic or absent |
| [docs/GLOBAL_EYE.md](docs/GLOBAL_EYE.md) | Corroboration and dedupe, the lane catalogue, the timing gate, why the probability is unavailable |
| [docs/PORT_TWIN.md](docs/PORT_TWIN.md) | What is real and what is schematic, the work-rate model, the reward function, the measured policy results |
| [docs/LEARNING.md](docs/LEARNING.md) | The ledger's enforced properties, proper scoring, contextual reliability, the exact attribution identity |
| [docs/AGENTIC_AI.md](docs/AGENTIC_AI.md) · [docs/MCP.md](docs/MCP.md) | The agent boundary, the Critic, and the MCP tool layer with READ / SIMULATE / PROPOSE / EXECUTE |
| [docs/API_CONTRACT.md](docs/API_CONTRACT.md) | Every route, the identity headers, and what each status code means |
| [docs/PERFORMANCE.md](docs/PERFORMANCE.md) · [docs/DECISION_BENCHMARK.md](docs/DECISION_BENCHMARK.md) | The measured proof |
| [docs/MILESTONES.md](docs/MILESTONES.md) | What each milestone built, in order |

## Licence

MIT. See [LICENSE](LICENSE).
