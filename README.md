# PortWatch X

**A maritime operations system for Indian ports and the ships bound for them. It computes consequence, answers "what should we do?" with options it simulated and criticised, keeps the current plan unless an intervention survives not knowing how long the disruption will last, and traces every number to the measurement it came from — with a written refusal wherever there is none.**

---

## What it is

PortWatch X builds a live model of the world — chokepoints, trade lanes, hulls, quays, cargo — from public feeds, propagates every event through that world to the ports and vessels it actually reaches, ranks what needs attention now, and, for any hull, berth plan or consignment, computes the options an operator really has. Each option is simulated on its own branch of the observed world, ranked on a Pareto frontier, checked by a Critic, stress-tested against four horizons for how long the disruption might last, and put in front of a named person. What the person decides is written down before the world answers; when it does, the recommendation is scored against the outcome and the difference feeds the next decision.

```
SENSE → UNDERSTAND → PREDICT → GENERATE OPTIONS → SIMULATE → OPTIMISE → STRESS → CRITIQUE
  ▲                                                                                  │
  │                        HUMAN DECISION → OBSERVE OUTCOME → LEARN                  │
  └──────────────────────────────────────────────────────────────────────────────────┘
```

Four roles share one world: **National Command** (every port, ranked by where intervention matters), a **Port Authority** (its own terminal as a 3D twin, its berth plan, its advisories to arriving ships), a **Shipping Company** (which of its hulls need intervention and by when the option closes) and a **Vessel** (its passage, its destination, the advisories it has been sent). Each sees the decisions it holds and no one else's; national command sees everything.

## What it answers

| Ask | PortWatch X answers with |
|---|---|
| *What is happening, where, and what does it touch?* | A live event register (GDELT, GDACS) propagated through chokepoints → lanes → vessels → ports, drawn on the chart as it is computed, with the full step trace behind every reached node |
| *Which of our hulls, ports and cargoes need attention now?* | An attention queue ranked by consequence × confidence × urgency, cut when no option remains, with the deadline on every actionable row |
| *What should this hull do?* | A DecisionProblem: every catalogue action marked available or not with a reason, each option simulated on its own branch, hard constraints that reject rather than penalise, a Pareto frontier with named picks, a Critic verdict naming the computation it read — and a **robust recommendation**: `ACT`, `KEEP_CURRENT_PLAN` or `WAIT_FOR_MORE_INFORMATION`, judged by minimax regret over four labelled stress horizons for the claim's duration, with the break-even closure length of every intervention and the reversibility of every option ([docs/ROBUST_DECISIONS.md](docs/ROBUST_DECISIONS.md)) |
| *What should the port do about three ships arriving at once?* | Berth plans run through the port twin — first come first served, reassign by work, stagger arrivals, size the crane gangs, prioritise a commitment — measured on wait, turnaround and missed departures |
| *Will this consignment make its connection?* | Cargo options checked by real feasibility rules: capacity, reefer plugs, dangerous goods, deadweight, the cut-off window |
| *What is it worth?* | A financial twin that prices only from a stated basis — a cited public tariff, a contract, or an operator's assumption labelled ASSUMPTION — and says "unknown" for everything else, never zero |
| *Which Indian cargo categories are structurally exposed to this chokepoint?* | STRUCTURAL EXPOSURE: event → chokepoint → lane → port → commodity class, every link a catalogued fact with its source, no tonnage invented |
| *Is this hull behaving oddly?* | Seven behaviour rules over observed AIS — gaps, impossible jumps, loitering, route deviation, destination inconsistency, abnormal speed state, repeated identity conflict — each detection with rule, evidence, threshold, confidence and instants; UNAVAILABLE under the replay |
| *Would it have got the Ever Given right? The cyclone?* | Two historical missions replayed with only what was knowable at the clock, decided, revealed and scored on regret, calibration and forecast error, side by side |
| *Is the system healthy, current and intact?* | A freshness coordinator with a policy per artefact, a diagnostics surface with latencies and cache hits, durable-store probes on `/api/health`, a readiness check that refuses a misleading configuration, and a start command that prints the actual mode of every signal |

## Why the robust policy

