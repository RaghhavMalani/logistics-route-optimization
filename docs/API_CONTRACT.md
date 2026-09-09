# API contract

FastAPI, mounted under `/api`. Interactive docs at `/docs`.

The API computes no intelligence of its own. It serves exactly what
`run_award_demo.py` exported into `data/cache/` and `outputs/`. A missing
artefact is a **503 naming the command that produces it**, never a placeholder —
the terminal renders the gap rather than a plausible number.

```bash
uvicorn backend.app.main:app --port 8000
```

---

## Provenance vocabulary

Every timestamped payload carries a `dataStatus` from this set. It is enforced,
not asserted: a source claiming `LIVE` whose newest observation is older than its
freshness budget is automatically downgraded to `STALE`.

| Value | Meaning |
|---|---|
| `LIVE` | Fetched from the provider this run, observation inside the budget |
| `CACHED_LIVE` | Real provider data replayed from cache, still fresh |
| `STALE` | Real provider data past its budget; usable at reduced confidence |
| `SYNTHETIC` | Modelled stand-in. Never presented as measured |
| `UNAVAILABLE` | Source failed with no usable fallback |

---

## System

### `GET /api/health`

The twin's operational state. Safe to poll; always 200.

```jsonc
{
  "status": "ok",                         // "degraded" until the first run
  "intelligence": "live",                 // live | cached | stale | not_ready
  "serverTimeUtc": "2026-09-08T06:50:05Z",
  "cacheAgeSeconds": 4726,
  "lastRefreshUtc": "2026-09-08T05:31:18Z",
  "model": "adaptive_ensemble",
  "forecastOrigin": "2026-08-28T00:00:00Z",
  "forecastOriginStatus": "STALE",
  "forecastOriginAgeHours": 269.5,
  "horizonDays": 10,
  "ports": 12,
  "availablePorts": ["INCCU", "INCOK", "..."],
  "artefacts": { "forecast": true, "benchmark": true, "provenance": true },
  "benchmark": {
    "available": true,
    "version": "walk-forward-v3",
    "bestModel": "Adaptive ensemble",
    "folds": 4
  },
  "sources": {
    "readiness": 0.829,
    "live": ["Macro: oil / FX / inflation (FRED)"],
    "cached": ["Marine weather (Open-Meteo)"],
    "stale": ["Port activity (IMF PortWatch)"],
    "synthetic": [],
    "unavailable": []
  }
}
```

The five source buckets are disjoint and exhaustive — a test asserts it.

### `GET /api/provenance`

Every source with its provider, observation and fetch timestamps, age,
confidence, row count and fallback.

```jsonc
{
  "readiness": 0.829,
  "counts": { "LIVE": 2, "CACHED_LIVE": 3, "STALE": 2, "SYNTHETIC": 0, "UNAVAILABLE": 0 },
  "sources": {
    "Marine weather (Open-Meteo)": {
      "status": "CACHED_LIVE",
      "provider": "Open-Meteo (ERA5 blend + ICON/GFS forecast)",
      "detail": "Daily wind, gusts, precipitation, visibility and significant wave height for 13 ports",
      "observed_at": "2026-09-08T00:00:00+00:00",
      "fetched_at": "2026-09-08T04:52:53Z",
      "ageHours": 4.88,
      "confidence": 0.9,
      "fallback": "local response cache",
      "rows": 6630,
      "isReal": true
    }
  }
}
```

---

## Ports

### `GET /api/ports`

All ports, sorted by name. Observed fields come from the merged expert panel;
forecast fields are labelled as such. **A field the pipeline could not measure is
`null`** — this route previously invented throughput and vessel counts from the
congestion index, and no longer does.

