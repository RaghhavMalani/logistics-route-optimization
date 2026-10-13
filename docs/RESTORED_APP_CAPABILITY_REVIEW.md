# Restored application: connected capabilities and local review

Updated October 10, 2026. The base remains the actual application recovered from `e906f6a6bd4388cd3c059b4d9a5de6759139528b`. The source restoration was shown before these extensions. The current result uses the original Company, Vessel, Port and Admin routes, navigation, maps, rich surrounding traffic, inspectors, weather layers, timelines, digital twin and decision/advisory components.

Local preview: **http://127.0.0.1:4198/login**. Choose a role's demo button. The isolated review API runs on `127.0.0.1:9297/api`. Nothing has been published, pushed or reset in Git.

## Connected workflows

The frontend API adapter maps original domain requests to `/demo/terminal` for demo sessions. The server binds these original routes to visitor-owned state, identities, ledgers, decisions, advisories, world branches, agents, replay and camera registry. Caller role headers cannot choose server scope. Operational API paths reject demo credentials. Private camera writes, operational refresh and financial administration are unavailable in the demo.

The original Company workspace displays PW Meridian, PW Coromandel and PW Konkan inside its original fleet and traffic context. The Vessel workspace owns only PW Meridian. The Port workspace uses INNSA and its original port views. Admin retains its original network workspace. Generated surrounding traffic remains labelled simulated; the scene contains 826 vessels in the reviewed full-fleet views.

Company option approval updates the isolated proposal and ETA. The Port decision uses the same twin and original berth/crane/slot alternatives, then creates advisories through the existing handoff boundary. Company receives them, Vessel acknowledges or accepts them, and Port completes them. The API regression exercises this whole chain. Role switching keeps the visitor's world; reset changes only that visitor's generation and clears its terminal stores and frontend queries. Verified operational authentication remains separate.

Implementation: `backend/app/routes/demo_terminal.py`, `backend/app/services/demo_terminal.py`, `src/portwatch_os/sandbox.py`, and the original frontend service/provider adapters.

## Forecast freshness and weather learning

The public refresh and ensemble pipeline ran successfully on October 9. Its latest IMF observation is **October 2**, with congestion targets **October 3–12**. Generation time and source observation time are separate. The API recomputes ages and counts remaining future dates; it does not move an old series forward when it is downloaded or generated again. On October 10, only October 11–12 remain strictly future targets. The original weather timeline still identifies the dates of the model's consumed weather features.

Prior forecast, status and decision exports are archived by content hash before replacement. The broader pre-refresh snapshot is `work/capability-upgrades/before-forecast-refresh.zip`. Export writes are atomic. This repairs the refresh/export path and its freshness reporting; it cannot remove the upstream observation lag or supply an unobserved current port measurement.

The weather archive contains **576 real retained public forecasts and zero matched later outcomes** at collection. Original Port Weather and Admin Learning show original/corrected/observed values, issue time, target date, lead, unit, matching status and correction status. The five-day case can be inspected by lead; the archive also retains other supported leads.

Matching requires the same port, variable, daily statistic, unit, provider and availability time. A new forecast cannot be an observation. ERA5 reanalysis is identified as reanalysis. The supervised residual correction uses chronological partitions and availability purging, minimum sample requirements and a validation gain threshold. A validated correction enters future features; with zero resolved outcomes no correction is claimed as trained or improved. Operational-effect error learning remains a distinct existing outcome-ledger workflow.

## God's Eye inside the original Global Eye

The additional globe uses the pinned upstream viewer/application lifecycle, its earthquake layer and cable source. React controls connect original ports, full original traffic, events, camera viewpoints and the new provider context. Port, event and vessel selections return to the existing workspace inspectors and decisions. Opening the globe suspends the original map's animated drawing and wind renderer while retaining its mounted state; closing resumes it. The original map, weather/ocean fields, lenses, cascades and timeline remain available.

