# JNPA arrival evidence and waiting outcomes

The operator-confirmed operation workflow covers **JNPA / Nhava Sheva (INNSA)** in **Port → Operations**. It preserves weather/AIS evidence, a waiting claim, a controller's review, the existing advisory lifecycle, independently recorded actual action and a confirmed waiting outcome. The independent [public-data pilot](PUBLIC_PORT_PILOT.md) covers Paradip and Chennai with published ETA/reported-event targets. Other ports retain their existing weather and intelligence coverage.

The target is **hours from confirmed anchorage arrival to confirmed all-fast** for one named call. A port-call log or verified operator confirmation supplies both timestamps, the berth/reference and the time the evidence became available. AIS navigation status, congestion-index labels and generated twin calls do not supply this target. No savings or causal effect is inferred from prediction error.

The next collection milestone is implemented in the [prospective JNPA collection guide](JNPA_DATA_COLLECTION.md): preregistration, separate baseline/record availability fields, CSV preview/atomic import, independent measurement collection, quality counters and export. Nine official public berth facts are staged as awaiting verification; they are not qualifying prospective calls.

## Working with a call

1. Sign in as the verified JNPA authority or national command. Register the arrival/booking reference, nine-digit MMSI, vessel, recipient organisation, future planned arrival and route revision if available.
2. Supply the incumbent scheduler's **estimate for this individual call** and its source/reference. The twin's generated queue and aggregate mean waiting figure cannot stand in for that baseline. Until actual scheduling inputs are connected, this baseline is operator supplied and explicitly labelled.
3. The server joins the latest archived forecast for each weather variable covering the planned arrival day, with its original and consumed value, units, issue/target/recording times and prediction ID. It freezes available AIS reports for that MMSI from the preceding 24 hours. Later refreshes cannot alter these originals.
4. Review and approve the case. Create its arrival-review advisory, open it for review, then approve and issue it through the existing advisory state machine. It recommends review with the scheduler, with the estimate and missing inputs visible. It does not calculate an unevaluated arrival shift or command navigation.
5. The intended company/vessel receives and responds through the existing advisory workspace. Acceptance records a response; it does **not** resolve actual action or waiting hours.
6. Record what actually happened, including taken/modified/not-taken status, occurrence/availability times and execution-log reference. Record confirmed arrival/all-fast times, availability, source and berth reference independently. Routine calls may contribute measurements without an advisory/action; missing action stays missing and does not resolve an unexecuted decision. The first outcome is immutable. The UI shows observed waiting, signed error (observed minus predicted), interval coverage and the audit chain.

Recording actual action and resolving its prediction, decision and operation outcome use the same durable ledger. A failed outcome write rolls back the entire resolution. Advisory drafts live in the existing advisory database; a deterministic ID allows a draft created before a failed link write to be recovered by retry. The operator still has to issue it.

Overlapping measured waits for the same MMSI are refused. Training also deduplicates the same MMSI/confirmed arrival timestamp, so alternate booking references do not inflate the sample count.

## AIS collection and availability

The existing AISStream ingest now archives accepted timestamped position reports within 30 nautical miles of JNPA into `arrival_tracks` in `PORTWATCH_STATE_DIR/portwatch_ledger.db`. The normal ingest's provider credential/configuration is still required. Each row retains the normalized position, MMSI, provider, raw-message reference, source time, receipt time and independent recording time. The canonical report is retained even after the in-memory track expires; the raw reference alone does not guarantee indefinite raw-envelope retention. Configure the existing `PORTWATCH_AIS_RECORD_PATH` when a raw-envelope archive is required.

The radius is a candidate filter. Nearby Mumbai shares these waters; proximity and free-text destination do not establish JNPA membership, a berth boundary or vessel identity. The verified operator names the call and MMSI, and this match rationale is shown. Automatic geofenced arrival/berth detection and institutional port-call-log integration remain later adapters.

Reports with missing source timestamps do not enter this training archive. Reads require source, receipt and recording timestamps at or before the selected clock. Forecast joins require both issue time and the original ledger creation audit to be available. Historical views reconstruct operation/advisory steps available then; all writes require LIVE. No current camera feed joins this pilot; its absence is shown.

Legacy forecast creation audits have whole-second precision. The join conservatively waits until the end of that second and records this availability bound separately from the original audit stamp.

An existing recording can be imported with `python -m scripts.import_arrival_ais path/to/recording.jsonl`. This preserves original source/receipt times and deduplicates report IDs. Its recording time is the import time, so it cannot retroactively appear in an earlier replay or manufacture an earlier forecast claim.

