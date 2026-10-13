# Restored application: current-input workflow verification

Verified locally on October 10, 2026. This responds to `RESTORED_CAPABILITY_REVIEW_FEEDBACK.md`, which remains unchanged. The preview is at **http://127.0.0.1:4198**; the API is at localhost:9297. Nothing was published or deployed.

## Preserved application and evidence

All eight protected Company, Vessel, Port, Admin and twin files from the previous restoration manifest still match `e906f6a6bd4388cd3c059b4d9a5de6759139528b`, ignoring checkout line endings. The original navigation, maps, traffic, environmental layers, inspectors, weather/traffic timelines and advisory register remain in use. Extensions enter through service adapters and panels inside these screens.

Verified authentication and server-owned role permissions remain in place. Each visitor's demo retains its own world, proposals, advisory register and outcome ledger. Switching roles carries the same visitor world through the original screens. Production identities and stores were not reset. The existing local review state was reused when restarting the preview.

## Response to the two model findings

- **RL metadata:** the standalone policy and report now both say `REJECTED`, share an experiment ID and bind the policy to the report's exact UTF-8 byte hash. The serializer writes those same bytes on Windows. Regression coverage loads the policy with its report present, also checks standalone rejection and refuses a mismatched report. The fitted table, scores, training curve, seeds, historical generation time and recorded experiment code hash are unchanged. Exact original files, the initial amendment and the subsequent byte-hash repair are preserved under `work/current-inputs-review/rl-before-metadata-amendment/`.
- **Neural dropout:** training now hides a dropped specialist's median, interval width and availability inputs from the gate and uses those masked inputs in the gradient, in addition to masking output weights. A missing median also hides otherwise available interval endpoints. The original rejected model and report are byte-identical to the prior review manifest; no retraining or promotion occurred. The mutable shadow prediction CSV has changed since that manifest and is separately hashed in the new verification record. A revised experiment requires a separate output directory; a new chronological evaluation under provider outages remains pending.

The retained neural test MAE is 5.9844 versus GBM 5.8279. The retained constrained RL reward is about −211.994 versus lookahead −179.314. Neither rejected candidate replaced its baseline.

## Current inputs connected to a dated shipping decision

Open-Meteo surface and offshore marine forecasts and the GDACS alert feed refresh independently of the October 2 IMF activity observation. Raw response bytes, snapshot hashes, receipt availability, requested units and valid hours are retained. Unknown provider issue and forecast observation times remain null. Refresh failure preserves the previous receipt time and marks its age honestly. A background refresh recovered a temporarily stale Chennai surface response; the final native preview showed current surface forecasts for all 13 registered ports.

The original map consumes hourly wind, gust, visibility, precipitation and available marine wave forecasts. The weather timeline and map controls remain intact. Forecast fields are labelled as forecasts; unavailable storm probabilities and operational impact are not invented. The activity status continues to show its October 2 origin and **STALE 9D**. Refreshing weather does not make the congestion forecast current.

The completed native browser journey used **PW Meridian → INNSA**:

| Step | Visible consequence in the original screen |
| --- | --- |
| Signal and exposure | The consumed October 18, 11:00 UTC forecast has gusts of **15.9 kn** and visibility of **13,920 m** at the voyage's destination. |
| Explicit demo assumptions | Maximum gust **15 kn**, minimum visibility **5,000 m**, and **two consecutive clear hourly forecasts**. These are operator demo assumptions, not an official port operating limit. |
| Changed comparison | Arrival at 11:00 UTC incurs **4 h of assumed anchorage wait**; the first forecast-clear approach begins at **15:00 UTC**. A proposed arrival at that time incurs **0 h of assumed anchorage wait**. Both alternatives reach the same clear approach window. |
| Company | Created the comparison in original Global Eye, marked it reviewed and approved the proposed arrival. |
| Port | Reviewed the identical frozen Company input in original Advisories, approved the comparison, created the original DRAFT advisory, reviewed it and issued it. |
| Vessel | Opened the issued advisory in original Vessel Advisories, acknowledged receipt and accepted it. |
| Port outcome | Completed the advisory and displayed **SIMULATED_DEMO_OUTCOME: 4.0 h → 0.0 h**. The result is reproduced from frozen assumptions and is not an independent observed wait, forecast verification, berth guarantee or measured saving. |

