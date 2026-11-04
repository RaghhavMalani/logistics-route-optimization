# Declared passage, speed and component costs

October 23, 2026. Local implementation on `feat/portwatch-restored-intelligence`, based on `00b2fda7aa96a72d3ac2fd799bfce5625de7a05d`. Production publication is outside this milestone.

The original Company Global Eye → **Current weather decision** accepts an optional remaining-passage declaration. The existing decision panel, map selection, frontier, timeline, Money, Critic and approval/advisory ledger carry its results. Without a supported declaration the earlier arrival-window comparison remains available, with an explicit reason why physical speed/departure planning was not computed. Protected role/twin sources are unchanged.

## Calculation

The declaration freezes its reference/time, scalar distance and basis, optional simulated polyline, baseline speed/ETA, operating envelope, alternative speed, requested earliest approach and optional latest clear-approach deadline. At-sea references must be within the last hour; undeparted references must be future declared departures within 72 hours. Distance/speed/reference must reproduce the declared voyage ETA within one minute. Supplied geometry is checked with the existing routing length function. Scalar distance without geometry remains an operator assumption.

The adapter uses the existing action catalogue, routing arithmetic and shared propulsion index. It does not introduce another optimiser:

- KEEP_PLAN is evaluated like the alternatives.
- SLOW_STEAM / SPEED_UP changes only the future remaining segment, within the declared envelope and existing 6–24 kn calculation envelope.
- DELAY_DEPARTURE needs an undeparted vessel, a positive declared delay and an explicitly permitted, named holding location. It is unavailable at sea.
- A later arrival request alone does not establish a physical passage plan.

For an at-sea reference earlier than calculation time, common elapsed sailing stays at baseline speed. The original distance is preserved; projection to calculation time is frozen separately. Each alternative changes only the remaining segment, and fuel retains both speeds. This is a simulated projection, not later AIS evidence.

Sailing hours = distance nm / speed kn. Each option evaluates its own hourly gust/visibility rows from the later of physical arrival and the operator-requested approach time. The next whole forecast hour starts a two-consecutive-clear-hour gate. Missing initial/interior hours, variables or horizon coverage cannot be skipped. This resolution assumption is disclosed, not a measured meteorological delay. Future/expired receipts cannot drive passage planning. Daily corrections, ERA5, hazards and IMF activity do not enter this gate.

Timelines separate reference, common elapsed sailing, future sailing, permitted departure holding, physical approach arrival and conditional clear approach. Waiting is split between the requested-window assumption and subsequent hourly gate. Signed schedule shifts compare clear approach with the baseline. A declared deadline is a hard constraint, including when a rejected option uses less fuel. Onward delivery, berth availability, official clearance and whole-route safety are not established.

## Fuel and money

Consumption is optional. Every active mode needs applicable declared inputs. The simplified relation is explicit:

`sailing tonnes = [reference propulsion t/day × (speed/reference speed)^3 + auxiliary t/day] × sailing hours / 24`

Each common/future sailing segment uses its own speed. Anchorage and departure hold use separate declared rates. An unsupported active mode leaves total fuel unknown. The generic vessel propulsion index remains an index, never a mass conversion or complete fuel substitute.

The existing finance engine prices typed tonnes/hours through scoped, dated USER_ASSUMPTION rates covering the actual intervals. A price cannot establish consumption. One explicitly applicable whole-elapsed-time charge may be entered; no additional charter/delay/hold charge is layered over it. Cross-currency aggregation requires retained applicable FX evidence; this bounded form supplies none.

The named simulated consumption/price scenario must be deliberately selected and remains editable: reference propulsion 24 t/day at 12 kn, auxiliary 2 t/day, anchorage and departure hold 2 t/day, 8–16 kn applicability and USD 600/t assumed fuel price. These are illustrative assumptions, not measurements or a market quote. No operational rate is supplied by default.

Common port, cargo/onward and other contractual costs remain unknown, so monetary results are **partial**. Signed component deltas and missing inputs are visible; no total savings, percentage saving or cheapest-plan objective is created. Fuel is ranked only when all active modes are supported. Existing ranking weights and baseline tie-breaking remain unchanged. Both conditional alternatives and KEEP CURRENT PLAN are possible; no feasible basis means no recommendation.

## Frozen workflow

`current-weather-passage-v3` evidence contains `passagePlan`, `passageComparison`, a SHA input version and per-option hours, forecasts, fuel, financial components and limitations. Existing v1/v2 records are not migrated. Port copies retain the Company's selected passage plan; review does not command navigation or substitute another speed/departure choice.