```jsonc
{
  "code": "INNSA", "name": "JNPA / Nhava Sheva", "short": "JNP",
  "authority": "Jawaharlal Nehru Port Authority",
  "location": { "lat": 18.95, "lon": 72.95 }, "coast": "west",

  "observedCongestionIndex": 71.2,        // measured
  "observedAt": "2026-08-28T00:00:00Z",
  "dataStatus": "STALE", "dataAgeHours": 269.5,
  "throughputTonnes": 472482.9,
  "vesselCalls": 9.0, "anchorageCount": 2.4,
  "queuePressure": 0.71, "capacityPressure": 0.68,
  "anomalyScore": 0.21, "weatherImpact": 0.18,
  "aisConfidence": 0.75, "dataQuality": 0.886,
  "congestionHistory": [{ "date": "...", "value": 68.4 }],

  "congestionIndex": 74.9,                // day-1 forecast
  "peakCongestionIndex": 78.2, "peakDay": 6,
  "delayHours": 13.6,
  "forecastQ10": 68.7, "forecastQ90": 81.0,
  "modelDisagreement": 0.047, "confidence": 0.77,
  "model": "adaptive_ensemble",

  "regime": "SEVERE", "regimeConfidence": 0.81,
  "transitionRisk24h": 0.12, "expectedRemainingDays": 1.0,
  "recommendedAction": "ADD_SHIFT", "priorityScore": 0.44,
  "risk": "severe"
}
```

### `GET /api/ports/registry`

The canonical registry: model id, UN/LOCODE, PortWatch feed id, geography and
static capacity attributes. This is the single source of truth every layer
resolves through.

### `GET /api/ports/{code}`

One port. Accepts the model id, UN/LOCODE, short name or a legacy alias
(`INHAL` → `INCCU`).

---

## Model intelligence

| Endpoint | Returns |
|---|---|
| `GET /api/model/ports` | Port codes present in the forecast cache |
| `GET /api/model/pipeline` | One node per expert and model, with signal, confidence, artefact path, row count and `available` |
| `GET /api/model/benchmark` | The walk-forward artefacts (below) |
| `GET /api/model/{code}/forecast` | 1..H day quantile forecast |
| `GET /api/model/{code}/regime` | Latest HSMM state plus 30-day history |
| `GET /api/model/{code}/decision` | Highest-priority decision and its full schedule |
| `GET /api/model/{code}/chain` | The evidence chain, in demo order |

### `GET /api/model/{code}/forecast`

```jsonc
[{
  "portCode": "INNSA", "day": 1,
  "targetDate": "2026-08-29T00:00:00Z", "originDate": "2026-08-28T00:00:00Z",
  "dateLabel": "29 AUG",
  "congestionIndex": 74.9, "q10": 68.7, "q50": 74.9, "q90": 81.0,
  "intervalWidth": 12.2,
  "delayHoursP50": 13.6, "throughputTonnes": 472482.9,
  "severity": "HIGH", "confidence": 0.77,
  "source": "adaptive_ensemble",
  "modelDisagreement": 0.047, "conformalOffset": 0.219,
  "dataStatus": "STALE", "dataAgeHours": 269.5
}]
```

Guaranteed: `q10 <= q50 <= q90`, `q10 >= 0`, `0 <= confidence <= 1`. Tested.

### `GET /api/model/benchmark`

```jsonc
{
  "available": true,
  "version": "walk-forward-v3",
  "target": "congestion_index", "horizonDays": 10,
  "protocol": "expanding-window walk-forward; a training row is used only if its label was observable at the fold cutoff; stacking weights fitted on out-of-fold predictions only",
  "summary": {
    "folds": 4, "testRows": 28740,
    "bestModel": "Adaptive ensemble",
    "bestMae": 7.4675, "bestRmse": 10.1854, "bestCoverage80": 0.8063,
    "naiveMae": 8.0834, "skillVsNaive": 0.076,
    "tftEvaluated": true,
    "ensembleMembers": ["persistence", "gbm", "second"]
  },
  "models":    [{ "model": "...", "n": 28740, "mae": 7.47, "coverage_80pct": 0.806 }],
  "byHorizon": [{ "model": "...", "horizon_day": 1, "mae": 3.74 }],
  "byPort":    [{ "model": "...", "port_id": "JNPT", "mae": 6.9 }],
  "byRegime":  [{ "model": "...", "regime": "SEVERE", "mae": 8.13 }],
  "calibration": { "levels": [0.5, 0.8, 0.9], "models": { "Adaptive ensemble": [...] } },
  "ensembleWeights": {
    "members": ["persistence", "gbm", "second"],
    "globalWeights": { "persistence": 0.4, "gbm": 0.4, "second": 0.2 },
    "byHorizon": { "1": { "persistence": 0.8, "gbm": 0.1, "second": 0.1 } },
    "conformalByHorizon": { "1": 0.219 },
    "fitted": true,
    "source": "stacked out-of-fold on 4 expanding walk-forward folds"
  }
}
```

