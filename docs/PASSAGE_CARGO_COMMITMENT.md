# Declared passage and onward cargo commitment

October 29, 2026. Local extension of the restored application on `feat/portwatch-restored-intelligence`, following checkpoint `1973d28`. Hosting remains deferred. The prepared October 26 hosting package and its dated evidence manifests describe that earlier package; this feature does not change their deployment status.

The existing Company **Current weather decision** can attach one explicitly fictional shipment and onward connection to a declared passage comparison. The compact original inspector answers whether each retained conditional clear-approach time leaves enough time for that shipment's declared loading cutoff. Its existing selected option, Timeline, Why archive, Company approval, scoped Port review and Vessel navigation advisory carry the same frozen calculation. A cargo alternative is a proposal for review, never a booking or reservation.

## Declaration and clock

The optional `currentArrival.cargoCommitment` is schema version 1. It names the visitor-owned inbound `voyageId`, destination `portCode`, an explicit `fictionalShipment`, aware `declaredAt`, assumption `basis` and deliberate `mustMeet` flag. The supported path creates a declared fictional shipment; it does not match an official berth record to a fictional hull.

`shipment` retains its ID, TEU, cargo class, destination, weight and optional latest-departure commitment. `bookedConnection` and optional `laterConnections` retain each fictional onward vessel, departure, loading cutoff, rotation, free TEU, deadweight, reefer plugs, dangerous-goods/out-of-gauge eligibility and source or explicit assumption basis. Capacity is unreserved. Missing capacity or compatibility information cannot establish a confirmed connection.

`transfer` retains an explicitly assumed `approachToStartHours` interval and basis, direct/yard mode, gangs and deliberate acceptance of the schematic handling model. Conditional clear approach does not establish berth access, all-fast, customs release or cargo availability. The offset represents the declared interval **before inbound handling starts**, not completed discharge. An unknown interval produces unknown readiness rather than a zero-time release.

All conversion uses aware timestamps normalized to UTC and one frozen `conversionReferenceAt`. A simulation hour is `(timestamp UTC − reference UTC) / 3600`; an offset date near midnight is converted by its instant, not its printed local date. The reference, rule version, declaration hash and each option's assessment remain in the comparison evidence.

## Stage arithmetic

For each option independently:

1. `handling start = retained conditional clear approach + declared approach-to-start interval`.
2. Pass that start as the shipment's available/start simulation hour to the existing cargo connection model.
3. The model adds discharge, transfer overhead, optional yard moves and loading **once**.
4. `signed slack = explicit loading cutoff − completion`; a negative value misses the cutoff.
5. Check rotation, slots, deadweight, reefer plugs, dangerous goods, out-of-gauge compatibility and any declared latest departure through the existing cargo rules.

The existing illustrative one-gang rates are discharge 24 TEU/hour, loading 22 TEU/hour and 1.5 hours transfer overhead; class handling factors apply. For 24 dry TEU transferred directly, handling is `24/24 + 1.5 + 24/22 = 3.590909… hours`. With an explicitly assumed two-hour approach-to-start interval, completion is 5.590909… hours after conditional clear approach. Yard mode adds the model's two yard moves using the declared zone basis. These are schematic assumptions, not terminal guarantees.

This bounded path requires an explicit loading cutoff. It does not silently adopt `VesselCapacity.cutoff()`'s legacy departure-minus-two-hours fallback or offer a modeled cutoff as an official booking rule. Unknown cutoff, timing or capacity stays unknown. A timing fit with incomplete compatibility is distinguished from compatibility under the complete declared assumptions.

Equal clear-approach times with identical downstream declarations produce equal cargo readiness and slack, even where anchorage waiting or modeled fuel differs. Reduced waiting cannot manufacture earlier release, departure or final delivery. Only connection/next-sailing feasibility is evaluated; final delivery ETA is unavailable.

## Constraint, alternatives and financial boundary

Optional cargo context does not change the passage equations, existing objectives, default ranking or approval eligibility. Only an explicitly declared `mustMeet` commitment adds a hard constraint for this comparison. A blocked or unknown required connection is not an approvable guaranteed connection. The decisive rule remains visible alongside the original passage constraints; less modeled fuel cannot cancel a required cutoff or capacity failure.

When the booked connection is blocked, the existing cargo decision engine can propose a later declared, compatible sailing. Its own departure, cutoff, timing and compatibility are evaluated against the frozen source passage assessment. No invented sailing, automatic reservation, capacity decrement or cargo execution follows. Accepting the navigation advisory does not accept another operator's cargo booking.

The bounded editor uses one handling gang. Explicit declarations with more gangs can be assessed by the existing connection model, but later-sailing proposals remain unavailable there because the established cargo decision generator uses one gang. The missing proposal basis is reported instead of mixing two handling assumptions.

This bounded declaration supplies no storage or missed-connection price. Cargo costs remain unavailable, and existing passage money remains partial. A generic scenario penalty is not a contractual charge; FX baseline errors are not a settlement rate or cargo-delay coefficient. No complete savings or actual service improvement is claimed.

## Durable review