## Prediction and untouched-period evaluation

Without enough measured evidence, the numerical estimate and uncertainty are **unavailable**, with explicit reasons. There is no conversion from congestion points to hours. At least two archived reports, a latest report within one hour and an issue-time maximum-wind forecast are required to score/train a call. Other missing weather variables have explicit missingness features. The daily forecast is a covariate covering the planned arrival day, not a measurement of conditions at a berth.

Start the prospective cohort before registering calls. Once at least 60 complete qualifying calls exist and all enrolled calls are resolved or have a source-backed cancellation/duplicate disposition, **Seal later-period evaluation** freezes the cohort. The fixed `arrival-wait-gbm-v2` implementation splits by issue time into earlier 60% fitting, next 20% calibration and final 20% holdout; equal issue instants stay together. Fitting/calibration outcomes that were received or recorded across the next boundary are purged. After purging, at least 24 fitting, 10 calibration and 10 holdout calls are required. This enables evaluation; it does not establish accuracy.

GBM uses 40 trees, depth 2, learning rate 0.05, absolute-error loss and seed 168. Inputs are the frozen individual baseline, five forecast weather variables, latest speed, track age/report count and nearby anchored-transponder count, plus missingness indicators. The count includes the JNPA candidate radius and is not asserted to be JNPA's queue length.

Promotion uses only the calibration period: GBM must improve calibration MAE by 2% over the incumbent. Otherwise the incumbent remains the point estimate. The selected model's separate calibration residuals supply the 80% interval. The headline report compares GBM, the frozen incumbent schedule and the training-period historical median on the untouched final period, with MAE, signed bias and separately calibrated interval coverage for each estimator. Fixed scheduler-only, weather and AIS ablations measure incremental predictive value on the same calls. It records partition IDs/times, row-level holdout predictions, dataset/code hashes, dependency versions and fixed parameters. Nominal coverage does not guarantee future coverage.

Sealed holdout IDs are excluded from every later fitting/calibration cohort. The evaluator also refuses a proposed holdout whose outcomes previously contributed to any issued prediction's fitting/calibration. Repeated evaluation of an unchanged cohort returns its original report. Changed code/dependency versions withhold prediction until the current implementation is evaluated on a new later period. These gates preserve an auditable untouched comparison rather than reporting fitted accuracy.

Current production state contains **no measured waiting-time prediction dataset**. This implementation supplies collection, workflow and evaluation capability; operational accuracy and realized benefit remain unestablished until actual arrivals mature. Synthetic QA inputs never populate the production ledger.

## API and validation

All `/api/arrivals/*` endpoints require a verified national-command or JNPA authority identity. Client role and port assertions do not grant access.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/arrivals/workspace?portCode=INNSA` | Evidence chains, missing inputs and the sealed report available at the current clock |
| POST | `/arrivals/operations` | Freeze a future arrival's evidence, baseline and decision |
| POST | `/arrivals/operations/{id}/approve` | Named controller review with a note |
| POST | `/arrivals/operations/{id}/advisory` | Recoverably create/link an existing-register draft |
| POST | `/arrivals/operations/{id}/action` | Source-backed actual action after advisory issuance |
| POST | `/arrivals/operations/{id}/outcome` | Immutable measured waiting and atomic ledger resolution |
| POST | `/arrivals/benchmark` | Seal/evaluate chronological measured calls |

The existing `/advisories/{id}/transition` controls issuance and recipient response. This pilot's accepted/declined responses stay separate from measured decision resolution.

Run the isolated real-backend browser fixture with `PW_QA_ARRIVALS=1 python -m scripts.serve_verified_qa`, a production-auth frontend using that API, and `PW_REAL_API=http://127.0.0.1:9281/api` for `qa/tests/arrival-workflow.spec.ts`. Its historical source/port-call fixtures are deliberately synthetic and confined to a fresh `work/verified-qa` directory. They test behavior and never establish maritime accuracy.

October 7 validation covered **188 distinct Python tests** across the targeted arrival/API, ledger/advisory, identity, camera/intelligence, weather and AIS suites. The final arrival/API suite passed all 11 checks. **Six real-backend browser checks** passed at 1920×1080 and 1366×768, covering the full chain, persisted original/error display, missing AIS withholding and independence from a failed aggregate-state request. Only the resilience check aborts the unrelated aggregate request; arrival/advisory APIs use the running backend and SQLite stores. TypeScript, changed-file ESLint and production builds passed. The Python run emitted an existing Starlette/httpx deprecation warning. Operational data collection, automatic port-call-log integration and real-world accuracy remain outstanding.
