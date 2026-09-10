# Architecture

Where each layer's authority begins and ends, and why the boundaries are placed
where they are.

---

## The loop

```
OBSERVE  →  UNDERSTAND  →  FORECAST  →  SIMULATE  →  DECIDE  →  ACT  →  LEARN
   │                                                                      │
   └──────────────────── reliability, calibration, policies ◄─────────────┘
```

The last arrow is the one that constrains the design. Anything the system claims
has to be recorded in a form that can be checked later, which is why numbers come
from named deterministic modules and never from a language model: an invented
figure cannot be scored, and everything downstream of it would be measuring
fiction.

---

## Layers

```
┌──────────────────────────────────────────────────────────────────────┐
│  TERMINAL   TanStack Start · React 19 · MapLibre · Three.js          │
│  4 role workspaces, map-first, one API client, no local truth        │
└───────────────────────────────┬──────────────────────────────────────┘
                                │  HTTP, JSON, /api
┌───────────────────────────────┴──────────────────────────────────────┐
│  API        FastAPI. Route = shape + authorisation + 503 on missing  │
│             artefacts. No arithmetic, no fallback values.            │
└───────────────────────────────┬──────────────────────────────────────┘
                ┌───────────────┴───────────────┐
┌───────────────┴──────────────┐  ┌─────────────┴────────────────────┐
│  AGENT LAYER                 │  │  DETERMINISTIC CORE              │
│  orchestrator · specialists  │──▶  forecasting · twin · cargo      │
│  Critic · MCP server         │  │  global_eye · decision · routing │
│  Selects and reconciles.     │  │  Every number originates here.   │
│  Computes nothing.           │  │                                  │
└──────────────────────────────┘  └─────────────┬────────────────────┘
                                                │
┌───────────────────────────────────────────────┴──────────────────────┐
│  LEDGER + LEARNING   SQLite (WAL). Claims, outcomes, scores,         │
│  reliability weights, policies. Written before the answer exists.    │
└──────────────────────────────────────────────────────────────────────┘
                                ▲
┌───────────────────────────────┴──────────────────────────────────────┐
│  PIPELINE   ingestion → experts → regimes → forecast → decision      │
│  → export → learning pass. One command, artefacts on disk.           │
└──────────────────────────────────────────────────────────────────────┘
```

Two independent paths reach the core: the API for a human, the agent layer for a
question. Both call the same modules. There is no third path that computes its
own numbers, which is why a figure on a screen and the same figure in an agent's
answer cannot disagree.

---

## The pipeline

`run_award_demo.py` is the whole chain, in order, with each stage's artefact on
disk so a later stage cannot silently invent an input.

| Stage | Module | Produces |
|---|---|---|
| Acquire | `src/ingestion/portwatch_source.py` | The daily port-call panel |
| Specialists | `src/experts/*` | Eleven bounded 0–1 feature families |
| Panel | `backend/pipeline/build_features.py` | The merged model matrix |
| Regimes | `src/regimes/hsmm_model.py` | Regime state, probabilities, expected duration |
| Forecast | `src/forecasting/*` | Calibrated q10/q50/q90 per port per horizon |
| Evaluate | `src/evaluation/model_benchmark.py` | Walk-forward benchmark, ensemble policy |
| Decide | `src/decision/*` | Actions, expected saving, drivers, fallbacks |
| Route | `src/decision/route_optimizer.py` | Per-vessel alternatives with the trade-off |
| Export | `backend/pipeline/export_*.py` | The API cache and the provenance record |
| Learn | `src/portwatch_os/learning/*` | Ledger backfill, scoring, reliability, claims, policy gate |

The learning stage runs **last and reads only what the run already produced**. It
is wrapped so a failure degrades the learning screens rather than the pipeline —
the ledger is not load-bearing for the operational picture.

### Provenance is a state machine, not a label

`src/utils/provenance.py` holds the vocabulary the entire system speaks:

```
LIVE · CACHED_LIVE · STALE · SYNTHETIC · SIMULATED_TRAFFIC · SCHEMATIC · UNAVAILABLE
```

A source downgrades automatically with age. A missing artefact produces
`UNAVAILABLE` and the route returns 503 rather than an empty object — a screen
must be able to say "not exported" rather than "zero". See
[DATA_AUDIT.md](DATA_AUDIT.md) for the field-by-field ledger.

---

## The deterministic core

`src/portwatch_os/` is the operations layer added on top of the forecasting
stack. Each package owns its arithmetic and nothing else touches it.