The seeded benchmark had shown the expected-value ranking losing to "do nothing" on vessel routing: it intervened on 48% of test cases and 93% of those interventions were unnecessary, because a claim like "material transit disruption at the named chokepoint" says nothing about how long it will last. The robust policy does not invent a probability for that. It evaluates every option under four labelled horizons — the claim fizzles now, lasts half its stated horizon, lasts as stated, lasts twice as long — with the same closure model the mission scorecard scores by, keeps the current plan as a first-class candidate, and picks by minimax regret. When the answer depends on the horizon and the option stays open past the next register refresh, it says **wait**, and names what to look at. On the untouched test corpus (200 cases) it cut mean regret from 12.14 h to 1.05 h and p90 from 42.1 h to 0.0 h without raising the worst case; its value is in *not* intervening, and the panel says so, with the break-even band instead of a hedge.

The promotion gate ([docs/DECISION_POLICY_GATE.md](docs/DECISION_POLICY_GATE.md)) was fixed before the held-out corpora ran; a test asserts that the engine's active policy matches the published verdict.

## What is real

Every surface in the product says which of these it is standing on. The status strip names the licence mode (DEMO, RESEARCH, COMMERCIAL) and the traffic truth (LIVE AIS, AIS STALE, SIMULATED) on every screen.

| Signal | In the demo | Basis |
|---|---|---|
| Port activity | **Real, lagged** | IMF PortWatch daily satellite-AIS port calls; the export says how old |
| Maritime events | **Real** | GDELT DOC 2.0 and GDACS, deduplicated and corroborated; probabilities withheld until calibrated; the source lag is stated, and between live claims the attention queue is empty and says so |
| Weather and sea state | **Real** | Open-Meteo surface and marine forecasts; the marine grid says its fetch age and coverage |
| Vessel traffic | **Simulated, labelled** | A deterministic replay. It becomes `LIVE_AIS` only when a configured AISStream key delivers valid observations, and never by falling through. `scripts/verify_live_ais.py` is the acceptance path for a real key and SKIPs, honestly, without one |
| Port geometry | **Schematic** | The 3D twins are generated layouts; counts and rates are modelled and say so |
| Cargo manifests | **Demo data** | Behind real feasibility rules that a live feed would drive unchanged |
| Tariffs | **Real, cited** | JNPA and Chennai public scales of rates, cited to the page, priced only inside their validity |
| Commodity classes per port | **Real, cited** | The Ministry's Basic Port Statistics 2023-24 table and terminal operators' own statements; presence only, no volume |
| Missions | **Real chronology, illustrative hulls** | Ever Given (Suez, 2021) and Biparjoy (Gulf of Kutch, 2023) transcribed from cited sources with every unstated time marked; the hulls are placeholders and say so |
| Closure durations in the benchmark | **Hidden truths** | Drawn from a stated distribution the policy never sees |
| Money | **Refused unless based** | No default rupee value exists anywhere in the product |

The long version is [docs/DATA_AUDIT.md](docs/DATA_AUDIT.md) and [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md), which is rendered from the licence catalogue with the evidence for every product's terms.

## Running it

Python 3.11+ and Node 24.

```bash
pip install -r requirements.txt
cd india-portwatch-terminal && npm ci && cd ..
python -m portwatch.demo start --mode DEMO
```

`start` validates the environment, refuses a configuration that would mislead (a licence mode nobody stated, a key for a product the mode may not use), refreshes whatever artefact has lapsed, starts the API on :8000 and the terminal on :8080, verifies both, and prints the mode every signal is actually in:

```
Signals
  WORLD            READY              clock LIVE; intelligence cached; 12 ports
  EVENTS           FRESH              age 49 s; source lag 3.1 d; 40 events
  MARINE           FRESH              age 48 s; 4560 cells
  AIS              SIMULATED_TRAFFIC  positions are a deterministic replay, not observed AIS ...
  PORT FORECAST    EXPIRED            age 31.4 h; source lag 11.2 d; job RUNNING; adaptive_ensemble; origin STALE
  DECISION ENGINE  READY              22 catalogue actions; Critic runs 11 checks
  MISSION ENGINE   READY              2 missions: Ever Given: the Suez Canal blockage, Mar; Biparjoy: ...
  TERMINAL         READY              http://127.0.0.1:8080
```

