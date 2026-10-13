# Global intelligence and weather feedback

Open **Global Eye → Open global intelligence**. This integration connects all **13 ports in the existing registry**. Private cameras require verified sessions and server-assigned membership. See [verified workflows](VERIFIED_WORKFLOWS.md) for provisioning and real-backend QA.

## Connected now

| Capability | Implementation and limits |
|---|---|
| Native globe | God’s Eye View lifecycle and Cesium viewer, lazy loaded inside React. Opening it unmounts the shipping map; returning destroys the globe and layers. Natural Earth imagery and Cesium workers are served locally. |
| News/exposure | Existing deduplicated PortWatch events, source links, timestamps and event → trade lane → port chains. Selection shares `WorldContext`; opening shipping decisions returns with that event selected. Exposure alone establishes neither voyage delay nor cost. |
| Economics | Actual cached FRED Brent, USD/INR and India CPI series with observation dates and stale/unavailable states. Context only: no fitted cost-impact model. Withheld in historical/scenario clocks because publication vintages are unavailable. |
| Earthquakes | Upstream earthquake geometry and USGS source normalizer through a fixed backend provider. Optional layer, five-minute in-process cache and at most one hour of stale fallback retaining the original retrieval timestamp. A quake is not automatically a shipping disruption. |
| Port CCTV | Durable registry, coverage, rights basis, estimated/supplied/surveyed position, scoped media display and immutable observations. Image/MJPEG/MP4/WebM/HLS supported. No feeds are preconfigured; URLs remain **UNVERIFIED** and frame timestamps are not assumed. |
| Weather feedback | Immutable originals, separately stored corrections, later outcomes, error scores by port/variable/provider/horizon and guarded residual learning. All existing ports participate when the weather fetch runs. |
| API contract | Request cancellation, 20-second default timeout and runtime Zod validation for the new intelligence response. Existing response schemas still need migration. |

God’s Eye View is pinned to `9542a5e58b19277d1f9b6698a46f69fdaa5fc5c1`. Imported modules cover application lifecycle, viewer, earthquake layer/source and camera media-type helpers. The complete source notice is served at `/gods-eye-view-LICENSE.txt`, linked from globe attribution. The product catalogue records the code and USGS provider. Upstream data packs, camera videos and event imagery are not copied into the app.

## Weather learning

The existing `fetch_port_weather` call records surface/marine snapshots using each response file’s original retrieval timestamp. This is **retrieval time**, not a claimed provider model-run issue time. Cached reads preserve it; distinct retrievals create distinct immutable snapshots. Only future complete UTC days are recorded. Old caches cannot create retrospective predictions. URL/parameter fingerprints prevent a different archive range or model from reusing an unrelated response; unsigned legacy caches require a successful fresh fetch.

