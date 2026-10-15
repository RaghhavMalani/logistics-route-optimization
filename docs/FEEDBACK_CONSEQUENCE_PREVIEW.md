# Feedback identity and an authority-supported passage decision

Implemented October 14; preview validation continued October 15, 2026. This extends the restored `e906f6a` application on `feat/portwatch-restored-intelligence`, based on `f876bcccaa52f38cd951631a0b397c35200d4d90`. Production promotion is separate. The eight protected role/twin files still match the restoration reference after normalizing line endings.

## Decision now supported

An official NAVCEN GeoJSON notice identifies the S.R. 74 Wrightsville Beach bridge and its scheduled closed-position interval on October 17, 04:30–10:15 local. The complete original source response is retained with SHA-256 `9ee303695c67f57dc69d3c5089e94bc72f3ab6a1342184f82e43e9e3c65128d7`. Provider creation/modification metadata remain distinct from unverified publication time and actual first application receipt. See [source review and usage limits](NAVCEN_SOURCE_REVIEW.md).

The visitor explicitly declares passage through this bridge, ordinary transit requiring an opening, vessel dimensions and onward travel. Destination membership and schematic vessel position cannot establish exposure. The operator also confirms `America/New_York` as the geographic local-zone interpretation; the MSI body does not name an IANA zone. The source separately permits vessels that can pass beneath the closed bridge and provides an emergency exception. This ordinary opening-requiring comparison cannot claim those exceptions as guaranteed access.

The example requests passage at **October 17, 12:00 UTC**. Under the declared local-zone interpretation, the restriction ends at **14:15 UTC**. The calculation is `(14:15 − 12:00) = 2.25 hours`. With **180 hours of operator-assumed onward travel**, both options reach the same conditional destination arrival at **October 25, 02:15 UTC**:

| Quantity | Continuing request | Revised request |
| --- | --- | --- |
| Requested bridge passage | Oct 17, 12:00 UTC | Oct 17, 14:15 UTC |
| Requested destination arrival | Oct 25, 00:00 UTC | Oct 25, 02:15 UTC |
| Conditional bridge access | Oct 17, 14:15 UTC | Oct 17, 14:15 UTC |
| Planned waiting at bridge | 2.25 h | 0 h |
| Total destination schedule shift from original request | 2.25 h | 2.25 h |

Revising the request relocates waiting. It does not establish faster delivery or measured savings. Actual opening, clearance, water level, route suitability, anchorage, arrival-to-berth wait and all-fast remain unavailable. Fuel, monetary, safety and capacity benefits are unavailable. A scheduled boundary is not an actual reopening or reserved transit slot.

The original Global Eye presents this source and declaration. Selecting the constraint focuses the existing map at the official point; outside its original clipped theatre it uses the already bundled Natural Earth country context. This is a geographic reference point, not a chart, closure polygon, surveyed twin or invented water route. The existing comparison timeline distinguishes restriction start/end, passage request and conditional destination arrival. Company approval, Port review/issue and Vessel acknowledgement/acceptance carry the identical frozen calculation and source into a labelled simulated action/outcome.

## Correct feedback identity

Every new operational call has persistent server-owned call and voyage-leg IDs, namespaced to the visitor's durable resources. ETA edits, source refreshes, linked successors and Company/Port copies preserve that episode. A confirmed distinct next call creates a new episode without resetting the visitor. Stable `requestId` retries recover the same call; conflicting reuse is rejected. Historical decisions, approvals, advisories and simulation records remain retained.

Each option freezes its semantic action basis: movement parameters, original arrival reference, declared route, characteristics, opening requirement and relevant assumptions. Each predicted metric separately defines the measurement basis: destination schedule shift, waiting at the declared access asset, or actual access instant. Action and metric hashes must agree with later actual records. Approval and Vessel acceptance do not prove execution.

Evaluation uses `LATEST_APPROVED_FORECAST_BEFORE_EXECUTED_LOG_CUTOFF_V1`: an actual record supplies an explicit forecast cutoff and execution time. Only approved, available vintages before that cutoff are eligible; the latest origin is selected, and semantically identical role copies count once. Other vintages remain inspectable. Conflicting cutoffs, actions, measurement bases, numerical revisions or tied incompatible vintages are excluded rather than resolved by database order. Evidence cannot become available before observation, and an operational metric cannot imply a measurement after its observation time. Old targets without stable call/action/measurement identity remain unscored.

The generated-identity regression now counts two calls by one vessel at one port as two targets: absolute errors 1 and 5 produce MAE 3. Same-call copies, successors and ETA edits cannot multiply targets. These are synthetic software fixtures, not real operational evaluation results.

## Scoped continuation and learning

