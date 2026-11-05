# Research failure investigation

The failures are test-budget overruns from concurrent software-rendered charts. The feedback dates and retained bytes are deterministic. The affected cases pass when each Research browser owns its renderer capacity. This was reproduced on the same Windows machine, `supercomputer`, on 5 November 2026 IST with Node 24.14.1 and Playwright 1.63.0.

The full trees of `2e43af315d75faa5d138830b274dc6406ef4df1c` and `d623b901890ddf5c9c75c0ecaadcd58bad1ca14f` differ in seven files. The application source tree is identical, with frontend `src` tree ID `18ea116ddb64ea305e3c235369eb421110c890ee`. Both original Research specs have blob ID `2311e1fee89b1645c4229088e2d262227bac40b7`.

| File that differs | Change |
| --- | --- |
| `india-portwatch-terminal/qa/panel-smoke.mjs` | Production service identity assertions |
| `india-portwatch-terminal/vercel.json` | Production host rewrite and isolated preview fallback |
| `work/integration/CI_BASELINE.md` | Browser baseline evidence |
| `work/integration/QUARANTINED_TESTS.md` | Existing 15-case inventory |
| `work/integration/RELEASE_PLAN.md` | Release procedure |
| `work/integration/ROLLBACK.md` | Rollback IDs and backup metadata |
| `work/integration/STATE_AUDIT.md` | Persisted-state audit |

The controlled runs built each historical commit independently with the node-server production preset. Both used Chromium with `--use-angle=swiftshader`, 1920×1080, browser timezone UTC, two workers, retries disabled and the original 60-second test timeout. The original spec and application code were untouched. The first run lasted from 16:12 through 16:27 IST and the second from 16:27 through 16:50 IST on the same date.

| Commit or setup | Earlier as-of views, ten attempts | Corrupt-original download, ten attempts |
| --- | --- | --- |
| `2e43af3`, two renderers | 4 passed, 6 timed out | 4 passed, 6 timed out |
| `d623b90`, two renderers | 0 passed, 10 timed out | 2 passed, 8 timed out |
| Fixed fixture and one renderer, same machine/browser/viewport | 10 passed | 10 passed |

The fixed as-of case had a median duration of 11.03 seconds and maximum of 13.91 seconds. The fixed corrupt-original case had a median of 26.86 seconds and maximum of 43.72 seconds. The twenty fixed runs completed in 6.9 minutes without retries. Failed historical results often include an additional context-teardown timeout after the 60-second test deadline.

The CI run at `d623b90` shows the same runtime failure. Ordinary clicks took roughly 5–8 seconds, and the last assertion started with almost no test budget remaining. The traces contain successful 200 responses for the expected historical inspection and the deliberately corrupt 21-byte body. The source fixture returns unresolved/as-reported news before the confirmation date, and the download implementation rejects bytes whose SHA-256 differs from the requested digest. Timeouts interrupted the UI interaction or final error assertion. [Failed main CI](https://github.com/RaghhavMalani/logistics-route-optimization/actions/runs/42004439655)

Pausing traffic and requesting reduced motion alone still timed out under two concurrent software renderers. A single-worker trial passed both cases in 11.4 and 23.8 seconds, followed by all twenty repeated checks passing. The final fix therefore isolates Research rendering capacity in CI as well as settling the fixture's unrelated traffic motion.

| Dependency investigated | Finding |
| --- | --- |
| Current date and wall clock | `AS_OF`, claim release dates, observation dates and confirmation dates are literal UTC fixtures in `qa/tests/shared-feedback.spec.ts`. `inspection()` derives its expected data solely from the requested `asOf`. `Date.now()` creates a fresh one-hour synthetic login session. It does not determine the feedback result. |
| Timezone | Valid inspection inputs have `Z` or an explicit UTC offset. The invalid input deliberately omits that offset and is rejected before parsing. The fixture now explicitly uses browser timezone UTC. |
| Startup-imported data | Browser API requests are intercepted by `qa/harness.ts` and the spec's own `context.route` handlers. The test server is the frontend production build. No Python backend or production startup importer runs in these tests. |
| Date regression check | The repeated failures occur on the same date with identical source and deterministic feedback fixtures. The observed cause is renderer contention. The existing historical-boundary and timezone assertions are retained. |

`qa/run-browser-ci.mjs` partitions the active suite into 475 ordinary cases and six Research cases. The four existing shards run the ordinary partition. `Browser Research (isolated renderer)` runs the complete active Research partition with one worker at both existing viewport projects. Discovery and the original quarantine validation apply to both partitions. The partitions preserve all 481 selected cases and the 15-case quarantine. Original assertions and timeouts are retained. The corrupt-original test additionally asserts that no download event occurs.

The exact dedicated CI entry point passed all six active cases locally at both viewport projects in 57.6 seconds, with retries disabled. Typecheck and all nine gate regressions passed. The two partition lists were checked for an empty intersection and a 481-case union.

`scripts/verify_release_gate.py` requires a successful completed push workflow on the exact current main SHA, including every backend/build job, all four ordinary browser shards and the Research job. Nine regression cases exercise rejection of incomplete, failed, missing or wrong-SHA/branch CI. A live negative check refused deployment of the currently red `d623b90`. The release procedure requires this gate before the fresh production backup and again before Railway upload and Vercel promotion.

Raw comparison logs, JSON results, CI trace action timings, partition listings and the negative gate result are retained in `work/integration/research-failures-20261105/`. The report includes software-renderer stress results separately from hosted CI qualification. PR CI and the new main push CI must both pass before production work begins.
