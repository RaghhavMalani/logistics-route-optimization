# PortWatch Milestone A: connected role demos

**Visual review update, October 9:** the user rejected this release's shared
DemoShell composition. Its backend and advisory chain are retained. The bounded
[UI/globe correction preview](UI_GLOBE_CORRECTION_PREVIEW.md) restores Company
route screens and presents entry/global investigation for review. Vessel, Port
and Admin visual restoration and Milestone B remain pending that checkpoint.
The release description below records the earlier implementation, not visual
acceptance of the recovery.

Implementation started October 9, 2026 against the complete `PORTWATCH_IMPLEMENTATION_PROMPT.md`. This milestone restores the visitor role workflows while preserving the operational application, recovered public globe, research release and prospective collection. It is the first product-review checkpoint, not completion of the full brief.

## Usable workflow

The entry at `/` redirects to `/login`, which exposes four one-action controls: **Open Company Demo**, **Open Vessel Demo**, **Open Port Demo** and **Open Admin Demo**. Operator sign-in is a separate form. `/explore`, `/research` and the GLAD YOUNG permalink remain available anonymously.

1. Enter Company. Select fictional PW Meridian / PWD-001 ahead of Suez. Compare voyage actions; select an alternative to inspect its geometry, ETA shift, constraints and partial financial components. Change restriction duration from 72 to 120 hours and compare again. Keeping the plan changes from a 50-hour to a 98-hour modelled ETA shift under these assumptions. Submit the selected plan to the demo port.
2. Switch to Port without leaving the sandbox. The proposal enters the existing twin's future arrival input. Compare first-come/first-served and constrained lookahead on the same schematic arrivals, geometry, resources, seed and weather assumption. Select a policy, then approve a demo advisory.
3. Switch to Vessel. The bridge is assigned PWD-001; acknowledge its advisory. Compare a negative time-to-chokepoint to inspect the commitment gate. Diversion after passage is unavailable.
4. Switch to Port and record a demonstration waiting outcome after acknowledgment. It is a demonstrator-entered value, never a measured public port call or model score.
5. Switch to Admin. Inspect ranked public congestion proxies, port selection, dated sources, active-versus-benchmarked model status and the advisory chain. The Scenarios view runs the same voyage comparison engine.

Company can inspect its selected fleet vessel on the bridge and return to the fleet. Port can switch between the existing Three.js twin and the recovered Cesium globe. Changing the view retains the visitor's world; only one renderer is mounted at a time. Cargo, weather, forecast, source, model and advisory navigation focuses the relevant populated section. Mobile exposes Scene, Assets & signals, and Planning & decisions panels.

## Boundary and persistence

The explicit `/api/demo/*` API never forwards requests to protected operational endpoints. `DemoStore` persists independent visitor worlds at `PORTWATCH_STATE_DIR/demo/sessions.sqlite3`. Each opaque 12-hour session has its own server-owned role and state; only the token digest is stored. Role switching changes demonstration permissions only. No demo token is registered in the operational `AuthStore` or installed as `current_identity`.

All demo writes address one session row under a SQLite transaction. A server restart preserves the session/world. Reset refreshes the mounted query; logout revokes the server row and clears browser session/query state. Expired/revoked sessions return to entry. The deployed production authentication mode remains enabled. No shared operational identity, ledger, world clock, public cohort, collector setting or model is overridden. Demo history is bounded by 30 comparisons, 20 advisories, 1.5 MB per world and 128 active sessions, with expired-row cleanup on entry. At capacity, the API gives an explicit retry/reset response.

Authorization is checked inside each demo endpoint: Company proposes; Vessel accesses its assignment and acknowledges that vessel's advisory; Port compares resources, issues and records outcomes; Admin can inspect and exercise demo planning. Approval requires the current company proposal to match the proposal captured by the port comparison, and freezes the selected port policy, inputs, seed and metrics. A different-destination option can be inspected but cannot be submitted as a JNPA arrival. An infeasible plan or policy with hard violations cannot be approved.

The frontend additionally confines a demo session to `/demo/*`, sanitized `/public/*`, health and provenance reads. The server is the security boundary; spoofing client role headers or bypassing the frontend does not grant operational access.

## Data and model meaning

The three fleet vessels, positions, cargo descriptions, demo restriction and port occupancy are fictional. The twin is schematic rather than a surveyed JNPA terminal. Voyage alternatives reuse the existing `DecisionEngine` through the public scenario service, with no operational ledger writes. Port policies reuse the existing twin simulator and constraints. Public source reports, forecasts and weather are contextual evidence with their original clocks; they do not silently become closure or weather assumptions consumed by the demo simulation.