The global reliability snapshot is retained for audit. Continuation checks the consumed claim assessment/applicability, relevant revisions, retained originals, actual consumer-bound applied policy parameters, expiry and current voyage/call declaration. An unrelated pending report or descriptive sample-count change does not invalidate approval. Relevant contradiction, cancellation, revision, corrupt originals, expiry, changed voyage or applied policy requires an explicit linked successor and fresh review.

Policy consumption is explicit: merely finding a matching validated policy row does not apply it. Current calculators bind no learned policy, retain neutral weight 1 and no correction, and remain **COLLECTING**. A future calculator must bind the actual consumed policy context and parameters; the guard rejects subsequent relevant changes. Both rejected model candidates and their historical evaluations remain rejected and retained. No RL promotion occurred.

Source verification, inferred exposure and conditional operational error remain separate. Authority revisions and syndicated copies are not independent confirmation. Announcement and actual occurrence are separate targets. Cancellation changes applicability without falsifying an earlier accurate announcement. Missing features or reports do not prove cancellation or non-occurrence. Full responses, receipts, semantic revisions, reversions and cancellations remain inspectable; unsupported semantics or provider failure block new action.

FX quotes and DEXINUS persistence forecasts remain inspectable and reconcilable. Economic context alone cannot create a vessel hold. No contract amounts or settlement dates are invented; reference-rate valuation, executable FX and realized savings remain separate future contracts.

Weather reconciliation keeps its independent backend schedule. First retained targets become eligible October 17 and the five-day case around October 21, subject to later provider availability. The older missing-original claim remains excluded. Daily corrections do not change hourly gust/visibility calculations. Real camera evaluation awaits authorized footage. There is no arbitrary article parser or public actual-operation upload endpoint.

## Validation scope

The final relevant local suite passed **238 tests** across feedback, notice parsing, weather, role boundaries, decisions, recovery and isolation. TypeScript, focused ESLint and the Vercel preview build passed. Regression data are explicitly synthetic; retained-source parser tests are historical extraction replay, not prospective forecasting accuracy. Current conditional comparisons freeze actually received inputs before the future passage target.

Private QA sessions, credentials, local captures, databases and temporary build packages remain under ignored `work/`. The release commit includes reviewed implementation, tests, the public source fixture and documentation only. Unrelated local activity-feed refreshes are excluded. Existing production evidence and visitor stores are not replaced.

## Hosted preview evidence

Preview: [restored PortWatch capability update](https://india-portwatch-eey5iptrx-flash2404s-projects.vercel.app/login). Frontend deployment `dpl_HUtdSQxf5FmM8oqneknuT2ENxVgd`; isolated backend deployment after the second recovery check `fa88f980-79cb-4345-aefc-7472c9ae4535`. The existing preview volume was retained. Production promotion was not performed; the observed public frontend remains `dpl_A1h2oea2ujsFCgL5BCx3hYvjYyYQ` and public backend `3d01cead-9e3e-4e6b-a4ca-064461408f8c`.

The hosted bridge journey passed 36 recorded API checks across preparation, continuation and recovery. An actual backend restart after Company approval recovered the identical frozen comparison; Port review/approval/issue, Vessel acknowledgement/acceptance and the labelled simulated outcome completed. Advisory and outcome retries returned the same records. A second actual backend restart recovered the completed outcome and preserved its evidence. A distinct next call was created without resetting the visitor, its retry recovered the same new call, and the historical comparison retained its original episode. Another visitor received 404 for the private comparison and no private impact targets.

Eleven further checks through the final Vercel proxy verified the original four role service contracts, collecting feedback, pending news/economic outcomes and the original economic source-response hash. The NAVCEN original was also retrieved through the authorized evidence endpoint and its full-response SHA-256 matched the retained fixture. These are software, provenance and workflow checks, not evidence of forecasting accuracy.

Browser validation completed the Company → Port → Vessel → labelled simulated outcome journey and inspected the original four role workspaces. The original map focuses the authority point and the existing timeline carries the scheduled restriction. Browser testing found and fixed a MapLibre bounds collapse when spanning the full world: a finite union of the original theatre and the selected source point preserves the existing renderer and avoids an invalid projection matrix.

The final frontend additionally passed Company login, source inspection, declaration, comparison and timeline checks with the corrected authority/access wording. At 390 × 844, the declaration dialog and comparison had no horizontal page overflow; the timing table remains an explicitly labelled horizontal scroll region. The 1366 × 900 desktop check retained the original map, point label, inspector and timeline. Temporary viewport overrides were reset. Local screenshots remain excluded from Git.

At October 15, 14:22 UTC, the weather archive held 7,723 retained forecasts over 936 independent targets, with **zero resolved independent targets** and no eligible retained targets yet. The 351 missing-original records remain excluded. **Real resolved operational independent targets: zero.** News corroboration and the inspected future FX observation remain pending. Both model candidates remain rejected. Descriptive news aggregation still needs an explicit policy for conflicting same-target report vintages before any resolved source-reliability claim; current targets are unresolved and no such weight is applied.