The approved action, original arrival-window advisory and explicitly simulated outcome retain exact selected parameters, inputs, financial evidence and selected clear-approach time. Navigation-affecting advisory edits require a newly reviewed comparison. Simulated outcomes remain ineligible for real operational scoring.

Creation accepts optional `predecessorDecisionId` for a visitor-owned Company comparison of the same voyage. Successor links/retry identities are durable and prior approvals remain inspectable. Refresh accepts an explicit updated declaration. Expired passage references cannot be advanced or silently discarded into arrival-only planning. Existing ownership, role, evidence freshness and recovery checks remain in force.

## Validation boundary

Local logs, public diagnostics and screenshots are under ignored `work/passage-comparison-20261023/`; no credentials or browser network traces are retained. Fixture arithmetic is labelled simulation evidence. Live comparisons use genuinely retained current forecasts. Final checks and the working preview are reported in the handoff.

The local compiled preview is `http://127.0.0.1:4203/company/global-eye`, with an isolated backend on 8801. The independent collector backend remains on 8798. Final evidence:

- **133 backend tests passed** across declared passage/finance, workflow, existing current-input/recovery/activity-context, generic decision/finance and robust-policy suites. **Seven older finance API tests passed separately** in their explicit asserted-header fixture mode; the running preview keeps verified authentication. After the final current-world refresh guard, **10 overlapping workflow/recovery tests passed**; these are not additional independent cases.
- **Four browser runs passed** (two input/rendering contracts at desktop 1366px and narrow 390px), including the corrected passage policy explanation. TypeScript and the isolated final build passed. Changed-file ESLint has zero errors and two existing shared-file export warnings. Existing map/globe chunk warnings and the Starlette/httpx warning remain.
- All **eight protected files match `e906f6a`**, and all **252 frontend TS/TSX inputs match the served final build**, allowing CRLF→LF normalization only. No unrelated CSV is reset, staged or committed.
- Actual local UI: Company, Port, Vessel and Admin original workspaces/maps/layers/timeline inspected. Company approval → actual backend process restart → saved-comparison resume → scoped Port review/issue → Vessel acknowledgement/acceptance → labelled simulated outcome succeeded. Reload retained the frozen evidence hash. A separate fresh visitor saw zero proposals/advisories and received 404 for the other visitor's decision/advisory. Actual narrow-table inspection used a 297px scroller for 979px content and keyboard horizontal scrolling.

The supported live-source case used the retained INNSA surface snapshot `e11a94c36effe00573d3592ee5d911fced49eba240d5e43a2713ffdd784d5b29`, received October 23 at 14:39:44Z. Requested approach was October 31 at 14:00Z, with assumed gust ≤15 kn/visibility ≥5000 m and two clear hours. A deliberately selected 2,159.856 nm scalar simulated passage compared 12 kn with 11.0704 kn. Both reached conditional clear approach October 31 at 18:00Z; modeled fuel was 196.25 t versus 169.44 t under the disclosed illustrative relation. Baseline anchorage waiting included the operator-requested window plus the subsequent four-hour weather gate. These are modeled quantities, not measured savings; all money stayed partial.

Company decision `dec-arrival-91c0d070fd7a53d86fb0`, evidence `f92311072256cf053bf99f51a88855482ab91cabc036904e1e57eb249f054a0d` and advisory `ADV-INNSA-44DFF8F8D3` retain that completed fictional journey. A linked live-source counterexample (`dec-arrival-48e113b6d1d662920179`, evidence `5122c13fc40e0491da8bc495985f9e3cba7a9c9d4b1bc8a46f294d11acf5fc64`) uses the visitor's subsequent simulated ETA and a declared October 31 19:00Z deadline. Its slower option reaches conditional clear approach November 1 at 02:00Z, misses the deadline and is rejected; the baseline remains recommended. Earlier approvals/evidence remain inspectable.

Browser inspection exposed and fixed a remaining legacy Robust-tab sentence that incorrectly claimed equal timing and unavailable fuel for every passage case. The final build renders the frozen passage recommendation instead. A final refresh regression also verifies validation against the current owned voyage ETA, so a changed world cannot silently discard the old passage or reject a consistent explicit successor against the predecessor's old ETA.

Weather/public-port collection continues independently. Unrelated CSV refreshes, source archives, weather cohorts/adoption gates and both rejected neural/RL candidates are preserved.
