# Data honesty ledger

Field by field: what is measured, what is derived, what is a proxy, and what is
absent. If a reviewer wants to attack a number, this page tells them where to
aim — which is the point.

Last reviewed: 2026-09-08.

---

## The rule

> A synthetic fallback is never presented as a measurement.

Enforced in three places: `src/utils/provenance.py` (the state machine, with
automatic downgrade), `backend/app/routes/*` (nullable fields, 503 on missing
artefacts) and the terminal's `Value` component (renders `n/a`, never a
stand-in). `scripts/verify_artefacts.py` fails the build if any of it slips.

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

## Absent by design

| Claim not made | Why |
|---|---|
| Individual vessel positions | No commercial AIS licence. The map draws port-call aggregates and says so |
| SAR vessel detections, dark vessels | No Sentinel-1 scene ingestion. `/api/sar/feed-adapters` reports it `UNAVAILABLE`, confidence 0.0 |
| Measured berth-wait times | Not published openly. The proxy is labelled everywhere |
| Berth-level allocation | Operator-internal data |
| Inference latency, throughput, PSI drift | The Model Intelligence screen previously displayed all three as fixed numbers. Removed — this deployment does not measure them |
| Model cards for architectures we do not run | Removed. The pipeline reports the model it actually used |

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
