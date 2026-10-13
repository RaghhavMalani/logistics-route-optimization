# Paradip and Chennai public-data pilot

Port → Operations now exposes an independent public-data pilot for **Paradip INPRT** and **Chennai INMAA**. JNPA INNSA keeps its existing operator-confirmed arrival/all-fast workflow. No JNPA response, private camera or paid AIS account is required to collect the public reports.

## Sources and retained evidence

The adapter reads only the [Paradip traffic index](https://paradipport.gov.in/traffic/) and approved daily PDF links from that index. Refresh collects its latest three reports; the operator CLI can collect up to seven. It also reads the fixed Chennai [position](https://www.chennaiport.gov.in/api/static/default/vessel_report/pos.pdf) and [expected-arrival](https://www.chennaiport.gov.in/api/static/default/vessel_report/eta.pdf) PDFs. Redirects outside approved HTTPS paths are refused; the API accepts no caller-supplied source URL.

State lives under `PORTWATCH_STATE_DIR/public_port_pilot`, defaulting to `outputs/public_port_pilot`. Keep this directory on a persistent volume. Each original is written to `evidence/<SHA-256>.pdf` before parsing. SQLite retains its hash, source URL, report date, actual receipt/first-seen time, named collector and original parser version. Hashes are checked again before evidence downloads. Chennai's changing URLs cannot overwrite these originals.

Repeated identical documents preserve first-seen time and frozen cases. A parser revision creates a separate dated parse view; the original parse stays retained. Replay sees only parse views then available. Unchanged individual facts preserve their earlier availability; corrected facts become available at the later parse time. Parser revisions do not retime or recreate frozen ETA cases.

The adapters validate the known headers and page geometry. They retain raw timestamp strings, dimensions, names, page numbers, berth references and field flags. Dates without clocks remain unavailable; no midnight is invented. The inspected Chennai ETA report has an overprinted date heading on page two, so the four affected ETAs stay unavailable. Planned Paradip movements never become reported outcome events.

## Prospective calls and matching

Collection freezes a usable expected arrival strictly after receipt and within 21 days, from a report no more than three days old. Historical expected arrivals and already-known nearby arrival records cannot be enrolled retrospectively. Subsequent ETA revisions retain the first frozen value. These cases are public identity candidates, not MMSI-verified operator calls.

Matching requires the exact physical port, normalized vessel name, LOA within 0.5 m and beam within 0.5 m when both reports supply it. Draft may change with cargo and is retained but is not a fixed identity test. Reported arrival must follow freezing and fall within the declared ±72-hour ETA window. Repeated observations collapse only when event times **and berth reference** agree; one arrival cannot be assigned to multiple candidate cases. Multiple arrivals, conflicting berth timestamps or conflicting berth references withhold the affected target. Same-clock reports naming different berths retain both source records, raw clocks, availability times, page numbers and authenticated evidence links under `berthEvidence`. The UI shows the disputed references; waiting time stays unavailable while an unambiguous arrival can still support ETA error. Replay before a later contradiction sees only then-available evidence. Missing/ambiguous/unresolved calls and raw source flags remain in export.

This bounded matching window can exclude very late arrivals and rapid repeat calls. It defines a restricted public-report comparison, not an unbiased estimate of every port call. The source does not establish authoritative call identifiers, MMSI, timestamp event definitions or actual publication time. The collector's receipt time is the conservative availability bound.

**Timezone assumption:** all publisher clocks are interpreted as Asia/Kolkata, UTC+05:30. This is explicitly an assumption, not a source-owner confirmation. Short day/month values use the report year with bounded year rollover and carry `YEAR_FROM_REPORT`. Raw strings remain available for review. Display/export instants are UTC.

## Targets and evaluation

- **Published ETA error:** later reported arrival minus the ETA frozen at collection, in hours. Published ETA is the baseline; it is not a scheduler's waiting-hours estimate.
- **Reported waiting:** reported berth time minus reported arrival, in hours. A public berth time is not confirmed all-fast. Readiness, pilot boarding and planned movements cannot supply it.

Evaluation uses a **defined, closed enrollment cohort**, independent of continuing collection. A verified LIVE authority starts a fixed 30-day cohort in Operations (API allows 1–90 days). Its cutoff and protocol cannot be edited, backdated or reopened. At creation, every previously unassigned frozen case is enrolled, without selecting on outcomes; subsequent frozen cases join only before the exclusive cutoff. Each case belongs to one cohort. Membership assignment has its own availability timestamp, so replay cannot see a later cohort or enrollment. Calls after the cutoff remain available for collection and a disjoint successor cohort; they cannot block the earlier cohort's evaluation. The scheduled collector opens a 30-day successor after the prior cutoff.

The baseline evaluator requires 60 usable prospective cases **per port, cohort and target**, with at least 24 fitting, 10 calibration and 10 holdout calls after availability purging. Within the selected closed cohort, target-incomplete calls still inside their matching window block sealing; expired incomplete/ambiguous cases are explicitly excluded and retained. Issue-time periods are chronological 60/20/20 of **all enrolled cases**, with equal issue instants kept together. Successful labels do not move partition boundaries. Earlier labels received after the next period starts are purged.

It compares frozen published ETA with a fitting-period median ETA correction, and evaluates a fitting-period historical median for reported waiting. Each estimator's own calibration residuals supply an 80% interval. The untouched later period reports MAE, signed bias (observed minus predicted) and coverage. Both targets must pass before holdout results are exposed. The sealed report retains its cohort definition, exact case dataset, partition IDs, row predictions, code hash and dataset hash; repeated evaluation of that cohort returns the original report. A successor uses disjoint calls and cannot reuse earlier holdout labels. Protocol `public-port-cohort-v2` is separate from PDF parser version `public-port-report-v1.1`. No GBM, neural fusion, RL, dispatch policy or savings claim is introduced by this pilot.

## Use and permissions

Choose Paradip or Chennai in Port → Operations. The pilot shows source age/report date, the last successful collection, backend scheduler state, next attempt, retained collection failures, frozen cases, reported outcomes, exclusions and authenticated downloads of the archived originals. **Refresh official reports** performs real collection; **Export public dataset** downloads the complete currently available evidence. The pilot remains accessible independently of the aggregate operational model's response.

Reads and writes require a verified national-command account or the exact port's server-derived authority membership. Client identity headers do not grant access. Refresh, cohort creation and evaluation require LIVE; replay filters documents, parse revisions, cases, cohorts, enrollment and outcomes by availability. Archived evidence collected after the replay clock is refused. The existing JNPA API and collection protocol remain separate.

For an operator with host access:

```powershell
python -m scripts.import_public_port_reports INPRT --actor "Your name" --reports 3
python -m scripts.import_public_port_reports INMAA --actor "Your name"
```

The CLI is an operator command with filesystem access; it does not authenticate through the HTTP session store. It records actual receipt times and cannot accept a backdated collection argument or arbitrary URL.

## Regular collection and the first matched call

The application backend now owns regular collection. Its existing refresh scheduler registers independent `public_ports_INPRT` and `public_ports_INMAA` jobs at startup. Each job becomes due three hours after its last successful collection receipt, including when the documents are unchanged. A failed port retries independently and cannot prevent the other port's job from collecting. Failure receipts remain visible in Operations until a later successful collection. Original first-seen times continue to measure evidence availability rather than polling cadence.

Keep the backend running with `PORTWATCH_FRESHNESS_SCHEDULER=1` and `PORTWATCH_PUBLIC_PORT_AUTOREFRESH=1` (both default to enabled). Set `PORTWATCH_STATE_DIR` to the same persistent state directory across restarts; the existing default is `outputs`. Run one scheduler process against that shared SQLite state. The in-process coordinator prevents duplicate jobs within its process; it does not provide distributed leader election across multiple backend workers. Collection requires LIVE and pauses during replay. Replay also withholds collection status recorded after its clock.

The Codex heartbeat **Collect Paradip and Chennai public calls** was retired by pausing it after real backend coordinator jobs successfully collected both ports on October 7. Collection no longer requires this chat or Codex to run. The deployed backend must remain running with persistent storage; this change does not provision or deploy a hosting service. The operator CLI remains available for an explicit manual collection using the same workflow:

```powershell
python -m scripts.collect_public_port_pilot --actor "Your name"
```

The shared collector creates fixed cohorts when needed, retains per-port run receipts in `outputs/public_port_pilot/collection_runs`, writes dated dataset exports, and verifies previously collected hashes, first-seen times and frozen ETA values remain unchanged. The CLI additionally writes a combined receipt. A durable collection record allows the scheduler to retain its successful cadence across restarts. For every complete unambiguous call, it hash-checks and re-parses the archived ETA, arrival and berth originals, checking vessel/dimensions, event fields and berth reference. The receipt retains source URL, file path, page, raw clocks and first-seen time for each event. A failed archive check is an explicit verification error. These checks establish support in the public documents, not operator-confirmed event definitions.

The backend collects and prepares evidence audits; it never evaluates holdout performance automatically or performs AI visual review. Verified write permissions apply to manual collection and public-port scheduler refresh requests. No private camera or external messaging is involved.

### Persistent Windows host — October 8, 2026

The local backend now runs under the **PortWatch Backend** Windows Task Scheduler task. It uses the Raghh account with S4U logon and limited privileges, starts at Windows startup, retries failed process launches after one minute, and checks for a stopped process every five minutes. The running task has no execution time limit and ignores overlapping starts. A separate OS-held file lock prevents two managed backend entry points from owning the same state. The backend itself keeps the existing three-hour PDF cadence; the five-minute host recovery trigger does not request collection.

The process binds to `127.0.0.1:8000` with one worker, verified identity and `D:\LogisticOptimization-_Capstone_168\outputs` as its durable state. The launcher forces VesselFinder off. Its verified dependency overrides are retained under `.portwatch/backend-runtime`; it also uses the existing `.venv/Lib/site-packages` and bundled Python executable. No QA dataset or account is loaded. Keep these runtime paths and the state volume available. This local host must be powered on and awake; collection does not continue while the machine is shut down or asleep.

Automatic startup collection at **09:39 IST on October 8** succeeded for both official sources. The Windows task's backend results recorded `reason=scheduled`, rather than an explicit coordinator request. The reports were unchanged: all 53 frozen ETAs, originals, hashes, first-seen times and fixed cohorts were preserved, with zero complete real calls. A restart changed the backend PID and retained both successful collection receipt times; it did not poll the fresh reports again. The API reported LIVE, healthy durable storage and a running scheduler.

The first subsequent **elapsed three-hour cycle remains pending**, due approximately **12:40 IST on October 8**. Startup collection alone does not verify that interval. A separate Codex heartbeat, **Verify persistent public-port backend**, only reads host status, receipts and archived evidence; it cannot collect or restart the backend. It will report the first qualifying scheduled cycle and later the first visually audited complete real call, while staying quiet on routine pending/healthy results. The original Codex collector heartbeat remains paused. Reboot and logoff recovery are configured but have not been exercised by rebooting/logging off this computer.

Host evidence: `work/public-backend-windows-task-verification.json`, `work/public-backend-host-validation.json` and `work/public-backend-host-tests.log` (**three focused tests passed**). The proof distinguishes automatic startup, receipt preservation after restart and the pending unattended interval. Original startup receipts are `outputs/public_port_pilot/collection_runs/2026-10-08T04-09-41.717730Z-INMAA.json` and `outputs/public_port_pilot/collection_runs/2026-10-08T04-09-46.205395Z-INPRT.json`.

Host status/control commands from the repository:

```powershell
./scripts/manage_backend_host.ps1 -Action Status
# Stop/restart maintenance requires an Administrator PowerShell session.
./scripts/manage_backend_host.ps1 -Action Restart
./scripts/manage_backend_host.ps1 -Action Stop
./scripts/manage_backend_host.ps1 -Action Start
```

An intentional stop disables recovery until Start is used. The installer is `scripts/install_backend_host.ps1`; `-PrepareOnly` exports the task definition for inspection, while registration requires Windows elevation on this computer. Runtime diagnostics are `outputs/backend_service/host-status.json` and rotating `backend.log` files. The local control file targets a unique run ID, and graceful shutdown releases the process lock. `scripts/verify_backend_host.py` reads the archived state and host status and writes a diagnostic proof without requesting collection or evaluation. The Operations collection status remains the user-facing source for freshness and failures.

### First-case audit and visual review

Every complete match that passes the archive-field checks now produces a versioned JSON and Markdown candidate audit under `outputs/public_port_pilot/case_audits/<port>/<caseId>/`. It includes reported and normalized vessel identity, dimensions and identity limits, frozen ETA and freeze time, reported arrival and berth, document receipt and field-availability times, signed arrival error, waiting hours, timezone assumption, cohort cutoff, hashes, page numbers and archived PDF links. No MMSI or confirmed all-fast is inferred.

The audit begins with **visual review PENDING**. A reviewer must render and visually inspect all cited ETA, arrival and berth pages, comparing printed vessel names/dimensions, report date headings, raw clocks and berth reference against the extracted fields. Record reviewer, actual review time, per-event pass/fail, original hash, page and rendered image link in `visualReview.pageChecks`. Only after all three event checks agree may the review be marked PASSED and the case described as visually verified. Rendering failures or uncertain fields retain a pending/failed state. Candidate audit files are retained on the backend state volume; Operations provides the authenticated original PDF downloads. Repeated collection preserves the original audit preparation time and existing visual-review record; changed evidence produces a different audit version.

Each retained collection receipt now includes `collectionQuality` with counts and case IDs for **unmatched** (pending or expired unresolved), **ambiguous**, **incomplete** (matched arrival without a usable berth) and **complete** calls. These categories distinguish an arrival-only match from the full target chain. The nine excluded Chennai source rows and its known malformed date heading remain visible separately in dataset exports; they are source records rather than nine unresolved calls.

Real backend coordinator jobs at **22:10 IST on October 7 (16:40 UTC)** retrieved unchanged official reports from both ports with no collection errors. All originals, hashes, first-seen times, 53 frozen ETAs and cohort definitions were preserved. Paradip has 19 unmatched calls and Chennai 34; ambiguous, incomplete and complete counts are zero. No real case audit or visual-verification claim has been produced yet. Receipts: `outputs/public_port_pilot/collection_runs/2026-10-07T16-40-50.903364Z-INPRT.json` and `outputs/public_port_pilot/collection_runs/2026-10-07T16-40-48.282087Z-INMAA.json`. Verification used explicit requests handled by the registered backend workers, with their background coordinator running; automatic startup, cadence, retries and restart behavior were checked separately in focused tests. Preservation proof is in `work/public-backend-live-verification.json`.

At **12:26 UTC on October 7**, a fresh check of both ports retrieved identical documents with no fetch errors. The 53 original frozen ETAs were preserved; **zero** real arrivals or complete arrival/berth matches were available. The first real matched call remains pending a later public report. The initial cohort cutoffs are:

| Port | Initially enrolled | Exclusive enrollment cutoff (UTC) |
|---|---:|---|
| Paradip INPRT | 19 | 2026-11-06 12:26:03.703010 |
| Chennai INMAA | 34 | 2026-11-06 12:26:07.033897 |

These cohorts were defined before any real matched outcomes were available. **November 6 closes enrollment only; it does not guarantee evaluation readiness.** Outcomes for enrolled calls may arrive later. Evaluation still requires 60 usable calls per port/cohort/target and at least 24 fitting, 10 calibration and 10 untouched holdout calls after chronological availability purging; reaching the counts alone does not establish accuracy. Neural fusion and RL remain deferred until public-data baseline results are measurable.

## Public case publication — October 8, 2026

The later scheduled October 8 reports yielded three matched Paradip arrivals and one complete visually reviewed call, **MV. GLAD YOUNG**. Its published ETA baseline error is **−24 minutes**, and reported arrival-to-berth waiting is **2.4 hours**. Paradip now has 23 frozen ETAs and Chennai 39; these are collection counts, not accuracy results. The earlier zero-outcome entries above describe their dated checks.

The public Explore and Research pages now provide a selectable ETA → arrival → berth timeline, source/availability clocks, uncertainty, SHA-verified HTTP originals and a sanitized JSON audit. The two Paradip originals and reviewed case are packaged in an immutable public-only bundle for new cloud hosts. See [PUBLIC_RESEARCH_APP.md](PUBLIC_RESEARCH_APP.md) for the publication contract and identity limits. Existing audit preparation and visual-review records remain unchanged.

Parser revision `public-port-report-v1.2` inspects Chennai's overprinted date glyphs conservatively. The October 7 and 8 page 2 originals each contain two distinct valid dates; four rows per report remain excluded with both candidates, rather than selecting a guessed date. The dated reparses preserve original hashes, first-seen times, frozen ETAs and cohorts. A parser revision's actual availability time is retained separately from original collection.

## Optional structured vessel evidence

The VesselFinder adapter is disabled by default. To opt in, set `PORTWATCH_VESSELFINDER_ENABLED=1` and `VESSELFINDER_API_KEY` on the backend. The provider requires an API key and credits; coverage for these ports has not been verified. See the official [port-call API](https://api.vesselfinder.com/docs/portcalls.html) and [expected-arrival API](https://api.vesselfinder.com/docs/expectedarrivals.html). No live paid API request was made during this implementation.

When configured, independent `vesselfinder_INPRT` and `vesselfinder_INMAA` jobs request the fixed `portcalls` and `expectedarrivals` JSON endpoints every three hours in LIVE. Each collection makes two requests per port, with a 1,440-minute window and a maximum of 50 records per endpoint. This bounded window is enrichment rather than a complete port-call history; an empty response does not establish coverage. Authentication stays on the server, and credentials are excluded from evidence metadata and displayed failures.

Original JSON, hashes, source parameters and first-seen times live separately under `public_port_pilot/vesselfinder`. Operations exposes the available vessel name, MMSI/IMO, events, raw clocks, AIS ETA, field flags and authenticated JSON downloads. Replay filters records and evidence by availability. Provider event clocks are parsed as UTC; AIS ETAs use an explicitly labelled UTC interpretation, with the provider supplying the year. These records do not rewrite the public PDF frozen ETAs or cohort membership. Vendor arrival/departure events and AIS ETAs do not establish confirmed all-fast or reported berth times; those fields remain unavailable.

## First real collection — October 7, 2026

| Port | Original reports | Parsed public rows | Frozen future ETAs | Matched prospective outcomes |
|---|---:|---:|---:|---:|
| Paradip | 3 | 243 | 19 | 0 |
| Chennai | 2 | 68 | 34 | 0 |

Rows include expected arrivals, reported events and planned movements; they are not a count of unique port calls. All **53** frozen cases were collected before their published ETA. They remain pending actual reported arrivals. Historical waiting observations are descriptive evidence, not prospective outcomes. Repeated imports preserved original hashes, first-seen times and frozen ETAs. The initial parser's extra Chennai footer row was removed by an explicitly dated parser revision, preserving all originals and cases.

The first original receipt times were approximately 11:42 UTC. Reports and first-seen metadata are retained locally in the evidence store. The JNPA operator-confirmed qualifying count remains zero. These collection counts establish that collection is working; they do not establish operational accuracy.

## Verification

The backend migration passed **74 focused Python tests**, **eight real-backend browser checks** at desktop/laptop sizes, TypeScript, scoped ESLint and the production build. Regressions cover scheduler startup, due times, unchanged documents, restart cadence, independent retries, replay, durable failure receipts, verified write permissions, optional vendor identity parsing and credential-safe errors, plus the existing matching, cohort and audit contracts. Browser checks exercise the Operations failure display and successful refresh recovery, original downloads, matched/ambiguous/conflicting fixtures, replay, membership and the separate JNPA workflow.

Current execution results are recorded in `work/public-backend-tests-final.log`, `work/public-backend-browser.log`, `work/public-backend-build-production.log` and `work/public-backend-validation.json`. Browser checks use separate QA databases with explicit synthetic outcomes and real layout samples; manual refresh also downloads official reports. Synthetic cases never enter production collection state. The Python environment retains an existing Starlette/httpx deprecation warning. QA servers are stopped after validation; the final production identity build uses the normal same-origin `/api` base. The optional VesselFinder parser and scheduling were tested with synthetic responses only; provider coverage remains unverified.

Execution logs: `work/public-pilot-tests-release.log`, `work/public-pilot-browser-release.log` and `work/public-pilot-build-production.log`. Repeat-import and first-seen proof is in `work/public-pilot-repeat-proof.json`. Real dataset exports are `outputs/public_port_pilot/export-INPRT-2026-10-07.json` and `outputs/public_port_pilot/export-INMAA-2026-10-07.json`. QA servers are stopped after validation; the final frontend build uses production identity and the normal `/api` base.