The existing visitor world and ledger retain the shipment declaration/version, conversion reference, rule/model version, all per-option results and selected assessment. A change to a consumed declaration creates an explicit linked successor with fresh review. Earlier comparisons, approvals, advisories and evidence stay inspectable. Relevant consumed version changes block a new continuation action; unrelated shipments, source counts and unused economic context do not invalidate the approved record.

Company proposes its owned plan. Port reviews the advisory within its scoped role. Vessel acknowledges/accepts the existing navigation advisory and gains no authority to book an onward connection. The existing labelled `SIMULATED_DEMO_OUTCOME` remains simulation evidence, ineligible for real operational scoring. Repeated handoffs/outcomes reuse durable records. Old arrival-only and passage v1/v2/v3 records remain readable without invented cargo fields.

## Validation record

Local preview: `http://127.0.0.1:4211/company/global-eye`, with its own verified-auth API on port 8812 and isolated state under ignored `work/passage-cargo-20261029/`. Shared collectors and their state were not stopped or repointed. This validation server runs no duplicate reconciliation scheduler.

- **249 backend tests passed** across cargo arithmetic/workflow, declared passage/finance, recovery, current inputs, the existing cargo/twin and decision engines, weather/shared feedback, demo isolation and verified identity. This includes the 32 new arithmetic and 12 new workflow cases; overlapping development runs are not additional tests.
- **22 finance and authorization tests passed, three skipped**, separately in the older tests' explicit asserted-header fixture mode. The running preview retains verified authentication. The inherited Starlette/httpx deprecation warning remains.
- **28 browser runs passed**, without retries: 20 existing passage contracts and eight cargo contracts at 1366×768 and 390×844. They cover explicit scenario selection, missing inputs, equal-gate timing, optional-context eligibility, required cutoff failure, later proposals, keyboard evidence disclosure and compact layout. These presentation fixtures are separate from the real-source example below.
- TypeScript, changed-file ESLint (zero warnings/errors), and an isolated Vite/Nitro production build passed. Existing map/globe chunk and plugin timing notices remain. The served TS/TSX sources match the final workspace after line-ending normalization.
- Actual local Company, Port, Vessel and Admin entries were opened through the original role switcher, including their map/traffic, layers and timeline controls and Admin Global Eye. The original map rendered around the new shared cargo inspector.
- All eight protected role/twin files match `e906f6a`; weather/learning collectors, both rejected models, geometry, passage/finance equations and hosting configuration are unchanged. The prepared October 26 backend/frontend archives and public-seed manifest match their recorded SHA-256 hashes. The 19 unrelated CSV changes remain excluded.

The real-source local example consumed Open-Meteo response `52fe86ccf61ba6447c9feb1eada91946b0623464cc3b722717721c81d292be08`, received October 29 at 00:19:50 IST (October 28 18:49:50Z). Forecast issue time is unavailable; receipt is first local availability. The forecast is applied to a fictional voyage and explicitly declared handling/capacity assumptions, not an observed shipment.

In the supported equal-gate comparison, both plans clear approach November 5 at 14:00Z. For 24 dry TEU, a declared two-hour pre-handling interval plus 3.590909 hours of handling gives conditional completion at 19:35:27Z, against a 21:00Z cutoff: **+1.409091 hours slack for both options**. Modeled fuel can differ without inventing earlier cargo release. Company decision `dec-arrival-363ffaa78f59e4838a8f`, evidence `ac30dca17097ae50bef3a74c1713d1a4bde3be8ac4ea5335e08204c962bb4feb`, was approved, then recovered after the actual API process changed from 91736 to 41376. Frozen options, evidence hash, selected option and approval history were identical. Scoped Port review/issue, Vessel acknowledgement/acceptance and labelled simulated outcome completed through advisory `ADV-INNSA-78FF59845B`. Repeated handoffs/outcomes reused records; another visitor received 404 for those records. No cargo booking or execution was created.

The required-cutoff counterexample `dec-arrival-97c86c5d8669fb023f62` retained a valid baseline. Its slower option completed conditional handling November 6 at 08:35:27Z, missing the November 5 21:00Z cutoff by **11.590909 hours**, and was rejected despite lower modeled fuel. The existing cargo engine proposed the explicitly declared later sailing at November 6 23:00Z (+24 hours versus the booking), with 12.409091 hours of conditional slack. It remained unreserved and required separate Company review.

Logs, the actual-restart report, source originals, fixture results and screenshots remain under the ignored local work directory; opaque visitor credentials are kept only in an excluded private checkpoint. The UI was also exercised against the actual local API by deliberately selecting both named scenarios and inspecting the resulting cutoff comparison. Real terminal access, execution, contractual charges and final delivery remain unavailable. No hosting provisioning, deployment, public alias change or production-outage repair was attempted.

Focused deterministic arithmetic and workflow tests are in `tests/test_passage_cargo.py` and `tests/test_passage_cargo_workflow.py`. They use explicitly fictional weather, schedules and capacity. The 12 workflow cases pass locally, including unknown required inputs, failed-calculation persistence, consumed-version checks, linked successors, visitor isolation and the complete labelled simulation journey. Resource-cache eviction in those tests is not an actual backend process restart. Final combined validation results, actual process restart evidence, local preview and browser usability checks are recorded in the milestone handoff; fixture results do not establish current provider availability or real cargo execution.