| Source | Implemented coverage and limits |
|---|---|
| Original traffic | Full original demo replay, explicitly simulated. Operational AIS configuration is not borrowed by demos. |
| ADSB.lol | Selected port plus 250 nautical miles, bounded records and position age; volunteer coverage. Native review returned 25 aircraft. |
| CelesTrak | Stations catalogue, published orbital epoch and actual SGP4 propagation at current UTC; elements older than seven days are withheld. Native review returned 22 records. |
| USGS | Upstream earthquake layer through the application's fixed provider route. |
| NHC | Atlantic and eastern/central Pacific cyclone context; zero current features is a valid result. Indian Ocean tracks need an additional adapter. |
| OSM | Bounded roads, rail, industrial, warehouse and power context around the selected port. Final native review displayed 600 cached features for INNSA, fetched October 10 at 06:33 UTC. Geometry handling is verified against the provider response schema. Infrastructure is not a measurement of road congestion. |
| News and economics | Existing events, shipping exposure and cached economic series with their own dates/status. The new report list distinguishes archived reports and fictional scenarios. |
| Submarine cables | Optional reference dataset, labelled CC BY-NC-SA 3.0 and limited to demo use. |

The infrastructure adapter uses the documented [public Overpass endpoint](https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances) with an identifying User-Agent and bounded, cached queries. Its [geometry output](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL#Print_(out)) supplies lines and bounding-box midpoint markers. Provider failures produce unavailable or stale status, retaining the original source timestamp, not invented features. Aircraft and orbital context do not imply shipping delay. Transit agency feeds, FIRMS credentials, radio, surveyed camera projection and broader regional cyclone coverage remain incomplete.

Upstream code revision: `9542a5e58b19277d1f9b6698a46f69fdaa5fc5c1`, MIT. The cable data has its separate non-commercial licence. See the [upstream repository](https://github.com/bilawalsidhu/gods-eye-view), [ADSB.lol documentation](https://api.adsb.lol/docs), [CelesTrak formats](https://celestrak.org/NORAD/documentation/gp-data-formats.php) and [NHC product coverage](https://www.nhc.noaa.gov/productexamples/).

## Cameras and reviewed planning

The original Port Operations screen contains an additional authorized-viewpoint panel with coverage, pose basis, permission basis, source, timestamp, media type and explicit unverified/unconfigured health. The existing scoped image/video/HLS player is reused. Verified authorities can register their own camera; demos cannot register or read private operational feeds.

`src/portwatch_os/intelligence/camera_cv.py` implements a bounded offline foreground/occupancy experiment for timestamped authorized recordings. It needs an empty reference, fixed ROI and reviewed occupancy labels on separate chronological training/evaluation periods. It retains frame/reference/manifest hashes and reports precision, recall, false positives and false negatives. Rain, shadows and changed viewpoints can cause false foreground. It does not infer vessel identity or whole-port occupancy. Synthetic frames are regression fixtures only.

Computer-vision evidence requires a model version, frame hash and ROI. Evidence is immutable and defaults to needs-review. A recent reviewed berth observation can enter the original Port Twin decision panel. The authority explicitly selects the schematic berth and assumes a remaining hold duration of 0.25–6 hours. Evidence older than 30 minutes, unreviewed evidence, another port's evidence and non-berth viewpoints are refused. The helper clones the twin, retains any existing vessel identity and later release time, and changes only the selected berth's availability. Evidence, coverage, pose basis, original state epoch and operator assumptions are retained in the decision ledger before its computed payload is frozen. The selected scenario state is rendered by the original twin and uses the original alternatives and advisory workflow.

Regression verification shows changed simulated wait, ownership refusal, an unchanged observed snapshot and preserved decision evidence. **No authorized real footage or reviewed real occupancy dataset has been provided**, so there is no measured real-port CV accuracy or completed footage-based planning demonstration. Recording/evidence submission remains through the scoped API; automatic stream health collection and a camera evidence-review UI are still future work.

## Actual trained experiments

| Experiment | Result | Adoption |
|---|---|---|
| Neural expert fusion | Eight-unit nonlinear gate; 4,260 test rows. Test MAE 5.9844 versus GBM 5.8279 and equal weighting 5.9330; 80% interval coverage 87.75%. | **Rejected.** Actual shadow inference is exported; incumbent forecast remains. |
| Sequential constrained Q policy | 250 training, 50 validation, 100 test episodes with disjoint seed ranges. Test reward −211.994 versus lookahead −179.314. Zero hard violations and zero refused test actions. | **Rejected.** Available only for explicit simulator comparison; operator/advisory approval remains. |

The neural gate uses existing expanding-window out-of-fold specialist predictions, port, horizon, interval widths and availability masks, with source dropout and chronological target purging. Calibration has a separate partition. Issue-time source ages, historical weather vintages and causal regime labels are absent from this dataset and are excluded. The existing TFT was audited rather than duplicated. These reporting periods had already been examined in earlier benchmark work; this is a comparative experiment, not a newly untouched promotion holdout.

The Q policy makes sequential decisions, uses temporal-difference updates and masks infeasible joint berth/crane proposals before execution. The existing simulator independently validates submitted actions. Evaluation uses the same scenario family with different seeds, not independently held-out extreme scenario families. The policy and neural model are actual artifacts; neither establishes measured waiting-time savings, fuel savings or terminal performance.

Artifacts: `outputs/forecasts/neural_fusion.json`, `neural_fusion_report.json`, `neural_fusion_live.csv`, `constrained_rl.json`, `constrained_rl_report.json`. Reports retain experiment code/data hashes and seeds. Subsequent inference packaging changes do not rewrite those training hashes.

## Verification and preservation

The final focused backend run passed **64 tests** covering demo/operational boundaries, verified identity, original contracts and advisory chain, forecast ageing, weather matching, learned candidates and camera planning. TypeScript checking and the local production build pass. Targeted ESLint reports no errors and one pre-existing Fast Refresh warning for `applyPortPlan` beside its component. Original CRLF files are checked with their line endings respected.

Native browser review has rendered all four original workspaces, the weather archive, camera panel, Admin experiment comparisons and the actual additional globe. The local review also verified refresh, reset, logout and protected-route redirection. Native checks used the original Port composer to review and approve an alternative, create a draft, issue it, then acknowledge and accept it from the original Vessel screen. Build/test output and screenshots are in `work/capability-upgrades/`. `review-manifest.json` records artifact hashes and confirms eight key original role routes and the twin scene still match Git (ignoring checkout line endings).

The source restoration backups remain in `work/restoration-e906f6a/`, including the pre-restoration archive/patch and protected backend/evidence manifest. New public forecast/learning claims are additions; existing evidence was not reset. The October working tree contains substantial earlier work, so its whole Git diff must not be attributed to these extensions. No commit, reset, branch rewrite or publication was performed.

Reproduction, from the repository root (use the installed project runtime):

```powershell
$env:PYTHONPATH = 'work/test-runtime;.'
python scripts/serve_restoration_review.py
```

That script deliberately creates a fresh isolated review root. To retain a previous review, use its recorded state root instead of reprovisioning it. Build in `india-portwatch-terminal` with `NITRO_PRESET=node-server`, `VITE_PORTWATCH_AUTH_MODE=production` and **`VITE_PORTWATCH_API_BASE=http://127.0.0.1:9297/api`**; then run `qa/serve-build.mjs` with `PW_SKIP_BUILD=1` and `PORT=4198`.

Experiments can be reproduced with `python -m src.forecasting.neural_fusion` and `python -m src.portwatch_os.twin.constrained_rl`. The offline camera command is `python -m src.portwatch_os.intelligence.camera_cv manifest.json --output report.json`; it requires authorized inputs, not the synthetic test fixture as product evidence.
