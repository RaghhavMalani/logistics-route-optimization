# Current Indian operational context

October 31, 2026. Work from `a11a9ac` on `feat/portwatch-restored-intelligence`; hosting deferred.

## Qualification policy fixed before collection

Selected candidate: Paradip Port Authority daily traffic reports, discovered through the existing approved `PublicPilot` collector and official traffic index. Source family `PARADIP_DAILY_OPERATIONAL_CONTEXT`; policy `paradip-daily-context-v1`. This adds a read-only Company projection over the canonical public archive, not another source store or research cohort.

The daily product is LATEST_AVAILABLE only when it is the latest successfully retained non-conflicting report. CURRENT_ELIGIBLE additionally requires a supported parser/section, verified original, actual available parse/check, a successful collection check within six hours and a report date of the present or preceding Asia/Kolkata calendar day. A section with an explicit snapshot clock must be no more than 36 hours old and not future. A date-only section uses a conservative whole-day uncertainty interval: its oldest possible as-of must be no more than 36 hours old. This bound is an age test, never a fabricated midnight publication or observation. Publisher publication time remains unknown. Asia/Kolkata interpretation of unzoned clocks remains an explicit assumption.

Prior-day traffic totals, the separately dated working-vessel snapshot, anchorage listings, expected-vessel programmes and planned movements retain distinct scopes. A working-section 06:00 header must not be assigned to the anchorage table without authority evidence. Missing/contradictory headings, unknown categories, layout changes or ambiguous rows withhold the affected metric. No age budget will be increased to obtain a successful demonstration.

This source provides destination-port context and optionally an acknowledged operator threshold on a supported reported metric. It supplies no individual waiting forecast, live AIS, port closure, berth reservation, all-fast, clearance or verified match to a fictional demo hull. Counts never become hours. Newly available unconsumed context does not invalidate a saved plan. Exact consumed product/metric/rule changes require explicit successor review.

## Display scope

The official website policy asks for permission for reproduction. No email or new permission is assumed. The application will show attributed factual metadata, clocks, hashes, bounded aggregate metrics and issuer links; it will not publicly serve the full PDF or copy report tables into the video. Original bytes stay in the existing local audit archive. The existing verified public-pilot archive and prospective cohort enrollment/matching protocol are not redefined by this context projection.

## Retained official receipt and capture-time change

Official catalogue: https://paradipport.gov.in/traffic/ . It selected https://www.paradipport.gov.in/uploads/2026/10/dtr3010.pdf . Original SHA-256: `9c1d0958bcae37b33dea35355bb4da9ca28a79708aaef3d09b12c603801d409c`; snapshot `cc1b591180041a7c75338bd3ea52611f964e38553422c943c6fd518377df4f5a`. Original first receipt: **2026-10-31 06:30:58.080060Z**. Publication time is unknown. A later unchanged check does not change that receipt.

The report is dated October 30. Prior-day traffic totals concern October 29. The working section explicitly says October 30 06:00; under the disclosed unconfirmed Asia/Kolkata timezone assumption this is October 30 00:30Z. It lists **19 working-section rows**, including completed/departed entries. The separately date-only anchorage section lists **6 READY and 7 NOT READY rows**. These are attributed report facts, not a current occupancy or delay estimate. Pages 1 and 3 were visually checked against the retained original; page/row/hash references remain in the additive context parse. Individual authority vessel names are not used to match fictional demo ownership.

At the actual morning qualification (06:40Z), the working snapshot was approximately 30.2 hours old and CURRENT_ELIGIBLE. The date-only anchorage section's conservative oldest-possible age already exceeded 36 hours: those metrics stayed LATEST_AVAILABLE. The working metric's 36-hour bound expired at **October 31 12:30Z (18:00 IST)**. A later actual catalogue check still returned the same report; at the recording-time view the working section is therefore **LATEST_AVAILABLE**. A fresh download does not restore operational eligibility. This milestone includes an actually collected current-eligible receipt and its subsequent honest aging, not a fabricated current event. Fresh live coverage after expiry remains dependent on a newer supported issuer report.

Parser `paradip-context-sections-v1.1` additionally rejects unclassified headings/rows and duplicate vessel names within the reviewed anchorage section. The older October 6 software fixture has an unclassified no-cargo heading, so its readiness aggregates are withheld by the stricter parser. Legacy v1 evidence remains inspectable under its original version. The new parse's actual availability is separately retained; no earlier prospective case or outcome is backfilled.

