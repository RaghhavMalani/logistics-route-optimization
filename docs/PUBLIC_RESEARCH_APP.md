# Public shipping-intelligence research application

Anonymous visitors start at `/explore`. Operators retain their authenticated workspaces. `/research` is public, too. Visitor access creates no account, role, membership or write permission.

## Visitor journey

Explore follows a sourced report → catalogue-exposed ports → dated port forecast → shipping scenario → alternative actions. All 13 ports remain selectable. A forecast at an unlinked port is shown independently. Corroboration and lane exposure are heuristics, not calibrated disruption probabilities or causal delay estimates.

Forecasts include origin, target date, model, nominal 80% interval and stale state. Modelled delay is a pressure-derived proxy, distinct from confirmed anchorage waiting or all-fast. Old snapshots are labelled. Real-source provenance is required; synthetic fallbacks are withheld. Backend replay withholds live snapshots. Sources show retrieval and observation dates separately.

Route scenarios use catalogue detour distance, visitor-entered speed and USD/day cost. Extra passage hours = nautical miles / knots; assumed cost = hours / 24 × USD/day. Speed sensitivity is an assumption range, not a confidence interval. No scenario executes actions or establishes realized savings.

## Historical research

```sh
python -m scripts.build_public_research
```

The October 8 build uses 4,740 existing panel rows and 4,260 reporting rows per model, with targets through October 2. GBM MAE is 5.9177 congestion-index points, persistence 6.6735 and ensemble 6.2612. GBM’s nominal 80% interval covers 75.92%, showing undercoverage. GBM with history plus calendar scores 6.2691, and history only 6.4001. The predeclared feature-removal ablations indicate predictive association, not causal weather value. This data window differs from the October 6 release; these scores are not a paired improvement over that release.

The congestion target derives from cached IMF PortWatch vessel-call pressure, not measured vessel waiting. ERA5 features are reanalysis, not historical provider forecasts. Same-day availability is an offline panel assumption, not a verified publication-vintage archive. Future weather without issue-time archives and full-history regime features remain excluded. The historical reporting period has been examined previously; this release does not create an untouched evaluation. Production members are not changed automatically by rankings.

The page shows chronological partitions, baselines, MAE, RMSE, signed bias, interval coverage/width, horizons, ablations and code/dataset/dependency versions. Predicted-versus-observed plots average ports for display; metrics use individual rows. Visitors can toggle the mean published lower/upper quantiles. This shading is an average of individual forecasts, not a calibrated confidence interval for the cross-port mean. Hash-checked downloads include the frozen dataset and predictions, calibration and reproduction instructions. `current.json` hashes one immutable release manifest. Rebuilding creates a new version and preserves originals. The case-study update does not retrain models or change this historical release.

## Weather and operational evidence

`weather-residual-v2` fits a median residual on earlier independent targets, selects it on later validation, and calibrates a nominal 80% conformal radius on a separate final block. Outcomes unavailable before the following block are purged. Each block needs eight targets after purging; 24 total targets alone do not guarantee readiness. Validation must improve MAE by 2%. Originals stay immutable and accepted correction applies to new forecasts. Reanalysis stays distinct from station measurements.

The page reports availability-filtered MAE/bias by port, variable, provider and horizon for Open-Meteo forecasts with public ERA5 outcomes. Station/operator outcomes and private providers remain protected. These scores are descriptive, not an untouched weather holdout. Missing publishable observations produce a collecting state. An algorithm refinement is not measured improvement. Optional weather/collection store failures show explicit unavailability, never invented zero counts, and do not prevent access to packaged historical research.

Paradip and Chennai collection continues in the backend scheduler. Public visitors can inspect reviewed official-report cases, aggregate counts, freshness and source exclusions. Actor/reviewer names, private operator workflow records and private cameras remain protected. The JNPA verified workflow stays available. Reported berth remains distinct from all-fast; published ETAs remain distinct from scheduler waiting estimates. Cohorts still need qualifying outcomes and chronological minimum counts before operational evaluation. Visitor requests do not collect, train or evaluate cohorts. Neural fusion and RL remain deferred.

## GLAD YOUNG public case

Both `/explore` and `/research` show the first complete, visually reviewed Paradip call. The interactive timeline selects published ETA, reported arrival or reported berth and shows the original clock, normalized clock (IST assumed or UTC), document first-seen time, field availability, cited page, source URL, parser revision and SHA-256. Vessel identity uses the printed name and dimensions; MMSI and publisher timestamp definitions remain unconfirmed. A case-specific `/research#case-<caseId>` link selects the same case as the catalogue grows.

The frozen published ETA was **08-10 0100**, reported arrival **00:36 / 08-10**, and reported berth **03:00 / 08-10**, berth SQ. **Published ETA baseline error is −24 minutes** (reported arrival minus frozen ETA); reported arrival-to-berth waiting is **2.4 hours**. The ETA is the publisher's baseline, not an ML prediction. No ETA confidence interval was supplied, and reported berth is not confirmed all-fast. These observations do not establish operational accuracy or savings.

The ETA document was first collected at `2026-10-07T11:42:18.380791Z`; the later arrival/berth document became available at `2026-10-08T08:25:09.569959Z`. The original audit preparation time `2026-10-08T08:25:13.619081Z` and the existing passed visual review `2026-10-08T09:12:12.275680Z` remain unchanged. Public downloads omit local filesystem links and actor/reviewer identities.

At the retained October 8 collection, Paradip has **23 frozen ETAs, three matched arrivals and one complete chain**; Chennai has **39 frozen ETAs and zero matched arrivals**. Collection started roughly **75 minutes after the preceding successful check plus three hours**. The dashboard presents this as data freshness, separately from vessel waiting. Counts and freshness describe the displayed state and are not benchmark scores.

