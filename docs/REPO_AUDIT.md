# Repository map

What each directory is, what it owns, and what it is not. Written so a reviewer
can find the code behind any number on screen in one hop.

Last reviewed: 2026-09-10.

---

## The one-line version

```
src/                the intelligence:  ingestion → experts → regimes → forecasting → decision
src/portwatch_os/   the operations OS:  global eye · twin · cargo · advisories · agents · MCP · ledger · learning
backend/            the API:            serves artefacts and the OS, computes nothing
india-portwatch-terminal/               the operator UI, four role workspaces, one typed client, no local data
tests/              ten suites:         intelligence, API contract, and the OS
scripts/            operations:         refresh loop, artefact gate
outputs/            artefacts:          features, regimes, forecasts, benchmark, the ledger DBs  (gitignored)
data/cache/         API cache:          the JSON the terminal reads                              (gitignored)
```

`run_award_demo.py` is the single entrypoint that runs `src/` end to end and
writes both artefact trees.

---

## `src/` — the intelligence pipeline

| Path | Owns |
|---|---|
| `src/utils/port_registry.py` | **The single source of truth for ports.** Model id ↔ UN/LOCODE ↔ PortWatch feed id ↔ geography ↔ capacity, with tolerant lookup and legacy aliases |
| `src/utils/provenance.py` | The `LIVE / CACHED_LIVE / STALE / SYNTHETIC / SIMULATED_TRAFFIC / SCHEMATIC / UNAVAILABLE` state machine, with automatic downgrade when a claim outruns its timestamps |
| `src/utils/config.py` | Paths, canonical column names, horizon, quantiles, regime labels, the modelling port registry |
| `src/ingestion/connectors/` | One module per external feed. Each records its own provenance on both the success and failure paths |
| `src/ingestion/portwatch_source.py` | Turns the PortWatch cache into the raw bundle, with leakage-safe derived series |
| `src/experts/` | Ten specialists, each emitting bounded 0–1 features plus a `*_confidence` column |
| `src/regimes/` | The HSMM feature matrix and the regime model (state, dwell, transition risk) |
| `src/forecasting/` | The supervised frame builder, the GBM quantile model, probabilistic persistence, the ridge second opinion, the TFT, the adaptive stack and conformal calibration |
| `src/evaluation/model_benchmark.py` | The walk-forward benchmark. **Every accuracy claim in this repository is produced here** |
| `src/decision/` | The decision engine, route optimizer, impact model, scenario catalogue and scenario propagation |

### The experts

| Module | Answers |
|---|---|
| `weather_expert` | How bad is the weather for berthing today? |
| `weather_persistence_expert` | Is it a squall or a multi-day system? |
| `news_expert` | How much event risk is attached to this port? |
| `port_ops_expert` | What is the AIS-derived queue and turnaround pressure? |
| `arrival_dynamics_expert` | Are arrivals accelerating, clustering, or piling up at anchorage? |
| `trade_demand_expert` | What is the underlying demand pressure? |
| `macro_expert` | What are oil, FX and inflation doing? |
| `capacity_expert` | How close is the terminal to a capacity squeeze? |
| `anomaly_expert` | Is today unusual against what was knowable yesterday? |
| `disruption_expert` | Which global chokepoint stress is about to land here? |
| `data_quality_expert` | How much should you trust all of the above? |

Every one of these writes a CSV under `outputs/expert_features/`, and every one
of those columns appears in `HSMM_FEATURES` and `_ORIGIN_FEATURES` — so the
signals change the forecast, not just the dashboard.
`scripts/verify_artefacts.py` fails the build if that stops being true.

---

## `src/portwatch_os/` — the operations layer

Added on top of the forecasting stack. Each package owns its own arithmetic and
nothing outside it computes those numbers.

