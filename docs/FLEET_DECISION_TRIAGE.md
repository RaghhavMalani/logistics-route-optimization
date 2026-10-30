# Fleet decision triage in the Company review queue

October 30, 2026 (India time). Local product work following `cf9aceec50b3ce2b5513e902ab481748eb2e5d5f` on `feat/portwatch-restored-intelligence`. Hosting remains deferred. The dated October 26 hosting package and its source/evidence manifests retain their original status; this feature does not describe a deployed revision.

The original Company overview's review entry now answers which owned current voyage needs review, the retained reason, the next responsible role and the exact comparison to inspect. It opens a bounded worklist over the existing chart. It does not create a second fleet, optimizer, ledger or approval state machine.

## Current-plan selection

The contract is `fleet-decision-triage-v1`, with selection policy `current-call-plan-selection-v1`. Selection starts with the authenticated visitor's owned fleet and the existing operational episode and voyage-leg identities. Destination or ETA changes are assessed within that call; no GET creates a missing episode. A previous call on the same vessel is historical, and records without a supported call relationship are explicitly identified as legacy coverage gaps.

An approved plan needs a durable Company comparison, its actual `humanChoice` option ID, and a matching proposal/journey relationship with the same vessel and frozen evidence. The explicit active `terminalProposal` wins only when those relationships agree. Otherwise, one approved leaf can be identified through reciprocal predecessor/successor links; conflicting approvals or inconsistent links remain ambiguous. Creation time, insertion order and IDs do not choose an operational plan.

With no approved plan, a uniquely applicable current comparison's retained baseline represents `BASELINE_NOT_APPROVED`. Explicit reciprocal successor links can identify that unique leaf only when all candidates form one complete acyclic chain. Disconnected records and cycles remain ambiguous, including a cycle beside an otherwise unique leaf. Several unrelated candidates, a missing baseline or incomplete approval identity instead produce a needs-assessment/ambiguity explanation. An unapproved successor never replaces an approved plan. It remains separately inspectable and requires fresh review.

The DTO keeps current plan, human choice, engine recommendation and separate candidates distinct. A frontend-highlighted alternative does not enter server triage. In particular, a rejected slower alternative with negative cargo slack cannot create a current-plan failure when the applicable approved/baseline option meets its commitment. A failing baseline remains a review reason even if the engine recommends another unapproved option.

## Classification and ordering

The six display categories, in review order, are:

1. `CURRENT_CONDITIONAL_FAILURE`.
2. `REASSESSMENT`.
3. `COMPANY_ACTION`.
4. `WAITING_OTHER_ROLE`.
5. `INCOMPLETE_ASSESSMENT`.
6. `MONITORED`.

Only the applicable option's retained assessment with explicit `mustMeet=true`, a decisive failure and current consumed evidence establishes a current conditional cargo failure. Missing compatibility or timing is incomplete assessment. Optional cargo context never becomes a required block. An elapsed scheduled cutoff without suitable actual execution evidence is a reassessment reason, not an observed missed shipment.

Classification checks completion first, then a current required failure, reassessment/elapsed applicable windows, incomplete or inconsistent basis, and the pending workflow role. This precedence keeps unknown data from being presented as an ordinary approval task, while separate reasons and workflow fields remain visible. An expired basis suppresses a fresh-failure claim without erasing the frozen negative slack.

Within each category, known applicable times precede unknown times; the next keys are time and stable vessel/call identifiers. Time basis is explicit: pending advisory validity, then an applicable retained comparison action deadline, then a declared required cargo loading cutoff. Vessel ETA is not substituted for an action deadline. Signed hours remain negative when overdue. These are review-order rules, not disruption probabilities, optimizer scores, financial losses or savings.

## Read-only inputs and freshness

`GET /api/demo/terminal/company/decision-triage` is a Company-demo-only projection. Role and fleet membership are checked before loading decision bodies. Caller-supplied query scope identifiers are rejected; repeated fictional vessel IDs never select another visitor's namespace. The ordinary operational endpoint does not grant access to a demo world.

