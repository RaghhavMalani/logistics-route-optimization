# Daily weather error analysis and shadow readiness

Local milestone on October 19, 2026, based on `1d99630320ce8eefd3e90be691dcb86706657eaa`. The public release is unchanged. The restored role screens, map/twin sources and hourly approach calculator remain unchanged.

## Observed evidence

The frozen local report at `2026-10-19T13:03:44.292428+00:00` is `wx-shadow-report-82dab5a55837268745582389`:

| Measure | Count |
| --- | ---: |
| Qualified matched forecast snapshots | 654 |
| Independent outcome targets | 117 |
| Distinct outcome dates | 3 |
| Context memberships across horizons | 195 |
| Repeated snapshots within those contexts | 459 |
| Exact analysis contexts | 117 |
| Collecting contexts | 117 |
| Shadow-validated / rejected corrections | 0 / 0 |

These are logical outcome identities, not 117 independent weather days. Ports and variables can share weather patterns. The same outcome can be compared with several forecast horizons; those memberships do not create new outcomes. Background collection can change later reports, so retain `asOf`, report ID and downloaded audit together.

For INNSA, Open-Meteo surface, daily maximum wind gust, receipt-calendar horizon +1 day, two targets (October 11–12) have forecast-minus-outcome bias **−2.25 kn**, MAE **2.25 kn**, RMSE **2.2506 kn**, and two underpredictions. This is a descriptive pattern in a very small sample. It does not establish a stable systematic miss or support correction adoption.

The retained five-day example remains open. Eligibility around October 21 does not guarantee the provider will return a complete outcome. The older claim without retained originals remains excluded from automatic reconciliation and fitting. Outcomes currently scored here are explicitly labelled ERA5 gridded reanalysis, not station measurements.

## Evidence qualification and identity

`WeatherShadowAnalysis` reads the existing forecast ledger and source archive without collecting or modifying them. It verifies retained forecast and outcome response SHA-256 hashes; source/product identity; first receipt/availability; requested and returned coordinates; units; target window; and all 24 original hourly sample labels. It recomputes both aggregates and checks them against the frozen claim and annotation. A newer forecast is never an outcome for an older forecast.

Legacy claims may derive a statistic or daily window from their immutable variable and target only when the annotation and recomputed original responses agree. The audit records that derivation. Original rows remain unchanged. Rainfall retains the original preceding-hour interval convention instead of being relabelled as a different daily total.

An exact context separates port, variable, provider, receipt-calendar horizon, season, outcome source/kind, unit, statistic, requested coordinate, forecast grid and outcome grid. Within each context and target, select the latest original prospective receipt; prediction ID breaks ties. Selection never depends on its error. Global outcome identity omits forecast provider/horizon/grid, preventing repeated comparisons from inflating evidence counts.

Horizon is target calendar date minus original response receipt date in UTC. It is not provider model-run lead time, which is unavailable. Each target also retains exact receipt-to-target-start hours and the full sampling window. Malformed, missing, future or mismatched evidence is pending or explicitly excluded; no replacement source is silently substituted.

## Chronological baseline and adoption criteria

The engine reuses the median residual baseline: fit `median(outcome − raw)` only on fitting targets. Order target blocks chronologically into fitting, validation, calibration and subsequent evaluation. Purge an earlier block's labels if they were not available before the next block's original forecast receipts. Preserve purged IDs, boundaries, membership and current block shortfalls. At least 32 targets nominally, and at least eight surviving targets in every block, are required; 32 alone may be insufficient.

Validation and subsequent evaluation MAE must each improve by **strictly more than 2%** against their respective raw forecasts. Calibration independently supplies the nominal 80% residual interval. Evaluation reports held-out coverage; it does not imply future coverage. Insufficient contexts remain `COLLECTING`, failed candidates `REJECTED`, and passing retrospective replay `SHADOW_VALIDATED`.

Retrospective success is insufficient for adoption. The explicit criteria additionally require at least eight genuinely prospective independent shadow targets with the same candidate version frozen before the original forecast receipt, target and outcome availability; prospective MAE improvement greater than 2%; review of interval coverage and limitations; and an explicit adoption record scoped to the daily context/version. This milestone implements no adoption action. Every report and candidate has `decisionEligible=false`.

New daily frames, daily research watches and arrival weather features consume the immutable raw forecast through a common fail-closed guard. Mathematical `VALIDATED` flags and preserved legacy `correctedValue` fields cannot enable consumption. Candidate values/version/evidence are inspectable separately. Historical predictions, approvals, advisories and outcomes are not rewritten. Daily candidates never alter hourly gust/visibility approach calculations. Both rejected neural/RL candidates remain rejected.

## Inspection contract

`GET /weather/shadow` accepts optional `portCode`, `variable`, `provider`, `horizon` and timezone-aware `asOf` filters. Future `asOf` and invalid filters return 422. The existing authenticated/demo adapters expose the same read-only public research report to all four roles without joining visitor records. No POST adoption endpoint exists.

The response freezes `analysisVersion`, `reportId`, `criteriaId`, `selectionPolicyId`, `asOf`, scope, exclusions, global counts, exact-context metrics, chronological readiness, raw/shadow comparison results, criteria and target/source membership. `GET /weather/evidence/{sha256}` serves hash-checked retained originals. Replaying the same `asOf` after backend restart returns the identical report against the retained archive.

In the original interface, open **Global Eye → Current weather decision → Inspect original five-day forecast and learning → Matched error analysis and daily correction shadow readiness**. The shared panel also appears through the existing Weather/Learning surfaces. Port, variable, provider and horizon filters select contexts. Inspect original forecasts and later outcomes, expand adoption criteria, or download the complete audit JSON. There is no adoption control or replacement workspace.

## Local validation

- **89 tests passed** across weather shadow/API/feedback/reconciliation, current-input journey/recovery, arrival workflow and weather cache. One existing Starlette/httpx deprecation warning remains.
- TypeScript and focused ESLint passed for the final panel changes.
- Real local API checks verified retained response hashes and recomputed aggregates, exact `asOf` replay, filtering, all four demo role read contracts, separate visitor state, raw daily consumption and both rejected models.
- An actual backend restart recovered the same disposable visitor and returned the identical frozen report above.
- Browser checks used the original Company/Global Eye screens: current weather was separately current, activity remained visibly stale, horizon filtering changed metrics, source inspection and audit download worked, and the panel remained collecting. Daily target wording uses the UTC target date rather than its next-midnight validity endpoint.
- All eight protected role/twin files match restored `e906f6a` after line-ending normalization. `current_arrival.py` matches the base commit.

Local preview: `http://127.0.0.1:4199/login`, backend `http://127.0.0.1:8798/api`. Automatic reconciliation remains enabled in the local backend. Durable state is the existing isolated local-state directory; it is not production state. Runtime reports, downloaded audit copies, screenshots and disposable QA credentials stay ignored under `work/weather-shadow-20261019/`; they must not be committed.
