# Data honesty ledger

Field by field: what is measured, what is derived, what is a proxy, and what is
absent. If a reviewer wants to attack a number, this page tells them where to
aim — which is the point.

Last reviewed: 2026-09-10.

---

## The rule

> A synthetic fallback is never presented as a measurement.

Enforced in three places: `src/utils/provenance.py` (the state machine, with
automatic downgrade), `backend/app/routes/*` (nullable fields, 503 on missing
artefacts) and the terminal's `Value` component (renders `n/a`, never a
stand-in). `scripts/verify_artefacts.py` fails the build if any of it slips.

The vocabulary every layer speaks:

```
LIVE · CACHED_LIVE · STALE · SYNTHETIC · SIMULATED_TRAFFIC · SCHEMATIC · UNAVAILABLE
```

`SIMULATED_TRAFFIC` and `SCHEMATIC` were added in this cycle. They exist because
the operations layer draws two things that look observed and are not — vessels on
the water, and a port in three dimensions — and "synthetic" was too weak a word
for something a viewer will assume is real.

---

## Observed port state

| Field | Status | Basis |
|---|---|---|
| `vesselCalls` | **Measured** | IMF PortWatch daily satellite-AIS port calls |
| `throughputTonnes` | **Measured** | PortWatch import + export tonnage, 7-day trailing mean |
| `congestionIndex` | **Derived** | 7-day trailing calls vs the port's own expanding baseline; 50 = normal, 100 ≈ double. Leakage-safe (baseline shifted one day) |
| `utilization` | **Derived** | Trailing activity vs the port's historical peak |
| `anchorageCount` | **Derived** | Calls in excess of baseline. A queue *proxy*, not a counted anchorage |
| `delayHours` | **Proxy** | Excess call pressure mapped onto 0–36h above a 4h handling floor. No public feed publishes measured Indian berth-wait times |
| `queuePressure` | **Derived** | Logistic of call pressure against baseline, fused with capacity and berth pressure |
| `aisConfidence` | **Declared** | 0.75 for PortWatch daily aggregates, 0.35 for the congestion-derived fallback |
| `observedAt` | **Measured** | The newest PortWatch observation date for that port |

### What "congestion index" is not

It is not a queue count, a vessel-hours-waiting figure, or a berth-occupancy
percentage. It is a normalised pressure index derived from call volume against
each port's own history. The terminal labels it "0-100 pressure index"
everywhere it appears.

---

## Weather

| Field | Status | Basis |
|---|---|---|
| `windKnots`, `gustKnots` | **Measured** | Open-Meteo daily max, converted from km/h |
| `rainfallMm24h` | **Measured** | Open-Meteo daily precipitation sum |
| `waveHeightM` | **Measured** | Open-Meteo marine, significant wave height. `null` where the marine grid has no coverage |
| `visibilityKm` | **Measured** | Open-Meteo daily mean. `null` in the ERA5 archive window |
| `stormRisk` | **Derived** | GDACS alert severity blended with a low-visibility term |
| `impactScore` | **Derived** | Weighted composite of wind, rain, wave and storm risk |
| `weatherRegime` | **Derived** | `CALM / UNSETTLED / SHOCK / PERSISTENT` from the backward-looking shock and persistence terms |
| `forwardLoad` | **Forecast** | Mean weather risk over the next five known-forecast days. Legitimately known at the forecast origin |

### Fixed in this cycle

The previous exporter reverse-engineered physical values *out of* risk scores —
`windKnots = 8 + wind_risk * 28` — and presented the result as measurement. It
now publishes the Open-Meteo values the model actually consumed, and `null`
where the feed had nothing.

---

## Events

| Field | Status | Basis |
|---|---|---|
| `title`, `source`, `url` | **Measured** | The actual GDELT article or GDACS alert. Every headline links to its document |
| `severityScore` | **Derived** | Keyword-weighted severity by shock type |
| `affectedPorts` | **Derived** | Chokepoint events: the port's measured lane exposure. GDACS: exactly the ports the alert names. Unattributed headlines: a reduced national weight |
| `sentiment` | **Derived** | Tone from attributed event severity, not a language model's opinion |