When the benchmark has not been run: `{"available": false, "reason": "..."}`
naming the command. The UI renders that reason rather than blank tables.

### `GET /api/model/{code}/decision`

```jsonc
{
  "portCode": "INNSA", "severity": "medium",
  "title": "Add a handling shift", "action": "ADD_SHIFT",
  "target": "JNPT day 1", "horizonDay": 1,
  "actions": ["Add a handling shift and pre-clear yard space for day 1"],
  "rationale": "P(congestion>50) = 88% at day 1. Leading factors: congestion probability 0.26, capacity pressure 0.11, weather load 0.02.",
  "topDrivers": [{ "factor": "congestion probability", "contribution": 0.2646 }],
  "expectedImpact": "Relieves the day-1 pressure point; about 4.1h of expected wait is addressable within the forecast window.",
  "expectedDelaySavedHours": 4.1,
  "alternativeAction": "Extend gate hours and defer non-priority cargo moves",
  "uncertainty": 0.223, "confidence": 0.793,
  "congestionProbability": 0.879, "portEntryRisk": "High",
  "priorityScore": 0.44,
  "schedule": [{ "horizonDay": 1, "action": "ADD_SHIFT", "priority": 0.44 }]
}
```

Action codes: `HOLD_ARRIVAL`, `SLOW_STEAM`, `STAGGER_ARRIVALS`,
`REASSIGN_BERTH`, `ADD_SHIFT`, `YARD_OVERFLOW`, `PREPOSITION_MARINE`,
`ETA_BUFFER`, `DIVERT_PORT`, `MONITOR_DISAGREEMENT`, `MONITOR_QUALITY`,
`NORMAL`.

The three passive codes always report `expectedDelaySavedHours: 0` — a test
enforces it, because an action that changes nothing must not claim a benefit.

### `GET /api/model/{code}/chain`

Five stages in fixed order — `RAW SIGNAL`, `EXPERT`, `REGIME`, `FORECAST`,
`DECISION` — each with its metrics, confidence, observation timestamp and status.

---

## Scenarios

### `GET /api/scenarios`

The catalogue. Each entry declares only its shock type, scope, default severity
and the real-world analogue its elasticities are calibrated against. **No entry
stores an outcome.**

Keys: `HORMUZ`, `SUEZ`, `REDSEA`, `MALACCA`, `CYC_E`, `STORM_W`, `CAPDROP`,
`LABOUR`, `DEMAND`, `FUEL`. Aliases (`cyclone_east`, `red sea`, …) resolve.

### `POST /api/scenarios/simulate`

```json
{ "scenarioKey": "HORMUZ", "intensity": 1.0, "runId": 0 }
```

Applies the typed shock to the live quantile forecast through the measured
lane-exposure graph and returns the **difference between the two forecasts**.