| Path | Owns | Detail |
|---|---|---|
| `global_eye/model.py` | 17 event categories, classification, corroboration, severity, decay | [GLOBAL_EYE.md](GLOBAL_EYE.md) |
| `global_eye/ingest.py` | Dedupe: category + anchor + 36h + headline overlap, all four required | |
| `global_eye/exposure.py` | The chain — chokepoint → lane → vessel → port → impact → action — and the timing gate | |
| `global_eye/calibration.py` | Severity × corroboration → a probability, only once enough outcomes resolve | |
| `twin/state.py` | **`PortState`** — the one logical port read by the renderer, the simulator, the optimisers and the RL environment. No meshes, no cameras | [PORT_TWIN.md](PORT_TWIN.md) |
| `twin/simulation.py` | The deterministic discrete-event engine. Refuses infeasible actions and records why | |
| `twin/policies.py` | FCFS, random, two greedy optimisers, and the contextual bandit | |
| `twin/rl.py` | The training environment, with training and evaluation seed bases disjoint | |
| `twin/promotion.py` | The gate: `CANDIDATE → EVALUATING → APPROVED / REJECTED / RETIRED` | |
| `cargo/` | Transshipment feasibility and assignment. Real rules over demo shipments | |
| `fleet/company.py` | The carrier account interface, the fictional demo carrier, and `from_provider` | |
| `advisories/model.py` | 11 states, role-gated transitions, recipient visibility, ASCII folding | |
| `advisories/store.py` | Persistence and the append-only audit trail | |
| `agents/tools.py` | The four access levels, `ApprovalContext`, `approval_from_session` | [AGENTIC_AI.md](AGENTIC_AI.md) |
| `agents/portwatch_tools.py` | 24 tools, each declaring `computed_by` | |
| `agents/specialists.py` | Nine specialists, each with declared tools, ceiling and failure modes | |
| `agents/orchestrator.py` | Eight intents, sequential chains, subject narrowing | |
| `agents/critic.py` | Eight checks. Can only lower confidence, never raise it | |
| `mcp/server.py` | JSON-RPC 2.0 over stdio, over the **same** registry the agents use | [MCP.md](MCP.md) |
| `ledger/schema.py` | The five record types, their transitions, content-derived ids | [LEARNING.md](LEARNING.md) |
| `ledger/store.py` | SQLite (WAL). Refuses to rewrite a resolved row | |
| `learning/scoring.py` | Proper rules only: Brier, log loss, pinball, calibration bins | |
| `learning/reliability.py` | Contextual weights. **Raises** on a leaking row rather than skipping it | |
| `learning/attribution.py` | The exact decomposition `y − predicted = Σ wᵢ(y − sᵢ)`, verified to close | |
| `learning/outcome_agent.py` | Resolve → score → attribute → recalibrate. Observers injected, never imported | |
| `learning/backfill.py` | Loads the run's own walk-forward history into the ledger | |

**No package here holds an EXECUTE ceiling.** The highest any agent reaches is
PROPOSE, and EXECUTE additionally requires an approval context only an
authenticated human session can build.

---

## `backend/` — the API

| Path | Owns |
|---|---|
| `backend/app/main.py` | App assembly, CORS (configurable by env) |
| `backend/app/routes/` | Fifteen routers. Core: health, provenance, ports, model, weather, news, sar, fleet, scenarios. Operations: global_eye, company, port_twin (with `/cargo`), advisories, agents, learning |
| `backend/app/services/cache_service.py` | Read-only artefact access. Missing artefact → 503 naming the rebuild command |
| `backend/pipeline/export_award_cache.py` | Exports the primary artefacts (port state, forecasts, regimes, decisions, pipeline nodes, benchmark, vessels, fleet, run status) |
| `backend/pipeline/export_support_cache.py` | Exports the weather and event caches from measured values |

**The API computes no intelligence.** If a number is not in an artefact or in a
`src/portwatch_os/` module, the API does not have it. A route shapes and
authorises; that is all.

`POST /api/advisories/{id}/transition` is the only route whose effect a person
outside the system sees. It builds its principal from the request headers, and
the store — not the route — decides which role may make which transition.

### Removed in this cycle

A second, unmounted API lived under `backend/app/routers/` and
`backend/app/engines/`, alongside services that shipped a hardcoded
`PORT_RISKS` congestion table and a `get_weather` function that returned
constants. A reader could not tell which implementation served the terminal.
Deleted — the mounted `backend/app/routes/` tree is the only one.

---

## `india-portwatch-terminal/` — the operator UI

| Path | Owns |
|---|---|
| `src/services/api.ts` | The HTTP layer. **No local fallback data by design** |
| `src/services/portwatch.ts` | Every typed endpoint, in one module |
| `src/types/portwatch.ts` | The API contract, with nullable fields wherever the pipeline can fail to produce a value |
| `src/components/terminal/ui.tsx` | Shared primitives, including `ProvenanceChip` and a `Value` that renders `n/a` rather than a stand-in |
| `src/components/terminal/Shell.tsx` | Chrome, navigation, command bar, live source readiness |
| `src/components/map/MaritimeMap.tsx` | The radar map: risk-coloured ports, chokepoints, sea lanes, hover intelligence |
| `src/auth/` | The four roles, the demo account adapter, `normaliseRole`, and the ASCII header folding a browser's `fetch` requires |
| `src/services/portwatch-os.ts` | Every operations endpoint, typed, in one module |
| `src/lib/maritime/` | The chokepoint and lane catalogues, the water/routing graph, the weather field and model, and `traffic-source.ts` — the `TrafficSource` seam a licensed AIS feed fills |
| `src/components/map/weather-layers.ts` | The composite raster and the storm cells, with motion inferred from the risk gradient |
| `src/components/command/TimeTransport.tsx` | The forecast and weather cursors: NOW / +3 / +6 / +12 / +24 / +48 / +72 with play, pause and scrub |
| `src/components/twin/` | The 3D twin. Three.js directly, lazy-loaded, rebuilt only when the port's shape changes |
| `src/components/{globaleye,advisory,cargo,agent}/` | The operations screens |
| `src/routes/` | 57 route files: a root, a sign-in, nine legacy addresses kept as redirects, and four role workspaces — `admin/` (15), `port/` (14), `company/` (10), `vessel/` (9), each with its own layout |
| `qa/` | The Playwright suite: the production build, a replayed API, two viewports |

### Removed in this cycle

