# Repository map

What each directory is, what it owns, and what it is not. Written so a reviewer
can find the code behind any number on screen in one hop.

Last reviewed: 2026-09-08.

---

## The one-line version

```
src/          the intelligence:  ingestion → experts → regimes → forecasting → decision
backend/      the API:           serves artefacts, computes nothing
india-portwatch-terminal/        the operator UI, one typed client, no local data
scripts/      operations:        refresh loop, artefact gate, UI smoke test
outputs/      artefacts:         features, regimes, forecasts, benchmark  (gitignored)
data/cache/   API cache:         the JSON the terminal reads               (gitignored)
```

`run_award_demo.py` is the single entrypoint that runs `src/` end to end and
writes both artefact trees.

---

## `src/` — the intelligence pipeline

| Path | Owns |
|---|---|
| `src/utils/port_registry.py` | **The single source of truth for ports.** Model id ↔ UN/LOCODE ↔ PortWatch feed id ↔ geography ↔ capacity, with tolerant lookup and legacy aliases |
| `src/utils/provenance.py` | The `LIVE / CACHED_LIVE / STALE / SYNTHETIC / UNAVAILABLE` state machine, with automatic downgrade when a claim outruns its timestamps |
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

## `backend/` — the API

| Path | Owns |
|---|---|
| `backend/app/main.py` | App assembly, CORS (configurable by env) |
| `backend/app/routes/` | Nine routers: health, provenance, ports, model, weather, news, sar, fleet, scenarios |
| `backend/app/services/cache_service.py` | Read-only artefact access. Missing artefact → 503 naming the rebuild command |
| `backend/pipeline/export_award_cache.py` | Exports the primary artefacts (port state, forecasts, regimes, decisions, pipeline nodes, benchmark, vessels, fleet, run status) |
| `backend/pipeline/export_support_cache.py` | Exports the weather and event caches from measured values |

**The API computes no intelligence.** If a number is not in an artefact, the API
does not have it.

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
| `src/routes/` | Eight screens, one file each |

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
| `ui_smoke.py` | Drives all eight screens at three viewports, failing on console errors, failed requests or horizontal overflow |
| `download_nasa_weather.py`, `preprocess_weather.py`, `explore_weather.py` | Historical weather preparation for the research track |

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
| `n/a` | The pipeline genuinely did not produce that value |