Outcomes must be station/operator measurements or labelled reanalysis. The automatic resolver explicitly requests **ERA5**, after a conservative six-day lag, for wind, gusts and precipitation. Reanalysis contains model estimates; it is not a port station measurement ([Open-Meteo documentation](https://open-meteo.com/en/docs/historical-weather-api)). Forecast API `past_days` backfill never resolves outcomes. Waves and visibility need supplied observations.

| Variable | Unit | Required daily UTC statistic |
|---|---|---|
| `wind_speed` | `kn` | maximum 10 m wind |
| `wind_gust` | `kn` | maximum 10 m gust |
| `rainfall` | `mm/day` | precipitation sum |
| `wave_height` | `m` | maximum significant wave height |
| `visibility` | `km` | mean |

`validAt` is midnight UTC **ending** the target day; `availableAt` says when the observation became available. Timezones are required and both must be in the past. Mean wind cannot resolve a maximum-wind forecast. The first accepted outcome remains immutable; submit preferred station outcomes before automatic reanalysis if station validation is intended.

`weather-residual-v2` fits a median residual per port, variable, provider, season and exact horizon. Earlier outcomes fit the bias, a later block selects it and a third independent block calibrates the residual interval. Availability-crossing outcomes are purged before each subsequent block. Each block needs eight independent targets after purging; 24 total targets alone are insufficient. Hourly refreshes of one target do not inflate the count. Validation MAE must improve by at least 2%. Finite-sample nominal 80% conformal coverage is not a future guarantee. Inspection shows original → corrected → observed and explains `COLLECTING`, `REJECTED` or `VALIDATED`.

Validated corrections enter weather features and recommendations on the **next pipeline run**. Submitting an outcome only resolves the ledger; it does not immediately run the optimizer or execute actions. This build uses supervised correction; multi-provider weighting and neural residual models remain future work.

```bash
python run_award_demo.py --source portwatch
```

Ledger failures stop the weather step instead of losing claim history silently. Weather records use the existing ledger. Camera records/evidence use `PORTWATCH_STATE_DIR/intelligence.db`; include it in state-volume backups. `/api/health.durableStores.cameraRegistry` probes integrity. QA fixtures are never runtime fallbacks.

The October 6 initialization fetched weather for all 13 ports and recorded 576 available forecast values. All are pending later outcomes; no trained correction or measured improvement is claimed from this first fetch.

## Corrected evaluation

`chronological-holdout-v4` generates expanding-window base predictions, fits weights on earlier origins, calibrates on a separate later block and reports every headline on the untouched final fold. Crossing labels are purged at both boundaries. Full-history HSMM features and current future-weather forecasts without a historical issue-time archive are excluded. Fold-local regimes and archived forecast features remain future work.

`holdout_predictions.csv` supports metric recomputation. The summary records partition dates, dataset/code hashes, Git revision, seeds, dependency versions and configuration. It does not provide a Python dependency lock. The API withholds legacy benchmark headlines; old fitted ensemble policies use an explicitly unfitted equal-weight fallback. Rebuild before making updated accuracy claims:

```bash
python -m src.evaluation.model_benchmark --no-tft
python backend/pipeline/export_award_cache.py
```

Install `requirements-tft.txt` and omit `--no-tft` to include the existing TFT. Congestion-proxy accuracy does not establish measured waiting-time error or realized savings.

The benchmark records its offline feature/member setup. Current live weather covariates and a reduced production member set are not replayed by these headline metrics; a like-for-like production benchmark needs an issue-time archive and matched members.

The October 6 rebuild used 4,752 existing panel rows, with holdout origins from August 2 and targets through September 11, 2026. Each model was scored on 4,260 holdout rows; TFT was excluded from this run. GBM led with MAE **5.8403** congestion-index points, versus **6.8003** for persistence and **6.0650** for the ensemble. GBM's nominal 80% interval covered 80.99%; ensemble coverage was 87.58%. These are proxy-target benchmark results, not measured operational savings.

## Next build stages

1. **Public research application first.** Anonymous exploration, a clearer event → port → forecast → consequence → alternatives journey, sourced uncertainty, historical comparisons and reproducible downloads are described in [PUBLIC_RESEARCH_APP.md](PUBLIC_RESEARCH_APP.md). Prepare Vercel plus a persistent hosted backend; local Windows checks and waiting for a prospective call are not the main development roadmap.
2. **Forecast quality alongside background collection.** Compare chronological historical baselines and predeclared ablations, preserve availability semantics, separate weather fitting/validation/calibration and show actual errors by horizon. These proxy results do not establish operational savings. Keep Paradip/Chennai collection and the [JNPA operator handoff](FIRST_CALL_HANDOFF.md) available in parallel. A qualifying JNPA case still needs a verified future call, individual scheduler estimate, weather/AIS and confirmed arrival/all-fast. Subsequent operational evaluation still requires 60 qualifying calls with 24 fit, 10 calibration and 10 holdout after purging.
3. Expand news, economics and infrastructure through that same contract, followed by other aligned adapters. Each needs actual coverage, time semantics, rights and an evaluated operational relationship; exposure alone is insufficient.
4. Evaluate neural fusion after a useful consequence dataset exists. The holdout favors GBM over the ensemble and establishes no operational savings. Weather correction stays supervised. Neural promotion requires chronological improvement, calibration and missing-input checks.
5. Expand disruption/optimizer benchmarks, then evaluate sequential RL in the validated simulator. No new RL or neural-fusion policy is active here.

### First consequence contract

| Link | Required evidence |
|---|---|
| Signal | Stable source/forecast/evidence ID, source, observed/valid time, available/recorded time, units, coverage, confidence and review status. |
| Affected operation | Canonical port, vessel identity and route revision; observed/planned state with provenance and match rationale. Camera coverage stays limited to its viewpoint. |
| Expected consequence | Delay hours and/or cost with currency, horizon, baseline, interval, model/version and assumptions. An unavailable reason when the operational relationship is uncalibrated. |
| Recommendation | Existing decision ID, evaluated option, approval actor/time, advisory ID and recipient response. Preserve forecast originals and world revision. |
| Outcome | Actual arrival/wait/berth/service time or cost, source, availability time, actual action and immutable resolution. Savings need a defensible counterfactual. |

Weather predictions and reviewed camera evidence must be inputs actually consumed by the decision model, rather than nearby signals attached after computation. Fit the operational relationship on chronological data, compare against the incumbent and report missing-input behavior. Extend the existing decision/outcome ledger around this contract; do not invent delay conversion factors or claim savings from the congestion proxy.

The dependency audit found 13 inherited toolchain/MapLibre vulnerabilities; God’s Eye/Cesium/HLS packages were not identified in that report. Dependency remediation remains a separate upgrade task.

### Independent public-data collection

The [Paradip and Chennai public-data pilot](PUBLIC_PORT_PILOT.md) is implemented in Port → Operations. It archives official PDFs and freezes public ETAs before later reported outcomes, independently of the pending JNPA operator handoff. These reported-event targets remain separate from confirmed all-fast and individual scheduler estimates. The first real collection contains five original reports and 53 frozen future ETAs, with zero matched prospective outcomes; accuracy and savings remain unestablished. Neural fusion and RL remain later priorities.