`src/data/*.ts` (nine static demo modules) and nine `*Service.ts` shims that
served them. API responses were merged *on top of* that static data, so a screen
could look alive while the backend was down, and port coordinates always came
from the static table regardless of what the API said. Deleted.

---

## `scripts/` — operations

| Script | Purpose |
|---|---|
| `live_refresh.py` | Long-running refresh loop; replaces the cache only after a successful run |
| `verify_artefacts.py` | The gate between "the pipeline exited zero" and "the terminal can be trusted" |
| `build_basemap.py` | Clips Natural Earth to the Indian Ocean theatre; regenerates the terminal's bundled coastline |
| `download_nasa_weather.py`, `preprocess_weather.py`, `explore_weather.py` | Historical weather preparation for the research track |

Browser smoke testing moved into the terminal itself as a Playwright suite
(`india-portwatch-terminal/qa/`), which drives the production build across the
three roles rather than a single anonymous session.

---

## `tests/` — ten suites

| Suite | Covers |
|---|---|
| `test_api_contract.py` | Every route's shape, and its 503 when an artefact is missing |
| `test_award_intelligence.py` | Experts, regimes, ensemble, provenance, the decision layer |
| `test_forecast_evaluation.py` | Walk-forward protocol, calibration, leakage |
| `test_decision_and_scenarios.py` | Decision cascade, scenario propagation, routing |
| `test_weather_expert.py` | Weather features and the known-future covariate |
| `test_global_eye.py` | Ingest, dedupe, corroboration, exposure, the timing gate, calibration thresholds |
| `test_agents_and_mcp.py` | Access levels, agent ceilings, Critic verdicts, the MCP protocol |
| `test_learning_ledger.py` | Ledger integrity, proper scoring, leakage raising, the attribution identity, policy promotion |
| `test_twin_and_cargo.py` | Twin determinism, constraint enforcement, the policy benchmark, cargo feasibility |
| `test_advisories.py` | The state machine, authorisation, visibility, the audit trail |

The suites assert the product's *claims*, not only its functions: that no tool
ships without a `computed_by`, that no agent holds an EXECUTE ceiling, that a
leaking reliability fit raises, that the same twin inputs produce byte-identical
metrics, and that a committed vessel is never told to divert.

---

## The research track

`run_demo.py`, `src/analytics/`, `src/storage/`, `src/streaming/`,
`src/dashboard/`, `src/webapp/`, `app/ui/` and `features/*.ipynb` are the
original research pipeline the product grew out of: a Streamlit dashboard, a
static web app, analytics exports, a SQL storage layer and a Kafka-style bus.

They are **kept deliberately** — they document how the modelling was developed
and they still run — but they are not the product. The product is
`run_award_demo.py` → `backend/` → `india-portwatch-terminal/`. Anything in the
research track that duplicates a product concern (its own port table, its own
dashboard) is superseded by the registry and the terminal.

---

## Artefacts

Both trees are gitignored: they are outputs, not sources, and a stale committed
artefact is exactly the kind of thing that makes a demo lie.

| Path | Contents |
|---|---|
| `outputs/expert_features/` | One CSV per expert, plus `merged_panel.csv` |
| `outputs/regimes/regimes.csv` | HSMM state, probabilities, dwell, transition risk |
| `outputs/forecasts/` | Forecast table, decisions, routes, and all benchmark artefacts |
| `outputs/analytics/provenance.json` | The run's provenance registry |
| `data/cache/*.json` | Exactly what the API serves |
| `outputs/portwatch_ledger.db` | Claims, outcomes, reliability weights, policies, and the ledger audit |
| `outputs/portwatch_advisories.db` | Advisories and every state transition |
| `data/portwatch/` | The IMF PortWatch snapshot (committed, so the demo runs offline) |

---

## Where to look for a number on screen

| If you see | It came from |
|---|---|
| A congestion figure | `outputs/forecasts/forecast_table.csv` ← `src/forecasting/ensemble.py` |
| A regime label | `outputs/regimes/regimes.csv` ← `src/regimes/hsmm_model.py` |
| An action | `outputs/forecasts/decisions.csv` ← `src/decision/decision_layer.py` |
| An accuracy claim | `outputs/forecasts/model_benchmark.csv` ← `src/evaluation/model_benchmark.py` |
| A LIVE / STALE badge | `data/cache/provenance.json` ← `src/utils/provenance.py` |
| A scenario delta | Computed per request by `src/decision/scenario_service.py` |
| An event's impact chain | Computed per request by `src/portwatch_os/global_eye/exposure.py` |
| A berth, crane or yard figure in the twin | `src/portwatch_os/twin/state.py`, simulated forward by `twin/simulation.py` |
| A policy's reward or its promotion state | `outputs/portwatch_ledger.db` ← `src/portwatch_os/twin/{rl,promotion}.py` |
| A number inside an advisory | The twin simulation named in the advisory's own `evidence` |
| A figure in an agent's answer | The tool named in its trace, and that tool's `computed_by` |
| A reliability weight or an attribution bar | `outputs/portwatch_ledger.db` ← `src/portwatch_os/learning/*` |
| `unavailable` with a reason | The module refused to state a number it could not measure |
| `n/a` | The pipeline genuinely did not produce that value |