| Package | Owns | Documented in |
|---|---|---|
| `global_eye/` | Event ingest, dedupe, corroboration, exposure chain, calibration | [GLOBAL_EYE.md](GLOBAL_EYE.md) |
| `twin/` | `PortState`, the simulator, the optimisers, the RL environment, the promotion gate | [PORT_TWIN.md](PORT_TWIN.md) |
| `cargo/` | Transshipment feasibility and assignment | — |
| `fleet/` | The carrier account interface and the demo carrier | — |
| `advisories/` | The port→vessel state machine, authorisation, audit trail | — |
| `agents/` | Tool registry, access levels, specialists, orchestrator, Critic | [AGENTIC_AI.md](AGENTIC_AI.md) |
| `mcp/` | The JSON-RPC server over the same registry | [MCP.md](MCP.md) |
| `ledger/` | Records, transitions, the append-only audit | [LEARNING.md](LEARNING.md) |
| `learning/` | Scoring, reliability, attribution, the Outcome Agent, backfill | [LEARNING.md](LEARNING.md) |

### One shared port state

`twin/state.py` is read by the 3D renderer, the discrete-event simulator, the
optimisers and the RL environment. That sharing is the justification for building
it: if the twin an operator looks at and the twin a policy trains in were
different objects, every result from one would be unfalsifiable in the other.

`state.py` contains no meshes, materials or cameras. The renderer projects the
state; the state knows nothing about the renderer.

---

## The agent layer

> **Agents orchestrate. Tools compute.**

Enforced, not encouraged: `ToolSpec.computed_by` is required and a test fails any
tool without one; every `Finding` names the tool that produced it and a test
asserts the agent was allowed to call it; a tool an agent did not declare returns
`DENIED` in its own trace.

Access has four levels, checked at call time in `ToolRegistry.call`:

| Level | Side effects | Highest agent holding it |
|---|---|---|
| `READ` | none | most specialists |
| `SIMULATE` | none | twin, route, cargo, scenario |
| `PROPOSE` | a pending record | the advisory agent |
| `EXECUTE` | real | **none** |

EXECUTE has two independent gates: the caller's ceiling (no agent is constructed
above PROPOSE, and over MCP at the default ceiling EXECUTE tools are not even
listed), and an `ApprovalContext` whose `human_verified` flag only
`approval_from_session` can set, which requires an authenticated session. There is
deliberately no path from agent output to that function.

The same `ToolRegistry` backs the internal agents and the MCP server. Two
registries would eventually disagree, and the one that disagreed would be the one
with the EXECUTE tool in it.

---

## The API

One rule: **a route shapes and authorises; it does not compute.**

| Group | Routes | Backed by |
|---|---|---|
| Core | `/ports`, `/forecast`, `/weather`, `/news`, `/model`, `/provenance`, `/health` | the exported cache |
| Decision | `/scenarios`, `/fleet` | `src/decision/*` |
| Operations | `/global-eye/*`, `/company/*`, `/port-twin/*`, `/cargo/*` | `src/portwatch_os/*` |
| Workflow | `/advisories/*` | `advisories/store.py` |
| Agentic | `/agents/*` | `agents/orchestrator.py` |
| Learning | `/learning/*` | `learning/*` + the ledger |

A route with no artefact returns 503 naming the command that produces it. A route
that could return a plausible default returns null instead, and the terminal's
`Value` component renders `n/a` — never a stand-in.

`POST /advisories/{id}/transition` is the only route in the system that changes
something a person outside it can see — issuing a draft, or a master accepting or
declining one. It builds its principal from the request headers and the store
enforces which role may make which transition. Identity is *asserted* rather than
verified in this deployment, and `/advisories/policy` says so in its own response
and names the function to replace. See [API_CONTRACT.md](API_CONTRACT.md).

### Roles

Four, resolved client-side from the demo adapter and carried to the API as
identity headers:

| Role | Workspace | Scope |
|---|---|---|
| `NATIONAL_ADMIN` | `/admin/*` | Every port, every company, the learning system |
| `PORT_AUTHORITY` | `/port/*` | One port: twin, cargo, advisories issued |
| `SHIPPING_COMPANY` | `/company/*` | One carrier: fleet, exposure, routes, advisories received |
| `VESSEL_OPERATOR` | `/vessel/*` | One vessel: its advisories and its port |

Advisory visibility is enforced server-side in `visible_to_recipient`, not by
hiding a route. Headers are ASCII-folded on both sides — a header carrying an
em-dash makes `fetch` reject before the request leaves the browser, so
`asciiHeader()` folds it client-side and `ascii_fold()` matches server-side.

---

## The terminal

TanStack Start with file-based routing, one route file per screen under
`src/routes/{admin,port,company,vessel}`.