## Operational contract

`GET /api/demo/terminal/intelligence/port-context` and `/audit` authenticate and scope the owned voyage before reading the canonical SQLite archive with `mode=ro`, including committed WAL. They do not initialize PublicPilot, fetch a provider, create a call/comparison, rank an option or approve. Invalid stores/originals become unavailable. The explicit fixed-family refresh POST reuses PublicPilot; caller URLs/paths are not accepted. Existing collector scheduling remains the sole lifecycle; no new host automation was added.

Company explicitly declares a fictional INPRT destination and an integer threshold on one supported metric. A destination change creates a distinct owned INPRT call. A matching eligible metric can create a **separate Company source-review reason**; workflow stage and next-role remain intact. Consumed `portContextBindings` freeze product, revision, original hash, section time, exact metric, criterion and policy with `numericalEffect: null`. Exact consumed metric/time/rule/eligibility changes require a linked successor and fresh review. Unused metrics/reports do not invalidate a plan. An unchanged download deduplicates; a byte reversion is a new lineage event, while original first receipt is retained.

The current-input editor requires explicit acknowledgement of the exact eligible context and rule. Saved bindings cannot be silently dropped. Original evidence, prior chosen options, approvals and advisories remain in the ledger. The ordinary weather/passage/cargo engines supply any numerical comparison, separately from report context. A report count supplies no waiting hours, fuel, cost, safety or berth guarantee.

Software lifecycle sources are selected explicitly in the visitor's private DEMO world. They retain canonical fixture originals in that visitor's namespace; missing/corrupt fixture originals block approval. Their hours and outcomes never become real weather verification, port observations or learning samples. The frozen evidence view explicitly identifies software forecasts through Company, Port and Vessel inspection.

## Verification

The consolidated local regression run passed **269 tests**, including both clock audits, source/parser lifecycle, exact-binding reassessment, triage, passage/cargo/finance, workflow recovery and isolation. A later focused source/API run passed **13 tests** after the destination-call and distribution boundary changes; these overlap existing coverage and are not independent operational observations. A type-checked production build succeeded. Scoped lint has no errors; MapPanelAccess retains its existing mixed hook/component export warning. Browser/video evidence and any later validation results are recorded in DEMO_VIDEO_RECORDING.md.

A later unsupported section parse cannot refresh prior active eligibility: the last qualified metrics and successful-check time are retained with `RETAINED_AFTER_UNSUPPORTED_PARSE`. Ten focused source-context tests pass, including this refusal. The three scenario/API tests pass after enforcing route-preset ETA = computed remaining-primary distance / declared speed. These are software checks, not operational target counts.

## November 1 current receipt

A later explicit check discovered the new official report through the same catalogue: https://www.paradipport.gov.in/uploads/2026/11/dtr0111.pdf . SHA-256 `490e48be581f3e377c028395c56bc919a883e99ce628031ea4517b29cc87f0fe`; snapshot `a47249db587f3d5b0b879bcff0f40d40fd36bef200697bef77520a39dca26d05`. Original first receipt `2026-11-01T07:44:49.320498Z`; context available and successful check `2026-11-01T07:44:57.356053Z`. Its working snapshot is November 1 06:00 under the disclosed IST assumption (00:30Z); prior-day traffic is October 31. Publication remains unknown. The same fixed policy qualifies this as CURRENT_ELIGIBLE at the check; no budget was loosened.

Pages 1–3 were rendered and visually inspected. There are **22 named working-section rows**, including repeats at different berths and completed/departed entries: not 22 distinct vessels or live occupancy. Anchorage lists **3 READY and 13 NOT READY rows** under a date-only scope. Those sections also qualify within the conservative uncertainty bound at this check. A later provider/check/age failure still withholds active use.

The final connected example explicitly declares a Company review criterion on WORKING_LISTED_ROWS ≥ 20 for the S16 owned call. The existing editor creates a linked, unapproved successor with the exact current report/metric/rule binding; Company then reviews and approves it. Port and Vessel evidence disclosures expose that binding and its original hash. Weather, passage and cargo remain separately labeled illustrative inputs; the report count contributes no delay/fuel/cost number. Both old and new originals, prior comparisons and approvals remain retained.