The company ETA effect is added to its future `VesselCall`; a missing ETA effect withholds that call. The principal Suez voyage is outside the 72-hour berth simulation horizon. Comparing port policies therefore demonstrates resource planning on the separate illustrative calls, not a measured downstream benefit for that distant voyage. Cargo connection cutoffs, several port charges and realized savings remain unavailable. Monetary assumptions are shown beside partial costs.

Current cached forecast targets are still stale. The UI exposes their actual origin/target rather than relabelling a new cache receipt as a fresh forecast. The published GBM historical proxy benchmark and the active adaptive ensemble are distinguished. This milestone does not train neural fusion, a new RL policy, a weather correction candidate or reserved-period interval calibration.

## Verification evidence

Commands and dated results are retained under `work/demo-A-*`. Browser checks use a real API and real engines; only the explicit failure-recovery test intercepts a request to inject a 503. QA uses a separate task-owned state directory and disables its collector. No QA fixture replaces operating state.

- `tests/test_demo_boundary.py`: cross-role chain, policy/input preservation, restart persistence, visitor isolation, changed-proposal review, foreign-vessel restrictions, incompatible destination rejection, local reset, revocation, expiry, invalid inputs and operational credential rejection.
- `work/demo-A-python.log`: focused demo, public scenario and authorization regressions.
- `work/demo-A-ts.log`, `work/demo-A-lint.log`, `work/demo-A-build.log`: TypeScript, changed-source lint and production build.
- `work/demo-A-check.mjs`: complete entry-to-outcome desktop/mobile journey, direct entries, deep links, source recovery, public globe and real research permalink.
- `work/demo-A-local-validation/report.json` and screenshots: local browser evidence.
- `work/demo-A-staged-r2-validation/report.json`: final staged role evidence; `work/demo-A-public-browser-r2.log`: seven public globe/research regressions, including a deliberately different browser clock.
- `work/demo-A-api-validation.json`: ten public API checks, all 13 research-download hashes and all three case-event PDF hashes, original review/availability clocks and retained public collection counts.
- Railway deployment `f6c38080-8971-4717-8620-eb81ee219bdc` is healthy. Vercel `dpl_6Yi7aZM7xHWtGamk2Ts4oCxmjhJo` was staged and promoted to `https://india-portwatch.vercel.app/`; the primary alias passed the same 21 role checks and seven public regressions. See [the complete release record and screenshots](PUBLIC_ROLE_DEMO_RELEASE.md).

Desktop and mobile screenshots are visually reviewed after the globe/twin has rendered. Operational negative checks verify rejection before any protected write is performed. Existing public research artifact and case-PDF hashes are checked against the release manifest, without inspecting holdout performance or evaluating prospective cohorts.

Focused validation: 14 Python tests pass, TypeScript passes, changed-source lint has zero errors and two inherited AuthProvider hot-reload warnings, and the production build passes. The local full demo journey and first HTTPS stage each passed 21 checks. The preserved explorer's server/browser clock race was reproduced during QA, corrected by establishing the actual view clock after hydration, and covered by the additional public regression. No artificial initial timestamp is sent to inference or feedback.

## Full product status and next milestones

| Category | Status and evidence |
|---|---|
| Implemented and usable in Milestone A | Four role entries, isolated durable visitor state, existing globe and twin, actual voyage/resource comparisons, proposal/review/advisory/acknowledgment/demo outcome, dated public context, reset/expiry/logout, mobile panels. |
| Existing and preserved, awaiting source coverage | Scoped camera/media and AIS foundations remain. No observed AIS stream or authorized camera is supplied for this demo. Private cameras remain protected. Prospective port collection continues independently. |
| Experimental and evaluated before this milestone | Existing historical congestion benchmarks and twin/decision benchmarks remain under research; they are proxy/simulator results. The two demo port policies produce simulated metrics from fixed seed 20261009. No new holdout model result or operational-savings claim is added. |
| Milestone B remaining | Trace and repair the supported forecast fetch/features/inference/export path; demonstrate a current target with original inputs/clocks; expand missed-intervention cases and improve the optimizer against strong baselines. Feed supported evidence and explicit economic choices into consumed comparisons. |
| Milestone C remaining | Broader global layers and incident clustering, observed AIS identity/tracks, inland/hazard/context adapters, authorized camera observations and held-out CV evaluation connected to decisions. Credentials constrain their own layers rather than all product development. |
| Milestone D remaining | Original Day-5 forecast/valid observation/correction/downstream inference workflow; chronological neural specialist/gating experiments and ablations; a reproducible constrained RL simulator experiment with separate seeds/families and baselines; interval calibration on a newly reserved chronological period. Publish candidate/deployed status and reproducible artifacts. |

Milestones B–D retain the implementation brief's full objective. They are development work to perform after the Milestone A product-review checkpoint, not placeholders asserted as completed or dependencies on the first operator response.