The route holds the existing visitor mutation lock and takes two complete equal read snapshots, using at most three reads if state changes. Read-only SQLite transactions include committed WAL records and inspect the full relevant retained dataset, rather than the generic listing's default page or engine-memory cache. It does not construct an engine or writable domain store, restore workflow records with writes, recompute options, fetch providers, advance traffic, generate forecasts, create calls or create verification tasks. Temporarily inconsistent linked state is reported as updating/unknown; GET does not repair it.

One aware wall-clock `asOf` governs receipt ages, effective periods and signed times. The separate simulated traffic replay is not the operational decision clock. Freshness policy `fleet-triage-consumed-freshness-v1` checks the frozen receipt/requested arrival, current destination/ETA/call, declared route and vessel applicability, authority revision/effective window, consumed cargo version, original response hashes and consumer-bound feedback. Missing originals, corrupt originals, unsupported legacy basis and changed dependencies retain distinct reason codes. No private path, credential or unrelated ledger body is included in queue rows.

The public-feedback reader uses a frozen read-only facade and the existing continuation predicates. Its original-status hook uses only configured canonical public archive roots. Descriptive global counts, unrelated headlines/shipments and unused neutral policy updates do not invalidate a plan. Actually applied policy bindings and relevant claim/vintage changes do. Daily weather learning is not substituted into hourly gust/visibility decisions; model/adoption rules are unchanged.

## Workflow and counts

The projection follows the canonical Company source, linked Port review copy, advisory states and saved outcome. Port copies and retries are representations of the same voyage journey, not additional affected voyages. An issued/acknowledged advisory awaits Vessel response even while the Company source still says approved. Queries return to Port, declines/withdrawals return to Company review, and Vessel acceptance leaves a distinct Port demo-outcome step. No Company shortcut issues or accepts an advisory.

Completed advisories and labelled simulated outcomes close that journey. The projection reports `NOT_REQUIRED_COMPLETED` freshness rather than reopening it as pending solely because the original forecast aged. Completion remains simulation/advisory evidence; it establishes neither navigation execution nor cargo booking. An explicitly started next call has a separate identity and does not inherit the old alert.

There is one row per owned vessel's retained current call, or one missing-call row when that basis is unavailable. Coverage and category counts describe the full owned scope. Categories are disjoint; reason counts explicitly overlap because one voyage can have several reasons. Retained comparison and source-lead counts are separate quantities. The UI filters those full-scope rows and pages six at a time, with the displayed range and total; it does not silently truncate after eight.

Retained notice/voyage source leads remain available in a separate disclosure using cached catalogue records and the existing exposure semantics. Possible geographic exposure remains a confirmation lead. Its old heuristic priority is not mixed with cargo slack, workflow order or money, and missing source coverage cannot become a clear-route conclusion.

## Exact navigation and usability

Saved rows link to `/company/global-eye#fleet-review?vesselId=…&decisionId=…&optionId=…&episodeId=…`. Missing-basis rows use `#current-inputs?vesselId=…&episodeId=…`. Existing `#intelligence-review?noticeId=…&vesselId=…` source-lead links remain distinct. Returning to `/company/overview#fleet-queue` restores visitor-scoped filter, page and selected-row context.

The shared link controller loads the exact owned Company decision and current call, verifies the requested retained option and its current-plan/candidate relationship, then reuses existing vessel, port, inspector and option selection state. That same selection drives the map and timeline. A historical call, unavailable record, unauthorized identity or invalid option produces an explanation and an explicit current-input path; no newest comparison or recommendation is silently substituted. Stale passage positions need explicitly updated inputs through the original editor.

The existing dialog/disclosure patterns provide keyboard focus, Escape/Close and return behavior. Additional evidence, provenance and candidates stay behind disclosures. The query is visitor-scoped, polls at a bounded interval and invalidates after existing workflow mutations. Refreshing and failed requests identify retained previous results and their projection time; an unavailable response does not become an empty reassuring fleet.

## Validation and limitations

Focused tests cover selection/false-alert policy, full-dataset counts and order independence, cyclic comparison history, call boundaries, linked cross-role progression, malformed records, source/cargo/feedback freshness, immutable read-only API behavior and exact navigation. Fixture results are software-contract evidence and remain separate from actual local provider/journey/restart checks.

