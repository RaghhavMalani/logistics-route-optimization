# Restored PortWatch public demo release

Release validation: October 11, 2026. Publication status is updated at the end of this record after promotion and public checks.

## Restored application and release artifacts

The Company, Vessel, Port and Admin workspaces retain the recovered application from `e906f6a6bd4388cd3c059b4d9a5de6759139528b`. All eight protected role/twin files match that commit after checkout line-ending normalization. Existing maps, traffic, layer controls, navigation, inspectors, timelines and schematic digital twin remain in place. The service adapters connect these screens to each visitor's isolated world.

- Validated frontend candidate: `dpl_3EzEfhB37mkQQMESLppZLK5ddDcF`, <https://india-portwatch-fc7dssk16-flash2404s-projects.vercel.app>.
- Published public domain: <https://india-portwatch.vercel.app>.
- Isolated preview API: `api-restored-preview` in Railway environment `restored-preview`, with its own `/app/state` volume.
- Backend public-source package: `work/restored-public-release-20261011-r5`. Its manifest is `work/release-readiness/release-plan.json`: 831 files and 3,845 packaged public forecasts. Private operator records, identities, credentials and visitor stores are excluded from uploads.
- Frontend source fingerprints and protected-file comparisons: `work/release-readiness/final-frontend-manifest.json`.
- Previous public frontend for rollback: `dpl_6Yi7aZM7xHWtGamk2Ts4oCxmjhJo`. Previous production backend: `f6c38080-8971-4717-8620-eb81ee219bdc`.

The same frontend artifact uses a same-origin `/api` proxy. The existing public domain routes to the existing production API; candidate URLs route to the isolated preview. Promotion therefore does not rebuild or replace the validated frontend.

## Durable continuation

Visitor decision ledgers now store continuation state separately from the original frozen comparison. Restoring a decision retains its options, recommendation, selected option, approval history and advisory/outcome links. Restoration performs no new ranking and grants no approval.

Further actions check visitor ownership, role membership, the consumed voyage destination and ETA, future arrival timing and forecast receipt age. Unrelated contextual events do not invalidate a weather calculation. Expired evidence returns an explicit refresh instruction; Company can create a linked successor comparison requiring fresh review, while previous evidence, approvals and issued advisories remain available.

Demo writes are serialized per visitor. Advisory handoff, acknowledgement/acceptance and outcome retries retain one result. An interrupted outcome can reconcile a completed advisory with its decision and visitor-world record. Authentication for operational routes remains required.

Demo sessions remain valid for 12 hours, with capacity for 128 concurrent sessions. Decision evidence must be sufficiently fresh before another consequential action; already completed historical outcomes remain readable while the visitor session is valid. Session expiration still requires a new demo. The release does not claim indefinite accountless continuation.

## Weather explanation and boundaries

The weather panel names the consumed hourly gust and visibility, receipt time, requested arrival and assumed operator limits. It lists each option's requested arrival, first clear approach time and assumed anchorage waiting. The weather comparison has its own explanation; the legacy closure-duration claim-horizon warning is no longer applied to it.

The browser-validated example requested October 19, 09:00 UTC under a 15 kn gust limit, 5,000 m visibility limit and two consecutive clear forecast hours. Both options reach October 19, 18:00 UTC. Continuing the request produces **9 h assumed anchorage waiting**, while proposing arrival at the clear window produces **0 h**. This is reduced assumed waiting, with unchanged approach timing. It establishes neither faster delivery nor measured fuel/cost savings, berth availability or calibrated uncertainty.

Weather receipts refresh independently of October 2 port activity. Activity still shows its original age. GDACS hazards, wave overlays and economic/news layers are context; they do not enter this approach-gate delay calculation. Provider issue times remain unavailable when the provider response does not supply them.

Public forecast receipts and originals live on the persistent backend volume. Missing packaged claims are merged without replacing newer durable records. The public research weather count now reads that configured forecast archive, applies public-source filtering, and reports an unavailable store explicitly instead of a false zero.

## Verification

