# Prospective JNPA operational collection

Start in **Port → Operations → Start prospective cohort**, using a verified JNPA authority or national-command account. This freezes the collection protocol, model code hash, dependency versions and actor before enrollment. Every newly registered call joins the active cohort automatically. Previously registered operations and imported public berth evidence do not enter that cohort.

**Current priority: one qualifying future call.** Follow the [first-call data handoff](FIRST_CALL_HANDOFF.md) to agree an operational owner and source definitions, obtain a verified identity/individual baseline before arrival, then export and reconcile confirmed outcomes. The supplier request and empty templates are ready; no operational source or future call is agreed yet.

The cohort includes all enrolled calls before sealing. Record cancellations and duplicate aliases with a source reference; confirmed outcomes cannot be excluded after seeing prediction error. Exact same-MMSI/planned-arrival pairs are flagged as possible duplicates until the alias is resolved. Overlapping confirmed waiting intervals for the same MMSI are refused. These checks flag common duplicates; different planned times still require operator reconciliation against the canonical port-call reference.

## Sources we can import now

The official [JNPA daily berthing report](https://www.jnport.gov.in/page/berthing-report/M2VlS0pwUXZ3akhSV0E0RDFUVlhxQT09) provides terminal, berth, VIA call reference, vessel name, reported “Berthed on” and expected completion. The October 7, 2026 import staged **nine named berth records**. They appear as **awaiting verification** in the collection panel and contribute **zero qualifying prospective calls**.

Run from the repository root:

```powershell
python -m scripts.import_jnpa_public_report
```

Snapshots live in `data/jnpa/public_reports`. Each preserves the report date, exact source text for timestamps, fetch time, source-content hash and a stable parsed-fact hash. Reimporting unchanged facts preserves their first observation. The reader uses only snapshots available at the selected clock; layout changes fail instead of guessing column mappings. This is an explicit import, not a scheduled collector.

The report supplies neither MMSI nor a confirmed anchorage timestamp, and does not define “Berthed on” as all-fast. Expected completion is not a scheduler estimate of anchorage waiting. No timezone is asserted for these source strings. First observation now is a conservative availability bound; an old report date cannot establish when a record originally became available. Imported calls already berthed before collection cannot supply prospective forecasts or baselines.

The [JNPA bulk-terminal report example](https://www.jnport.gov.in/uploads/berthing_report/pdf/18/DAILY_REPORT_12082025.pdf) also contains anchorage arrival, berth arrival and reported waiting hours. That is a promising source adapter after confirming terminal/time semantics and call identity. Its past labels alone do not establish issue-time AIS, forecast availability, an individual frozen scheduler baseline, or all-fast semantics. The [daily status report](https://www.jnport.gov.in/page/daily-performance-report/L0RSb0dEcWVrQUxEM1VkaStJdG5xQT09) mainly supplies aggregate traffic and current berth information. Neither aggregate waiting nor AIS-inferred port arrival is substituted for confirmed all-fast outcomes.

## Individual baseline and confirmed measurements

Before the actual arrival, freeze the **individual scheduler waiting-hours estimate**, its source, reference, issue time and availability time. The server adds the immutable registration/recording timestamp and joins weather/AIS known then. The scheduler estimate must exist and be available by registration. Prospective outcomes must occur strictly after that claim; imports cannot backdate registration.

A verified operator or port-call log supplies confirmed anchorage-arrival and all-fast timestamps, **separate availability times for each record**, combined availability, berth, source and source reference. The server independently stamps recording time and actor. The confirmed waiting target is `(all-fast − anchorage arrival)` in hours, including a confirmed zero wait. Availability must follow each event and be no later than combined availability/server receipt.

Measurements may be collected without an advisory or action. Missing action evidence stays missing and an unexecuted decision remains open. An issued-advisory action still uses its separate source-backed workflow. Acceptance alone never supplies actual action, measured waiting, or realized benefit.

## CSV import and export

The collection panel offers header templates, a local CSV file picker and pasted CSV records. **Preview CSV** validates call identities and all time constraints using a rolled-back transaction. **Commit validated CSV** revalidates the entire batch and records it atomically at the server's current time. A bad or duplicate row rolls back every row. Up to 200 rows/250 KB are accepted. These endpoints require verified membership and LIVE even for preview; client-supplied roles do not authorize imports.

Arrival columns:

```csv
operationRef,mmsi,vesselName,recipientOrganisation,plannedArrivalAt,baselineWaitHours,baselineSource,baselineRef,baselineEstimatedAt,baselineAvailableAt,routeRevision
```

Confirmed outcome columns:

```csv
operationRef,mmsi,arrivedAt,berthedAt,arrivalAvailableAt,allFastAvailableAt,availableAt,source,sourceRef,kind,berthRef
```

Use ISO 8601 timestamps with an offset, for example `2026-10-08T10:00:00+05:30`. `kind` is `port_call_log` or `operator_confirmed`. Outcome imports require both an existing operation reference and its exact MMSI. Quoted CSV cells support commas in names or source descriptions. Baselines are not inferred from public schedules or aggregate queues.

**Export cohort JSON** returns all enrolled operations with frozen inputs, baseline provenance, decisions/advisory/action/outcome events, exclusions, quality flags, protocol and any sealed benchmark. It includes missing and unresolved calls, not only qualifying rows. Keep this export with the underlying operator logs for audit; an operator-provided reference alone does not archive the underlying document.

## Quality and evaluation

The panel distinguishes enrolled, confirmed and qualifying counts. It tracks missing weather/provenance, missing or stale AIS at issue, unresolved calls, outcomes overdue two days after planned arrival, possible duplicates and source-backed exclusions. Optional missing weather contributes to missing-evidence counts but does not automatically exclude a call; maximum-wind coverage and two AIS reports with latest source age at most one hour remain required. Current archive freshness is shown separately. Later AIS cannot repair a frozen case.

At least **60 qualifying calls**, and after chronological purging **24 fit, 10 calibration and 10 holdout**, enable evaluation. All enrolled calls must have a confirmed outcome or source-backed cancellation/duplicate disposition before sealing; missing-input confirmed calls remain visible in the quality report. Sealing saves all enrolled IDs and the full quality manifest. Counts do not themselves establish accuracy.

The fixed GBM uses 40 trees, depth 2, learning rate 0.05, absolute-error loss and seed 168. All comparisons use the same 60/20/20 issue-time partitions. Fitting/calibration labels received or recorded across the next boundary are purged. Previously fitted/calibrated outcomes cannot be proposed as holdout, and sealed holdouts remain reserved from future fitting. The model implementation/dependencies must match the preregistered cohort.

The report includes **MAE, signed bias (observed minus predicted) and nominal 80% interval coverage** for the full GBM, frozen scheduler and fitting-period historical median. Each estimator's interval radius comes only from its own calibration residuals. Positive bias means underprediction. The scheduler and median intervals are evaluator-calibrated intervals, not uncertainty supplied by the original scheduler.

Fixed additional GBMs consume scheduler-only, scheduler plus weather, and scheduler plus AIS inputs. Their holdout predictions and intervals are archived. Paired MAE reductions compare full weather/AIS against scheduler-only GBM and each single-source model. Positive reduction means lower error; negative means the added input worsened error. These are descriptive comparisons, not statistical significance, causal savings or grounds to tune on the holdout. Promotion continues to depend only on calibration performance against the scheduler.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/arrivals/collection` | Start the prospective protocol; retry returns the active cohort |
| GET | `/api/arrivals/workspace` | Quality, evidence chains and staged public facts |
| POST | `/api/arrivals/import` | `{recordType, csvText, commit}`; operations or outcomes |
| POST | `/api/arrivals/operations/{id}/disposition` | Confirm cancellation or identify a duplicate canonical operation |
| GET | `/api/arrivals/dataset` | Export the latest cohort, including unresolved/excluded calls |
| POST | `/api/arrivals/benchmark` | Seal the eligible prospective cohort and untouched comparisons |

The older direct registration/outcome API supports legacy fields for compatibility when no prospective cohort is active. Legacy cases are clearly separate from prospective enrollment; an active cohort requires the complete provenance fields.

Operational state currently has **nine staged public berth facts and no qualifying prospective calls**. Actual scheduler estimates, verified MMSI matches, confirmed all-fast evidence and live AIS collection still need a source. No private camera, neural fusion or RL is connected by this work.

October 7 validation: **16 targeted Python tests passed** across collection, arrival workflow and authenticated API behavior; the final three API tests were rerun with cohort-export membership checks. **Eight real-backend browser checks passed** at 1920×1080 and 1366×768, including CSV preview/commit, independent measurement, immutable originals, missing AIS, and authenticated cohort download. TypeScript, changed-file ESLint and verified-auth builds passed. Synthetic QA calls remain confined to isolated `work/verified-qa` stores and do not establish accuracy. The production arrival-event count was independently checked as zero. Python emitted an existing Starlette/httpx deprecation warning.