Sign in as `admin@portwatch.demo` (password `portwatch`) and follow [docs/FLAGSHIP_DEMO.md](docs/FLAGSHIP_DEMO.md). `python -m portwatch.demo doctor` validates without starting; `status` asks a running deployment; `stop` ends a detached one.

**Production** is one long-running API process with a persistent volume, never a request-scoped function platform ([docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)):

```bash
PORTWATCH_LICENCE_MODE=DEMO docker compose up --build -d pipeline api terminal
```

The `state` volume (`PORTWATCH_STATE_DIR`) holds what must persist — the decision ledger, the advisory register, the operator's cost assumptions — and is the one to back up. A corrupt store is refused at open, named on `/api/health`, and never replaced; a decision computed before a restart is served from the ledger read-only. Without a container runtime the same process runs under any supervisor with `uvicorn backend.app.main:app --workers 1`. The public deployment is split the same way: the terminal is the Vercel project `india-portwatch` (root directory `india-portwatch-terminal`, TanStack Start) at `https://india-portwatch.vercel.app`, and the API is one long-running container on Render or Railway from `render.yaml` / `railway.json`, its URL baked into the terminal as `VITE_PORTWATCH_API_BASE`.

**Identity** is asserted from `X-PortWatch-*` headers and not verified; the API says so on `/api/advisories/policy` and on readiness. Behind an authenticating proxy set `PORTWATCH_IDENTITY_MODE=required` so a role-less request is refused at the door. In both modes administration surfaces need an explicit `NATIONAL_ADMIN` role and no flag grants it ([docs/SECURITY.md](docs/SECURITY.md)).

## Proof

| Question | Where the evidence is |
|---|---|
| Does the optimiser add value, and did the new policy earn its place? | [docs/DECISION_BENCHMARK.md](docs/DECISION_BENCHMARK.md) — five policies (current plan, greedy, a duty-officer heuristic, the expected-value incumbent, the robust candidate) on three disjoint seeded corpora (tuning 40, validation 100, test 200 per domain), scored against a hidden truth with every lost case listed; [docs/DECISION_POLICY_GATE.md](docs/DECISION_POLICY_GATE.md) — the promotion verdict, check by check |
| How fast is it, at what scale? | [docs/PERFORMANCE.md](docs/PERFORMANCE.md) — world builds to 10,000 hulls, cascades, attention, decisions, scenarios, the frontier, mission replays and API p50/p95/p99, with twelve budgets set from measurement and a gate (`python scripts/benchmark_performance.py --gate`); [docs/FRONTEND_PERFORMANCE.md](docs/FRONTEND_PERFORMANCE.md) — load, first map render, interaction latency and a fifteen-minute session watched for growth |
| Who may see and do what? | [docs/SECURITY.md](docs/SECURITY.md) — the threat model, the identity seam, the authorization matrix (thirty-one routes in twelve resource groups × five identities) proved cell by cell by `tests/test_authorization_matrix.py`, the fuzz suite (`tests/test_api_fuzz.py`), the findings register, and the dependency audit with its one deferred advisory |
| Does state survive a restart, and what happens when it is broken? | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — the state audit (ephemeral, cache, rebuildable, must persist) and `scripts/demo_restart.py`: restart, a corrupt ledger, a corrupt event cache |
| Does it survive attack? | `tests/test_adversarial_decisions.py` — fifteen attacks (no route, every berth taken, missing weather, stale AIS, contested identity, unknown money, lapsed tariffs, no FX, exhausted capacity, closed windows, a world that moved) that must degrade or refuse with a written reason |
| Is time handled honestly? | `tests/test_world_clock.py` — one WorldClock in four modes, every temporal subsystem proven to read it, and a source scan that refuses any other wall-clock read |
| Does it stay current on its own? | `tests/test_freshness.py` — the coordinator's SLA, lead, dedupe, last-known-good, bounded backoff and dependency invalidation, each with a test |
| Does the product do what it says? | `python scripts/demo_acceptance.py` — forty claims the product makes about itself, checked against its own API on the live register; a failed claim fails the gate. `scripts/demo_failure.py` — AIS credential refused, no charter rate, no marine grid and the provider unreachable, in the product's own words, with a non-zero exit if it ever substitutes or zeroes |
| What does it look like? | [docs/qa/release/](docs/qa/release/) — fifteen canonical screens at 1920×1080, 1440×900 and 1366×768; [docs/qa/productization/](docs/qa/productization/) — every workflow |