### Alignment

The event feed is current; the port panel trails it by the PortWatch publishing
lag. Port-level news *features* are therefore keyed to the last observed panel
day, and an event newer than that day shows in the stream and the mention counts
but has not yet reached the model. The Event Intelligence screen prints the
alignment date beside the feature table.

### Fixed in this cycle

On the PortWatch path the news expert received an empty frame, so the
"News / Geopolitical" pipeline node scored 0.0 while still being drawn on the
Model Intelligence screen. It now receives a real, port-attributed event stream.

---

## Forecast

| Field | Status | Basis |
|---|---|---|
| `q10`, `q50`, `q90` | **Model** | Adaptive stack of persistence + GBM (+ TFT), per-horizon conformal calibration |
| `confidence` | **Derived** | Interval width × horizon decay × regime confidence, then discounted by model disagreement and by the data-quality expert |
| `modelDisagreement` | **Measured** | Spread of member medians relative to the blended band |
| `predicted_delay` | **Model** | GBM point forecast of the berth-wait **proxy**, so it inherits that proxy's status |
| `conformalOffset` | **Measured** | Fitted on out-of-fold predictions per horizon |

---

## Decisions

| Field | Status | Basis |
|---|---|---|
| `action` | **Rule** | Deterministic cascade over the forecast distribution and specialist state. No language model participates |
| `expectedDelaySavedHours` | **Computed** | Difference between the wait at this arrival day and at the cheapest day in the horizon. Zero for every passive action |
| `topDrivers` | **Computed** | Weighted contribution of each factor to the priority score |
| `confidence` | **Derived** | Forecast confidence discounted by disagreement and data quality |
| Slow-steam knots | **Computed** | `v' = v · H / (H + d)` over a nominal 48h approach at 13 kn, capped at an executable 3.5 kn reduction |

### Fixed in this cycle

The engine issued instructions like *"reduce approach speed by 10.6 kn to absorb
216h of waiting"* — arithmetically consistent, operationally nonsense. Actions
are now bounded to what a master or a berth planner can actually execute, and
diversions require the modelled saving to exceed the extra steaming with margin.

---

## Scenarios