The first native run completed at approximately **13:55 UTC**. After restarting the preview, a fresh visitor run completed at approximately **16:21 UTC**, using the **16:13 UTC** source receipt. Its identifiers are:

- Company comparison: `dec-arrival-6d2fcbc054d717eb4f75`
- Port comparison: `dec-arrival-6d2fcbc054d717eb4f75-port`
- Completed advisory: `ADV-INNSA-1441107190`
- Frozen evidence: `8fbea20be28c315bad40ed4af0a20623ad5d894fcff8e8024215aedfabecf980`
- Surface snapshot: `ff3a92daf69fa548163524d1e5dd68af0c918b8eb333f8a95cce5ed5f1b63f95`

The same frozen evidence is visible throughout the chain. A proposal alone does not change the demo fleet ETA; the explicit demo outcome applies the selected fictional arrival. Current-weather decisions cannot be submitted as observed forecast outcomes. Expired snapshots, replay mode, premature outcomes and other visitors' proposals are refused. Durable advisory/ledger evidence survives a process restart; mutable decision comparisons must be recomputed after a restart.

GDACS events retain publication and event-validity times as regional context. They do not imply a port closure or a quantified voyage delay. The broader God's Eye integration, source coverage controls and camera register remain inside the restored application.

## Weather and camera acceptance status

The current five-day case is inspectable in Company Global Eye → **Current weather decision**. October 10 → October 15 retains original daily forecasts and explicitly shows **UNMATCHED** outcomes. The October 15 forecast is gust maximum **15.7 kn**, rain **0 mm/day**, and offshore wave maximum **0.56 m**. It has no valid observed error yet.

The public weather archive at 16:14 UTC contains **2,189 retained forecasts and zero matched observations**. Port Weather and Admin Learning retain the inspection controls. Rows display original, corrected and observed values, with signed raw/corrected errors when an observation exists and `Pending` otherwise. The origin label identifies receipt availability when provider issue time is unknown. Learned correction remains behind its chronological sample and validation gates.

Authorized real camera footage and reviewed labels are still absent. Existing camera registration, evidence/scenario adapters and synthetic software regressions do not establish camera accuracy or whole-port occupancy. Real-footage evaluation and the resulting evidence-review/scenario controls remain incomplete until authorized material is available.

## Verification and local review

- **76 backend tests passed**, with one FastAPI/Starlette test-client deprecation warning. The final run includes the Windows report-byte regression, current-input chain, freshness failures, authentication, demo isolation, weather feedback, camera planning and existing capability regressions.
- TypeScript check and production build passed.
- Targeted lint passed with zero errors; four existing Fast Refresh warnings remain in the original advisory/decision modules. The amended weather inspection panel has no lint errors or warnings.
- Eight protected restoration files and original neural training/report hashes were verified; RL fitted values and historical report fields were compared with the exact preservation backups.
- Both complete native browser runs have screenshots and text audits under `work/current-inputs-review/`. `verification.json` records integrity checks, source receipts, evidence IDs and proof-file hashes.

The preview is left on the completed Port advisory in the current visitor's demo. Use the **Demo role** menu to move between the original role screens while retaining this world. To create another weather proposal, switch to **Fleet Command → Global Eye → Current weather decision**. The current-input workflow is available in isolated demo sessions; it is not an operational vessel command.

![Completed result inside the original Port screen](D:/LogisticOptimization-_Capstone_168/work/current-inputs-review/port-resumed-completed-outcome.png)