The suites: 842 Python tests (`python -m pytest tests`), 320 browser specs at two viewports against the production build with a replayed API (`npm run test:browser:ci` in the terminal), all in CI.

## Documentation

| Page | Covers |
|---|---|
| [docs/PRODUCT_INTERNALS.md](docs/PRODUCT_INTERNALS.md) | The long-form account: product modes, architecture, agents, MCP, Global Eye, the decision engine, the port twin, cargo, advisories, learning, RL safety, data honesty, models, tests, limitations |
| [docs/ROBUST_DECISIONS.md](docs/ROBUST_DECISIONS.md) | The closure outcome model, the four stress horizons, minimax regret, the three answers, reversibility, break-even, and what the policy does not do |
| [docs/DECISION_ENGINE.md](docs/DECISION_ENGINE.md) | The decision model, the action catalogue, hard constraints, the frontier, the Critic, the financial twin, actors, the approval workflow, the ledger, missions |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | The deployment shape, the state audit, concurrency, running it, what was tested, what was not |
| [docs/SECURITY.md](docs/SECURITY.md) | The identity model and its two modes, the authorization matrix, the findings, the dependency audit |
| [docs/FLAGSHIP_DEMO.md](docs/FLAGSHIP_DEMO.md) | The two-minute decision demo, its timings, and the failure demo |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The layers, where each one's authority ends, the pipeline, storage, and the seams to extend |
| [docs/SIGNAL_FABRIC.md](docs/SIGNAL_FABRIC.md) | Licence at product granularity with evidence, the AIS socket and its state machines, entity fusion, observed hulls in the world graph, the sea |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) · [docs/DATA_AUDIT.md](docs/DATA_AUDIT.md) | Every product, its verified licence state and the evidence; field by field, measured, derived, proxy, simulated, schematic or absent |
| [docs/GLOBAL_EYE.md](docs/GLOBAL_EYE.md) | Corroboration and dedupe, the lane catalogue, the timing gate, why the probability is unavailable |
| [docs/PORT_TWIN.md](docs/PORT_TWIN.md) | What is real and what is schematic, the work-rate model, the reward function, the measured policy results |
| [docs/LEARNING.md](docs/LEARNING.md) | The ledger's enforced properties, proper scoring, contextual reliability, the exact attribution identity |
| [docs/AGENTIC_AI.md](docs/AGENTIC_AI.md) · [docs/MCP.md](docs/MCP.md) | The agent boundary, the Critic, and the MCP tool layer with READ / SIMULATE / PROPOSE / EXECUTE |
| [docs/API_CONTRACT.md](docs/API_CONTRACT.md) | Every route, the identity headers, and what each status code means |
| [docs/PERFORMANCE.md](docs/PERFORMANCE.md) · [docs/FRONTEND_PERFORMANCE.md](docs/FRONTEND_PERFORMANCE.md) · [docs/DECISION_BENCHMARK.md](docs/DECISION_BENCHMARK.md) · [docs/DECISION_POLICY_GATE.md](docs/DECISION_POLICY_GATE.md) | The measured proof |
| [docs/MILESTONES.md](docs/MILESTONES.md) | What each milestone built, in order |

## Known limitations

- Identity is a seam, not a verifier: tokens are not checked; a deployment puts an authenticating proxy in front and runs `PORTWATCH_IDENTITY_MODE=required`.
- Vessel traffic is a labelled replay until a licensed AIS feed is configured; nothing is called LIVE until an observation arrives.
- The robust policy models persistence to twice the claim's horizon; a claim that understates a closure fivefold is outside the stress set, and the WAIT loop is the operational answer.
- The live demo has something to decide only while a claim is live; when the event source lags or the news is quiet, the queue is empty and says so rather than inventing a hull to decide about.
- `maplibre-gl` 5.x carries an advisory whose path (popup and attribution HTML) the terminal does not use; the major upgrade is its own change, not part of the release freeze.
- Open-Meteo's free products are `PROHIBITED` commercially and AISStream's terms are `REQUIRES_REVIEW`; the licence catalogue says so and the mode refuses what it may not use.

## Licence

MIT. See [LICENSE](LICENSE).
