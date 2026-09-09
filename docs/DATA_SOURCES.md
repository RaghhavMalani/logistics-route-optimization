# Data sources

Every source this system uses, what it actually provides, how it degrades, and
what is deliberately *not* wired.

The governing rule: **a synthetic fallback is never presented as a measurement.**
`src/utils/provenance.py` enforces it, `/api/provenance` publishes it, and the
terminal renders it on every screen.

---

## Provenance states

| State | Meaning | Confidence weight |
|---|---|---|
| `LIVE` | Fetched from the provider this run, observation inside the freshness budget | 1.00 |
| `CACHED_LIVE` | Real provider data replayed from the local cache, still fresh | 0.90 |
| `STALE` | Real provider data past its budget — usable, labelled, discounted | 0.55 |
| `SYNTHETIC` | Modelled or generated stand-in | 0.30 |
| `UNAVAILABLE` | The source failed and no usable fallback exists | 0.00 |

A source declared `LIVE` whose newest observation is older than its freshness
budget is **automatically downgraded to `STALE`**. The system cannot claim
freshness it does not have, even by mistake.

---

## Wired sources

### IMF PortWatch — port activity

- **What:** daily satellite-AIS-derived port calls (by ship type) and
  import/export trade-volume estimates, per port.
- **Access:** public ArcGIS FeatureServer, no key.
- **Coverage here:** 12 of the 13 registry ports, roughly 16 months of daily
  history.
- **Refresh:** `python -m app.data.portwatch`, or `run_award_demo.py --refresh`.
- **Cache:** `data/portwatch/port_activity.csv`, `data/portwatch/history/*.csv`.
- **Publishing lag:** roughly a week. This is why the forecast origin trails
  today and why the terminal shows the age everywhere.
- **Derived, leakage-safe:** every baseline is an expanding statistic shifted one
  day, so day *t* only ever uses information up to *t−1*.

  | Derived series | How |
  |---|---|
  | `throughput` | 7-day trailing mean of import + export tonnes (real) |
  | `congestion_index` | 7-day trailing calls against the port's own expanding baseline, scaled so 50 = normal, 100 ≈ double |
  | `utilization` | Trailing activity against the port's historical peak |
  | `delay_hours` | **Berth-wait proxy.** Excess call pressure mapped onto 0–36h above a 4h handling floor |

  `delay_hours` is a proxy, labelled as one throughout. No public feed publishes
  measured berth-wait times for Indian ports; wiring port-authority dwell data
  would replace it directly.

### Open-Meteo — marine and surface weather

- **What:** daily maximum wind, gusts, precipitation, mean visibility and
  significant wave height per port, plus a 10-day forecast.
- **Access:** keyless. Forecast, marine and ERA5 archive endpoints.
- **Why three endpoints:** the forecast API backfills roughly two months; the
  ERA5 archive covers the rest of the port-activity history so the model trains
  weather-aware over its whole window; the marine API supplies wave height.
- **Cache:** `data/cache/openmeteo_*.json`, 3-hour TTL (7 days for the archive).
- **Known-future covariate:** the forward weather forecast is legitimately
  available at the forecast origin, which is what makes it usable without
  leakage.
- **Degradation:** unreachable with no cache → the weather expert falls back to
  GDACS storm flags alone and wind/rain/wave risk is reported as unmeasured.

### GDELT DOC 2.0 — maritime events

- **What:** recent maritime and geopolitical articles, classified into typed
  shocks (chokepoint closure, conflict, strike, sanctions, extreme weather) with
  an estimated severity.
- **Access:** keyless. 3-hour cache TTL.
- **Attribution:** a chokepoint event reaches a port in proportion to that port's
  **measured lane exposure**; an article with no lane attribution enters at a
  reduced national weight rather than hitting every berth equally.
- **Traceability:** the terminal shows each headline with its source domain and
  a link to the original document.

### GDACS (via IMF PortWatch) — disaster alerts

- **What:** climate and disaster alerts already intersected with specific ports.
- **Cache:** `data/portwatch/disruptions.csv`.
- **Feeds:** storm flags for the weather expert, and port-attributed events for
  the news expert.

### IMF PortWatch — chokepoint transits

- **What:** daily transit counts for six chokepoints relevant to Indian trade
  (Hormuz, Bab-el-Mandeb, Suez, Malacca, Panama, Cape of Good Hope).
- **Feeds:** the disruption propagation expert, which compares each chokepoint
  against its own expanding baseline and lags the result by the steaming time to
  the Indian coast.
- **Note:** the chokepoint name matcher requires a distinctive token. Matching on
  a "Strait" prefix folds Hormuz, Malacca, Bosporus and Gibraltar into one — a
  bug this project had, and a regression test now guards.

### FRED — macro conditions

- **What:** Brent crude, USD/INR and Indian CPI.
- **Access:** public CSV endpoints, no key.
- **Feeds:** oil, FX and inflation stress in the HSMM feature matrix.

---

## Deliberately not wired

These are reported `UNAVAILABLE` by the API rather than simulated.

| Source | Why not | What it would enable |
|---|---|---|
| **Per-vessel AIS tracks** | Requires a commercial feed (Spire, MarineTraffic, exactEarth) | Individual ship positions, headings, speeds and true queue composition |
| **Sentinel-1 SAR detection** | Requires scene ingestion (Copernicus/GEE) plus a detector | Cloud-independent vessel detection and dark-vessel cross-matching |
| **Port-authority dwell times** | Not published as an open feed | Replaces the berth-wait proxy with a measurement |
| **Berth-level allocation** | Operator-internal | Berth-specific rather than port-level recommendations |

The Vessel Activity screen states this explicitly, and
`GET /api/sar/feed-adapters` returns the SAR adapter with `status:
"UNAVAILABLE"` and `confidence: 0.0`.

---

## Offline behaviour

```bash
python run_award_demo.py --source portwatch --offline
```

Skips every network call and runs on the local caches. The provenance registry
records each source as `CACHED_LIVE` or `STALE` by its own timestamps, source
readiness drops accordingly, forecast confidence is discounted by the data
quality expert, and the terminal shows the degradation on every screen.

For a fully self-contained run with no cache at all:

```bash
python run_award_demo.py --source sample --offline
```

Every source is then recorded `SYNTHETIC`, and the UI says so. This is the path
CI uses, so the honest-degradation behaviour is tested on every commit.

---

## Adding a source

1. Write a connector under `src/ingestion/connectors/` that returns a tidy frame
   and calls `provenance.record(...)` with its provider, observation timestamp,
   row count and freshness budget — on both the success and failure paths.
2. Consume it in an expert under `src/experts/`, emitting bounded 0–1 features
   plus a `*_confidence` column.
3. Register the feature columns in `src/regimes/regime_features.HSMM_FEATURES`
   and `src/forecasting/tft_dataset._ORIGIN_FEATURES` so the signal reaches the
   model rather than only the dashboard.
4. Add the expert to `_EXPERT_SPECS` in
   `backend/pipeline/export_award_cache.py` so it appears as a pipeline node.
5. Add its columns to `REQUIRED_PANEL_COLUMNS` in
   `scripts/verify_artefacts.py`, which fails the build if the signal ever stops
   reaching the panel.