```jsonc
{
  "scenarioKey": "HORMUZ", "scenarioName": "Hormuz closure",
  "intensity": 1.0, "severity": 0.85, "durationDays": 21,
  "forecastOrigin": "2026-08-28T00:00:00Z",
  "baselineModel": "adaptive_ensemble", "horizonDays": 10,

  "congestionDelta": 5.42, "delayDeltaHours": 1.43,
  "throughputDelta": -4.1, "freightDelta": 38.2, "oilDelta": 20.4,
  "confidence": 0.5,

  "affectedPorts": [{
    "portCode": "INMUN", "name": "Mundra", "coast": "west",
    "exposure": 0.55,
    "baselineCongestion": 66.4, "shockCongestion": 74.8, "congestionDelta": 8.4,
    "baselineDelayHours": 10.7, "shockDelayHours": 13.4, "delayDeltaHours": 2.7,
    "throughputDeltaPct": -6.2,
    "baselineCongestionProbability": 0.81, "shockCongestionProbability": 0.92,
    "probabilityDelta": 0.11,
    "extraSteamingDays": 0.0,
    "riskLevel": "high", "impactScore": 61,
    "confidence": 0.62, "modelDisagreement": 0.09
  }],

  "routeImpacts": [{ "name": "West coast corridor", "delayDeltaHours": 2.4 }],
  "chokepointImpacts": [{ "code": "HORMUZ", "riskLevel": "severe", "isShocked": true, "hasAlternative": false }],

  "recommendation": {
    "available": true, "action": "DIVERT_PORT",
    "instruction": "Evaluate diverting to NML: expected wait is 14h lower against 8h of extra steaming",
    "expectedDelaySavedHours": 6.1,
    "changedFromBaseline": true, "baselineAction": "ADD_SHIFT",
    "confidence": 0.61
  },

  "propagation": [
    { "step": "SHOCK", "label": "Hormuz closure", "value": "severity 85%" },
    { "step": "LANE",  "label": "Strait of Hormuz", "value": "freight +38.2%" },
    { "step": "PORT EXPOSURE", "value": "INMUN +8.4 · INIXY +6.9 · INNSA +6.9" },
    { "step": "ETA", "value": "+2.8h" },
    { "step": "ACTION", "value": "MUNDRA -> NML" },
    { "step": "EXPECTED BENEFIT", "value": "6.1h" }
  ],

  "method": "Live quantile forecast transformed by a first-order impact model over the measured lane-exposure graph. Deltas are the difference between the two forecasts; no scenario outcome is stored. This is a decision-support estimate, not a prediction that the event will occur."
}
```

`congestionDelta` per port always equals `shockCongestion - baselineCongestion` —
tested. With no live forecast the endpoint returns 503; it will not simulate
against nothing.

---

## Weather, events, vessels, fleet

| Endpoint | Returns |
|---|---|
| `GET /api/weather` | Measured Open-Meteo conditions per port plus the risk decomposition the model used and the shock/persistence split. Unmeasured fields are `null` |
| `GET /api/weather/{code}` | One port |
| `GET /api/weather/intelligence` | National marine synthesis |
| `GET /api/news` | Traceable events (headline, source domain, URL, attributed ports with lane exposure) plus the decision engine's port alerts |
| `GET /api/news/entity/{entity}` | Filtered by chokepoint, port or free text |
| `GET /api/sar/vessels` | Daily port-call aggregates, with `basis` stating they are **not** per-vessel AIS tracks |
| `GET /api/sar/feed-adapters` | Which vessel feeds are wired. Sentinel-1 SAR reports `UNAVAILABLE` with confidence 0.0 |
| `GET /api/sar/{code}` | Activity for one port |
| `GET /api/fleet` | Route optimizer output: intended vs recommended call with ETA, risk and port-wait deltas |

---

## Errors

| Status | Meaning |
|---|---|
| 200 | Success |
| 404 | The identifier does not exist in the registry or the cache |
| 503 | An artefact has not been exported. `detail` names the command that builds it |
| 500 | Unexpected server error |

```json
{ "detail": "forecast_by_port.json has not been exported. Run `python run_award_demo.py --source portwatch` to build it." }
```

---

## CORS

`PORTWATCH_CORS_REGEX` controls allowed origins; it defaults to localhost. Set
it to the exact deployed terminal origin in production, e.g.
`https://portwatch\.example\.com`.