| Field | Status | Basis |
|---|---|---|
| `congestionDelta`, `delayDeltaHours` | **Computed** | Difference between the live forecast and the same forecast after propagation |
| `exposure` | **Measured** | The port's lane-exposure weight for the shocked chokepoint |
| `freightDelta`, `oilDelta` | **Modelled** | First-order elasticities calibrated against documented analogues (Ever Given 2021, Red Sea 2023-24, Hormuz's lack of a bypass) |
| `confidence` | **Derived** | Forecast confidence discounted by disagreement and by how much of the port's activity the shocked lane explains |
| Event probability | **Not estimated** | This system does not predict whether a shock occurs, only what it would do |

### Fixed in this cycle

`/api/scenarios/simulate` returned a hardcoded `baseCongestionDelta` per
scenario multiplied by the intensity slider. Every number a reviewer could see
was a constant with a knob on it. It now propagates against the live forecast.

---

## Vessel traffic

Added in this cycle, and the single easiest thing in the product to mistake for a
measurement.

| Field | Status | Basis |
|---|---|---|
| Vessel position, course, speed | **Simulated** | Deterministic replay from a seeded schedule over the routing graph. Not an observation of any vessel |
| Vessel identity, name, operator | **Fictional** | Generated. `imo` is `null` rather than a plausible-looking number |
| Track history | **Simulated** | The replay engine's own past steps |
| Voyage origin, destination, ETA | **Demo** | Constructed against the real port registry, so the geography is right and the voyage is not |
| Traffic density | **Simulated** | A count of simulated vessels, not a traffic measurement |

Every surface that renders traffic carries `SIMULATED_TRAFFIC`. The replay engine
sits behind a `TrafficSource` interface
(`india-portwatch-terminal/src/lib/maritime/traffic-source.ts`); a licensed feed
is an implementation of it, and nothing above the interface changes.

### What is real about it

The **water** is. The routing graph guarantees a vessel is on navigable water and
transits the chokepoints its lane actually transits, so exposure computed against
these positions exercises the real graph. The graph is non-navigational: it
guarantees water, not a passage plan, and says so.

---

## Port digital twin

> **SCHEMATIC DIGITAL TWIN — NOT A SURVEYED PORT PLAN**

The banner is not dismissible and does not scroll away.

| Field | Status | Basis |
|---|---|---|
| Berth count | **Measured** | Port registry |
| Capacity index | **Measured** | Port registry |
| Berth occupancy | **Derived** | Queue pressure from the observed snapshot |
| Yard utilisation | **Derived** | Capacity pressure, weighted toward the quay |
| Queue length | **Derived** | The anchorage census proxy plus the run's arrival rate |
| Crane move rates | **Modelled** | Published equipment envelopes, not one terminal's measured productivity |
| Berth positions, yard block and shed layout, crane rail, gates, anchorage | **Schematic** | Generated from berth count and capacity index |
| Vessel size mix, exact arrival times | **Modelled** | Seeded from the measured count; the individual vessels are not real calls |
| Weather derating curve | **Modelled** | Zero throughput above impact 0.62 — a modelled cut-off, not a measured one |
| Yard friction curve | **Modelled** | Quadratic re-handle cost above 0.80 utilisation, floored at 0.45 |
| Gang size | **Modelled** | Roughly one crane per 90 m of LOA, capped at five |

The layout **scales off two real numbers**, so a large port gets a large twin and
a feeder port does not — but the arrangement is generated and the twin is not a
survey of any terminal. Seeding is deterministic: free-times derive from the berth
index rather than `hash()`, which is salted per process and would make two runs of
the same snapshot differ.

### What the simulator guarantees

Not accuracy — **determinism and constraint enforcement**. The same inputs produce
byte-identical metrics, so two policies can be compared; and a vessel too long or
too deep for a berth is refused whatever a policy asks for, with the reason
recorded in `rejected_actions`. Those are the two properties a policy benchmark
needs to mean anything, and they are what the tests hold it to.

---

## Cargo and transshipment

| Field | Status | Basis |
|---|---|---|
| Shipments, TEU, commodity, cut-offs | **Demo** | Generated. Carries `CARGO_DISCLAIMER` on every response |
| Connection feasibility | **Computed** | Handling hours against the departure cut-off, berth compatibility, yard headroom |
| Unplaced reasons | **Computed** | Every failing rule is collected, not just the first |
| Plan value | **Computed** | The stated `VALUE_WEIGHTS`, applied identically to every candidate |

The **rules are real and the data is not**. A commercial manifest feed would drive
the same feasibility logic unchanged, which is the only claim being made here.

---

## Carrier accounts

| Field | Status | Basis |
|---|---|---|
| Company name, fleet, voyages | **Fictional** | `fleet/company.py::demo_company` |
| `imo` | **Absent** | `None`, deliberately — a fabricated IMO number is a fabricated vessel identity |
| Exposure, deadlines, route options | **Computed** | The real exposure chain, run over the demo fleet |

No real Maersk, MSC or CMA CGM voyage appears anywhere in this repository.
`Company.from_provider` is the seam a real account integration fills.

---

## Advisories

| Field | Status | Basis |
|---|---|---|
| The recommendation in a draft | **Computed** | The twin simulation that produced it, named in the record |
| Critic verdict | **Computed** | Eight declared checks over the producing evidence |
| State, transitions, timestamps, actor | **Recorded** | Append-only audit trail per advisory |
| **Actor identity** | **Asserted, not verified** | Taken from the request session. `/api/advisories/policy` says so in its own response and names the function to replace |

Nothing in an advisory reaches the recipient before a named human issues it. The
draft state is invisible to the recipient, enforced server-side in
`visible_to_recipient` rather than by hiding a route.

---

## Agents

| Claim | Status |
|---|---|
| Numbers in an agent's answer | **Computed** by a named module. `ToolSpec.computed_by` is required and a test fails any tool shipped without one |
| Agent autonomy | **None over real actions.** No agent holds an EXECUTE ceiling, and EXECUTE additionally requires a human-verified approval context an agent cannot construct |
| Confidence | **Propagated**, bounded by the weakest link, never asserted. No evidence returns `None`, rendered as unknown |
| Intent classification | **Keyword matching.** The product ships with no language model configured; the classifier seam is optional and its answer is validated against known intents |
| Narration | Assembled from findings that name their source tool. A model may render it more fluently but cannot introduce a number the trace lacks |
| Tool trace | **Recorded** per run: agent, tool, outcome, duration, computing module |

A failed call and an *unavailable* one are distinguished. "The weather artefact
has not been exported" is a state the product reports; "the weather tool crashed"
is a defect.

---

## Events, exposure and calibration

Extends the Events section above, for the Global Eye layer.

| Field | Status | Basis |
|---|---|---|
| Event cluster | **Computed** | Merged only on category + anchor + 36h + headline overlap ≥ 0.34, all four |
| Confidence | **Derived** | Distinct outlets, saturating; a second independent feed counts for more than a second newspaper |
| Severity | **Heuristic** | A transparent word list, labelled as one on every surface. Maximum across a merged cluster, never the mean |
| Location basis | **Declared** | `reported` / `chokepoint_centroid` / `port_location` / `unlocated`. An inferred centroid is not a geocode and the inspector says so |
| Unclassified items | **Counted** | Items the classifier could not place are reported as a count, not forced into a category |
| Lane exposure | **Computed** | `severity × confidence × recency_decay`, over the lane catalogue's actual chokepoints |
| Detour distance and hours | **Computed** | The lane catalogue's alternative routing |
| Port risk across events | **Computed** | Noisy-OR, so no pile-up of events reaches certainty |
| Timing gate | **Computed** | A vessel within six hours of the strait is committed; `monitor`, never `divert` |
| **Event probability** | **Currently unavailable** | 26 claims are committed with horizons and none has elapsed; the threshold is 20 resolved outcomes. The UI shows severity and corroboration and prints the reason |

---

## Learning

| Field | Status | Basis |
|---|---|---|
| Resolved claims, MAE, bias, coverage | **Measured** | Scored against recorded observations. 4,000 resolved claims, MAE 6.33, coverage 0.881 against nominal 0.800 |
| Ledger history | **Backfilled from the run's own walk-forward evaluation** | `outputs/forecasts/walk_forward_predictions.csv`, produced under that evaluation's leakage discipline. **Not** generated, and **not** the README's headline benchmark — a different panel and horizon set |
| Error attribution | **Exact** | `y − predicted = Σ wᵢ(y − sᵢ)`, verified to close. Unavailable, with a reason, when the signals were not recorded |
| Reliability weights | **Fitted** | Resolved rows only, behind an `as_of` barrier that *raises* on a leaking row rather than skipping it. Shrunk toward 1.0, clamped 0.35–1.60 |
| Policy results | **Measured** | 40 held-out episodes on seeds disjoint from training. Bandit +5.6%, greedy lookahead +4.8%, greedy +4.3%, random feasible +2.6% against FCFS. Deterministic: the same seeds give the same table |
| Policy state | **Recorded** | The bandit is `REJECTED`: it beats FCFS by 5.6% but the best optimiser by only 0.8%, below the gate's threshold |
| Decision take-up | **Measured** | `ACTION_NOT_TAKEN` is recorded as carefully as `ACTION_TAKEN`, and take-up is reported next to reward |

A claim is written **before** its outcome exists, and `record_prediction` on a
resolved row raises rather than warns. Rewriting a claim after seeing the answer
is the most damaging thing a learning system can do to itself.

---

## Absent by design

| Claim not made | Why |
|---|---|
| Observed individual vessel positions | No commercial AIS licence. What the map draws is a deterministic replay engine, labelled `SIMULATED_TRAFFIC` on every surface, behind the `TrafficSource` seam a real feed would fill |
| SAR vessel detections, dark vessels | No Sentinel-1 scene ingestion. `/api/sar/feed-adapters` reports it `UNAVAILABLE`, confidence 0.0 |
| Measured berth-wait times | Not published openly. The proxy is labelled everywhere |
| Berth-level allocation | Operator-internal data |
| Inference latency, throughput, PSI drift | The Model Intelligence screen previously displayed all three as fixed numbers. Removed — this deployment does not measure them |
| Model cards for architectures we do not run | Removed. The pipeline reports the model it actually used |
| Autonomous action by an agent | Structurally excluded, not merely unimplemented. See the Agents section |
| A predicted probability that a world event occurs | Global Eye scores what an event *would do*, not whether it happens |
| A forecast storm track or cone | Storm motion is inferred from the risk gradient between stations. The artefact carries no track |
| Measured wind direction | The feed carries none. Monsoon climatology, labelled MODELLED wherever shown |
| Significant wave height where the marine grid has no coverage | `null`, not a substituted sea state |

---

## Fake telemetry removed in this cycle

A complete list, because "we removed the fake data" is only credible if it is
enumerable.

| Where | What it was |
|---|---|
| `backend/app/routes/scenarios.py` | Hardcoded per-scenario deltas; `"confidence": 0.82`; `"timestamp": "live"` |
| `backend/app/routes/ports.py` | `throughput = max(1000, 10000 - congestion*100)`, `vessels = max(10, 85 - congestion)` |
| `backend/app/routes/sar.py` | Two hardcoded vessels; `changeScore 0.58`; `darkVessels 4`; `"timestamp": "live"` |
| `backend/app/routes/fleet.py` | Three hardcoded vessels with fixed ETAs, risks and recommendations |
| `backend/app/services/port_service.py` | A `PORT_RISKS` table of hardcoded congestion, delay, throughput and vessel counts for every port |
| `backend/app/services/weather_service.py` | `get_weather()` returning constants by coast |
| `backend/pipeline/export_support_cache.py` | Physical weather values reverse-engineered from risk scores |
| `india-portwatch-terminal/src/data/*.ts` | Nine static demo modules merged on top of API responses |
| Model Intelligence screen | Hardcoded sparklines, `INFER LATENCY 182ms`, `THROUGHPUT 1.2k req/s`, `DRIFT (PSI) 0.09`, `ENSEMBLE CONF 0.86`, and model cards for a `tft-fusion-v4.2` with `params=18.4M` and a `sar-detector-v2` with `mAP=0.81` |
| Terminal shell | A permanently green "LIVE MODEL OUTPUTS" button, a `TFT-HSMM v4.2` chip, `IMD · INCOIS · ECMWF` and `SENTINEL-1 · S1-IW` source claims, a decorative weather-overlay control, and a wall clock labelled "MODEL RUN" |

---

## Silent failures found and fixed

Not fake data — worse: real machinery that had stopped working while still
looking correct.

| Bug | Effect | Guard now in place |
|---|---|---|
| `_fuse_specialists` called twice | Every specialist column was suffixed `_x`/`_y`, so `capacity_pressure` and friends never reached the model under their own names. The agents were decorative | `scripts/verify_artefacts.py` fails on a missing or suffixed specialist column |
| Specialists joined after the neutral fill | `assemble_panel` created placeholder columns first, so the later join was skipped and the model saw constants | The specialists are now joined inside `assemble_panel`, before the fill |
| Chokepoint name matching on a "Strait" prefix | Hormuz, Malacca, Bosporus and Gibraltar all resolved to `HORMUZ` | Distinctive-token matching, with a regression test |
| Ensemble scored on an inner join | The ensemble was evaluated on a quarter of the rows the baselines were, inflating its apparent skill | Left join plus per-row weight renormalisation; a test asserts equal row counts |
| Level-form models | Every learned model lost to a random walk at every horizon | Residual formulation, and the benchmark is what proved it |