Anonymous GET routes are explicitly limited to:

- `/api/public/port-calls`: current public collection status and reviewed cases, filtered by the backend's replay clock.
- `/api/public/port-calls/evidence/<64-character-sha>.pdf#page=<page>`: approved official originals, hash-checked before serving, with SHA ETag and `no-store`.
- `/api/public/port-calls/<caseId>/audit`: the sanitized public JSON case. Other child routes and writes retain verified identity.

Only a current complete, unambiguous match with three passed page checks agreeing with the archived hashes and fields is published. Outcomes or reviews unavailable at replay time remain withheld. Changed/conflicting evidence or a failed review withholds the case. Downloads use the configured web API origin; no `D:/...` link is required by a visitor.

`python -m scripts.publish_public_case <caseId>` packages a reviewed case and its approved originals under `data/public_port_cases`. The immutable `case-publication-420ed130487e4cda` bundle was prepared at `2026-10-08T09:54:41.093333Z` with two PDFs. Its hashed manifest and originals ship in the backend Docker image. A fresh cloud host can serve this archived study independently of local collector state, with an explicit archived-publication label; current freshness is unavailable if its store is unavailable. A current conflicting case cannot be resurrected through the archive fallback. Packaging time never replaces evidence availability or collection time.

### Chennai date review

`public-port-report-v1.2` separates overprinted PDF glyphs by their actual vertical baselines. It recovers a date only when every glyph supports identical valid headings; unexplained glyphs or distinct dates remain excluded. The actual October 7 and 8 ETA originals contain two different dates on page 2: `07/10/2026` and `12/10/2026`, then `08/10/2026` and `12/10/2026`. Neither report supports choosing one date for the affected rows. Four rows per report remain without an ETA and carry `CONFLICTING_DATE_HEADINGS` with both candidates and their raw text.

The two retained originals were reparsed at the actual October 8 review time, with the earlier parser revisions preserved. Hashes, original first-seen times, 39 frozen Chennai ETAs and cohort definitions were unchanged; no collection was triggered or backdated. The saved review is `outputs/backend_service/chennai-parser-review-2026-10-08T09-54-01.271844Z.json`. Future collection uses the revised parser after the updated backend source is released.

## Prepared cloud release

Reuse `india-portwatch-terminal/vercel.json`, `Dockerfile`, `railway.json` or `render.yaml`. Set frontend `VITE_PORTWATCH_AUTH_MODE=production` and build-time `VITE_PORTWATCH_API_BASE=https://<backend>/api`. Set backend CORS to the actual frontend domain.

Run one always-on backend instance and one uvicorn worker, verified identity, freshness scheduler and public refresh enabled, VesselFinder disabled. Mount durable storage at `/app/state` with `PORTWATCH_STATE_DIR=/app/state`. The historical release is packaged separately under `/app/data/research_release`; the reviewed case and PDFs are under `/app/data/public_port_cases` (`PORTWATCH_PUBLIC_CASE_DIR` can override this location). `.dockerignore` excludes credentials, local databases, private outputs, QA scratch and provider caches, while retaining both public bundles. Exploration may show unavailable states during first cache refresh; historical results and the archived GLAD YOUNG case are already packaged.

[Render FastAPI hosting](https://render.com/docs/deploy-fastapi), [Render disks](https://render.com/docs/disks) and [Railway volumes](https://docs.railway.com/volumes) describe hosting and mounting. Render persists writes under the disk mount and attaches a disk to one instance. The Docker defaults and Render blueprint specify `/app/state`; Railway’s volume/variables must be configured on the host.

Before publication, copy the existing public-pilot directory and originals with a consistent SQLite backup or a stopped writer. Preserve cohort cutoffs and receipt times. Keep local collection running until hosted scheduling and restart retention pass, then select one owner for the cohort. No backdated cases or automatic cohort evaluation. Transfer private identity/ledger state only through the authorized backup process; no credentials belong in frontend variables or the image context.

Hosted CORS, an unattended collection for both ports, restart retention and publication remain release checks. No cloud deployment has been performed by this work.

## Saved local validation

`work/public-research-validation.json` records 81 passing focused Python cases, five follow-on download checks, eight real-API browser checks across desktop/laptop/mobile, passing TypeScript and changed-file lint, and successful node-server/Vercel builds. The browser suite verifies anonymous access, 13 selectable ports, dated forecasts, scenario inputs, calibration/horizons, real downloads, denied private writes, retry behaviour and optional-store unavailability.

The earlier preview used 53 frozen ETAs with zero complete calls. The October 8 case-study preview uses read-only copies of **62 frozen ETAs, three matched arrivals and one complete reviewed call**, alongside the existing real caches, public-provider weather forecasts and immutable historical release. Original receipt times and cohorts are preserved. It is separate from the running collector and does not write production state. Historical downloads are tied to the displayed release and use `no-store`; a changed release returns 409 rather than silently delivering a different dataset.

`work/public-case-validation.json` records the case-study update's focused Python, TypeScript, changed-file lint, node-server/Vercel builds and browser results. Browser checks cover anonymous case access, raw clocks, timeline interaction, clock switching, HTTP PDF/audit downloads, stable paper links, unavailable states, Chennai exclusions and mobile layout. The production service was not restarted by this product update. The configured Vercel connector returned 403 for `flash2404s-projects`, and the CLI was logged out; internet publication requires restored access to that existing team. No public internet release is claimed by the local preview.

Full-repository lint was also run. It retains inherited violations outside this change, mostly formatting/line endings; the changed files pass. Generated Vercel/Nitro output is now excluded from source linting. Docker image execution remains unverified because the local engine was not running. Hosted checks and deployment remain pending. No operational accuracy or savings are established.