| Concern | Where |
|---|---|
| API access | `src/services/{api,portwatch,portwatch-os}.ts` — every call, one place |
| Query cache | TanStack Query v5, keyed per artefact |
| Map | `src/components/map/*` over MapLibre GL |
| Weather composite | `src/components/map/weather-layers.ts` + `lib/maritime/weather-*.ts` |
| Traffic | `lib/maritime/traffic-source.ts` behind a `TrafficSource` interface, `replay.ts` implementing it |
| Time transport | `src/components/command/TimeTransport.tsx`, state in `traffic-context.tsx` |
| 3D twin | `src/components/twin/*`, Three.js, lazy-loaded |
| Role shell | `src/auth/*` and `src/components/app/*` |

**The client holds no operational truth.** It has no fallback numbers and no demo
data modules — the nine that used to exist were deleted, and their removal is
enumerated in DATA_AUDIT.md. What it does own is presentation state: which
overlay, which horizon, whether the cursor is playing.

`TrafficSource` is the seam a licensed AIS feed plugs into. The shipped
implementation is a deterministic replay engine and every surface showing it says
`SIMULATED_TRAFFIC`.

### Bundle

Three.js (~1.1 MB) is lazy-loaded, so it stays out of the entry bundle for the
screens that do not render a twin. The scene is rebuilt only when the port's
*shape* changes — a different port, or a different berth count — and merely
recoloured when the numbers change, so switching overlay never tears down the GL
context. Three.js is driven directly rather than through react-three-fiber: the
scene is a few hundred boxes that change colour, and a reconciler between React
and the scene graph would cost more than it saved.

---

## Storage

| Store | Holds | Why there |
|---|---|---|
| `outputs/` (CSV, JSON, Parquet) | Panels, forecasts, benchmarks, the API cache | Reproducible, diffable, inspectable without a server |
| `outputs/portwatch_ledger.db` (SQLite, WAL) | Claims, outcomes, reliability, policies, audit | Needs transactions, constrained transitions and query |
| `outputs/portwatch_advisories.db` (SQLite, WAL) | Advisories and every state transition | Same, plus the audit trail must be append-only |
| Browser | Session, overlay and cursor state only | Never operational values |

SQLite with WAL is enough: writes are one process at the end of a pipeline run,
reads are dashboard queries. Postgres would add operational weight without
changing a single guarantee at this scale.

---

## Testing

| Suite | Asserts |
|---|---|
| `tests/test_api_contract.py` | Every route's shape, and its 503 when an artefact is missing |
| `tests/test_award_intelligence.py` | Experts, regimes, ensemble, provenance, decisions |
| `tests/test_forecast_evaluation.py` | Walk-forward protocol, calibration, leakage |
| `tests/test_global_eye.py` | Dedupe, corroboration, the timing gate, calibration thresholds |
| `tests/test_agents_and_mcp.py` | Access levels, agent ceilings, Critic verdicts, MCP protocol |
| `tests/test_learning_ledger.py` | Ledger integrity, proper scoring, leakage raising, attribution identity |
| `tests/test_twin_and_cargo.py` | Twin determinism, constraint enforcement, policy benchmark |
| `tests/test_advisories.py` | State machine, authorisation, visibility, audit trail |
| `qa/tests/*.spec.ts` | Every screen at two viewports, against the production build |

The browser suite replays a recorded API, so it needs no backend and no network,
and it fails a screen that renders while throwing a console error, dropping a
request, or pushing the page sideways. It runs at 1920×1080, 1440×900 and
1366×768; CI runs the two outer ones, because for layout risk 1366×768 strictly
dominates the middle viewport. It also asserts the claims this product
makes about itself — that the weather composite is on by default, that a
schematic twin carries its banner, that an uncalibrated event says so rather than
showing a number, that no committed vessel appears in the action queue, and that
no agent in the catalogue holds an EXECUTE ceiling. Those are the easiest things
to break silently.

---

## Where to extend it

Each of these is a provider implementation behind an existing seam, not a rewrite.
**None is a current feature.**

| To add | Implement | Nothing else changes because |
|---|---|---|
| Licensed AIS | `TrafficSource` | The map already consumes the interface |
| Surveyed geometry | the layout generator in `twin/state.py` | Berths, cranes and yard are already typed objects |
| Commercial cargo | the shipment source in `cargo/model.py` | The feasibility rules are independent of the feed |
| A real carrier | `Company.from_provider` | The fleet screens read the account interface |
| Verified identity | the advisory identity function | The state machine already gates on role |
| A language model | `classify_intent`'s classifier callable, and narration | Neither can introduce a number the trace lacks |