The local preview is [Company fleet review](http://127.0.0.1:4213/company/overview#fleet-queue), using the isolated API on port 8814. A fresh visitor honestly begins with missing current-call assessments; the worklist GET does not create them. The retained local acceptance visitor has separate examples of a fitting baseline with a rejected slower alternative, a required current-plan failure, and a changed cargo commitment with an approved predecessor and an unapproved successor. Earlier snapshots preserve reassessment and pending-role states; after the full workflow and explicit next-call action, that third vessel correctly shows a missing new assessment.

The actual local journey used a retained Open-Meteo response received at `2026-10-29T19:33:54.547196+00:00` (response SHA-256 `349c99b3a060aab24650ab41fc3f3f007392a2189ac6584d497981c05d623c42`). Vessel passages and cargo commitments were explicitly fictional operator assumptions. No forecast or cargo outcome was manufactured as a real operational target. The accepted successor comparison was `dec-arrival-295e9b6b9d7bd37a3c3f`, with frozen environment hash `e64716830cd537d652247e7ee656390d018b73606346ef565dffbc0db66c99f7`.

After Company approval, the owned API process was stopped and restarted (PID 7044 to 17340). Its exact chosen option, frozen evidence, candidates and projected workflow recovered from durable records without reranking. Port review and issue produced advisory `ADV-INNSA-D0BE1A94E1`; the queue then awaited Vessel response. Vessel acknowledgement and acceptance, followed by the existing labelled simulated outcome, closed the journey. Retry identities were unchanged; a second visitor could not read the comparison. Starting an explicit next call excluded the completed call from current alerts.

Sanitized local projection snapshots, screenshots, build/test logs and `actual-restart-journey.json` are retained under ignored `work/fleet-triage-20261029/`. Credentials, private checkpoint state, runtime evidence, screenshots and build artifacts are excluded from the commit. The reusable tests and this contract are the committed validation material.

Final local validation:

- The consolidated 17-file backend run reported **315 passed, 2 failed**. The two failures are inherited repository-wide static clock audits (`NobodyElseAsksTheWallTests.test_every_wall_read_carries_a_written_justification` and `test_no_domain_module_reads_the_wall_directly`). A comparison with `cf9acee` found the same five direct reads and 77 unjustified wall calls, with no new violations. The relevant behavioural tests passed. The existing Starlette/httpx deprecation warning remains.
- That consolidated run includes the final **51 projection, 27 freshness and 11 API tests**. Earlier focused and consolidated runs overlap and are not additional independent samples. API coverage includes 26 retained comparisons, resource-cache eviction, full-scope counts, role/scope refusal, per-record corruption, visitor isolation, read-only GETs and the linked advisory journey.
- **38 controlled browser cases passed** across 1366×768 and 390px, including existing passage/cargo regressions and ten fleet-worklist cases. They cover exact human choice versus recommendation, direct links/reload/return, historical and invalid links, mutation refresh, retained errors, paging, signed overdue times, keyboard focus restoration and enlarged text without horizontal scrolling.
- **Two real-session browser cases passed**, one per viewport, with no response fixtures. Each opened the exact retained baseline after the actual API restart, checked the timeline's selected option, reloaded and returned to the selected queue row.
- **Two fresh-visitor four-role smoke cases passed**, one per viewport, through the normal role-switch menu with the same visitor identity. Company, Global Eye, Port, Vessel and Admin navigation and chart visibility remained available. Desktop layer interaction passed. An exploratory check exposed an inherited 390px Company-overview limitation: its original fixed inspector can cover the Layers button. That protected screen is unchanged; the new worklist's mobile, keyboard and enlarged-text checks passed.
- TypeScript checking, changed-file ESLint and the isolated production build passed. All eight protected role/twin files match `e906f6a` after line-ending normalization. The October 26 backend/frontend packages and public-seed manifest retain their original hashes.

This bounded worklist helps review existing calculations. It does not provide complete fleet risk coverage, terminal readiness, final-delivery guarantees, reserved capacity, real bookings, actual vessel movement, financial valuation, calibrated reliability or autonomous approvals. The restored role screens, maps/globe, layers, timelines and connected advisory workflow remain the product entry points. No passage/cargo/finance equations, ranking weights, adoption gates or rejected model candidates change for triage, and hosting/production remain outside this milestone.