- `work/release-readiness/backend-tests.txt`: 79 focused tests passed, with an inherited Starlette test-client deprecation warning.
- `work/release-readiness/authorization-tests.txt`: 35 tests passed and two fixture-specific tests skipped, with the same warning.
- `work/release-readiness/research-eviction-tests-r2.txt`: seven tests passed. This includes actual eviction under pressure from 128 other resource keys, restoration of the frozen Company approval, continuation to Port review, public-source filtering and missing archive handling.
- Recovery tests cover Company approval, Port approval, advisory issue, Vessel acknowledgement and acceptance, resource recreation, expired evidence refresh, consumed ETA changes, visitor isolation and an interrupted outcome between durable writes.
- TypeScript, targeted map/router lint and the final local production build passed. `npm-runtime-audit-final.json` reports zero vulnerabilities in production dependencies; this is not a claim that every development-only dependency is advisory-free.
- A required MapLibre security update needed the official Vite worker asset configuration. Browser validation caught the missing worker before publication. The fix preserves the existing map component; a malformed transparent weather placeholder was also corrected.
- `preview-ui-validation.json` records all four native role workspaces and direct login entries, layer controls, weather projection, the port inspector, digital twin and integrated God’s Eye globe.
- The native browser visitor completed Company comparison/approval → Port review/approval/issue → Vessel acknowledgement/acceptance → labelled demo outcome. Real preview backend restarts were performed after Port approval and after Vessel acceptance. The frozen comparison remained available.
- `final-proxy-20261011/preview-api-validation.json` independently validates the journey through the final Vercel candidate's API proxy, restart recovery, retry safety, same-visitor role switching and another visitor's rejection.
- Mobile actions were exercised at 390 × 844: direct entries, role switching, Port issue and Vessel acknowledgement/acceptance. Dense original maps remain oriented toward desktop; mobile inspectors scroll and can be closed. No replacement mobile shell was introduced.
- All 13 historical research downloads passed their published SHA-256 checks. The original public port-call case remains accessible with its archived PDFs, review, clocks and uncertainty statements.
- Final preview backend `65a01555-ac78-4a78-ba0f-ccaf8ed0704a` passed the final archive and completed-journey checks. The public research page displayed 4,963 immutable forecasts, all still awaiting publishable observations. Its final API evidence is `final-preview-r5/cloud-final-validation.json`; the completed frozen journey survived that deployment in `final-preview-r5-completed-recovery.json`.

Browser screenshots and machine-readable reports are retained under `work/release-readiness`. Earlier failed candidates and failed test setup logs are retained as diagnostics; they are not passing release evidence. An earlier cloud recovery credential expired after its stated 12-hour lifetime; the fresh restart checks succeeded. The additional eviction test initially asserted an unchanged option actor on the new Port review; its final assertion preserves every calculation field while checking the deliberate Port actor change.

## Remaining research and operating limits

Weather-error learning retains original forecasts but has no matched public observations in this release. Correction remains collecting. Real camera evaluation needs authorized footage and surveyed context; unavailable camera and keyed providers remain identified. Aircraft coverage is volunteer ADS-B coverage, not complete airspace coverage. Contextual intelligence does not automatically establish a shipping delay or port closure.

Both neural fusion and constrained RL remain **REJECTED**. Their historical model/evaluation artifacts are preserved, and neither replaces the stronger baseline. Revised specialist dropout hides the unavailable provider inputs, but a new chronological evaluation remains pending. Simulated outcomes are not recorded as independent weather observations or measured operational savings.

## Publication status

The validated frontend `dpl_3EzEfhB37mkQQMESLppZLK5ddDcF` was promoted without rebuilding to <https://india-portwatch.vercel.app> on October 11, 2026. Vercel inspection confirms that the public domain resolves to that READY deployment. Production backend `4ce516dc-411c-4423-9cea-be267c637fd3` is SUCCESS on the original service and persistent volume.

`production-20261011/cloud-final-direct-validation.json` and `production-20261011/cloud-final-validation.json` verify the original API and the promoted public proxy respectively. The pre-release visitor world and original public port-call evidence survived unchanged. All 13 historical download hashes remain valid, operational routes still require authentication, and production exposes 3,845 frozen public forecasts with zero matched public observations. The preview archive has additional preview-only receipts; its higher count is not presented as the production count.

`production-journey-20261011/preview-api-validation.json` verifies the production Company → Port → Vessel → simulated-outcome chain, retry safety, visitor isolation and same-visitor role switching. The public browser independently completed Company decision `dec-arrival-80d7438f15aac6cf2ce8`, Port review `dec-arrival-80d7438f15aac6cf2ce8-port` and advisory `ADV-INNSA-C7C84893BD`. Company and Port approvals and Vessel acceptance survived browser reloads. Vessel acknowledgement and acceptance succeeded at 390 × 844. `public-completed-weather-journey-dom.txt` retains the visible completion label; public screenshots retain the original map, recovered approval and mobile acceptance.

`public-ui-validation.json` records all four original public workspaces, separate weather/activity freshness labels, the Admin port inspector, Port twin projection, rendered God’s Eye globe, public research count and both rejected model candidates. No browser console errors were recorded in the public verification tab. `release-result.json` consolidates the successful publication and its evidence paths. The full preview restart and cache-eviction evidence above complements the public browser reload checks; the production deployment itself also preserved the pre-release visitor and source records.

Automatic approval review previously rejected registering a temporary Railway SSH key and deploying production before anonymous preview checks. No SSH access was added. Recovery was verified through ordinary demo APIs and backend restarts, and an isolated preview was used to satisfy the publication prerequisite.
