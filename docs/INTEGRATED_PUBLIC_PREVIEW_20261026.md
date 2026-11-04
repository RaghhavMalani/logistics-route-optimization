# Integrated public preview: package prepared, hosting blocked

October 26, 2026. Reviewed starting application: `0cbfbb465d8fbfece67de238b49b63b5694cb992`, branch `feat/portwatch-restored-intelligence`. The user requested finishing the package after Railway rejected provisioning. **No integrated preview has been deployed or accepted. No hosted application revision, completed hosted journey or hosted restart is claimed.**

## Hosting baseline and blocker

Vercel's existing `india-portwatch` project is `prj_7rUm8f8iofYg1cSMlrROZsK7iWP0`, under team `team_PR9rk0IgzFMGT7tBXRWyiFgK`, root `india-portwatch-terminal`, TanStack Start, Node 24. Production remains branch `main`, deployment `dpl_A1h2oea2ujsFCgL5BCx3hYvjYyYQ`, deployed Git revision `f876bcccaa52f38cd951631a0b397c35200d4d90`, public alias <https://india-portwatch.vercel.app>.

The existing commit-specific feature frontend, <https://india-portwatch-bssz6q4dl-flash2404s-projects.vercel.app/login>, returned the application's login HTML anonymously without Vercel SSO. Its deployment `dpl_7Ab1P5tN7qVASRQhVi5ynQTqEptp` matches `0cbfbb4`. **It is frontend-only evidence, not a working integrated preview:** its API proxy returned Railway `404 Application not found`.

Read-only HTTP checks at **2026-10-26T05:43:06.817304Z** also found the same platform 404 on the existing production API, production proxy and preview API, before any attempted provisioning. The existing production outage was not repaired or hidden with a fallback. Production research/original downloads were inaccessible, so live immutable-production-evidence comparisons remain unverified.

Railway project: `983b8896-688f-47ea-a693-6985e84ab03b` (`india-portwatch-api`), workspace `de4c37e5-ddec-4202-be73-0804b58a4441`.

| Binding | Existing preview | Production |
| --- | --- | --- |
| Environment | `restored-preview` / `7a2cfc66-cf8b-4c07-a852-ec93798068b7` | `production` / `7a940de4-9c13-411e-ad59-eb30ee42a9d4` |
| Service | `api-restored-preview` / `0b60aa68-6b07-4854-bea3-8ace1e684e27` | `api` / `128a61e8-a333-4c93-aa77-550d4e923495` |
| Volume | `f3317bc8-f667-4e7c-9038-01854fa95174` | `e8138731-4d1a-408f-b453-7343c2adbe57` |
| Mount | `/app/state` | `/app/state` |
| Public hostname | `api-restored-preview-restored-preview.up.railway.app` | `india-portwatch-api.up.railway.app` |
| Domain target port | 8080 | 8000 |
| Active deployments at baseline | 0 | 0 |

The primary production hostname's conditional rewrite targets the production API. Other hostnames of that same frontend artifact, including its generated URL and secondary aliases, use the legacy preview catch-all. Those are existing consumers of the old preview API. The next candidate should use a separately verified service instance/environment and volume, leaving those consumers and existing stores untouched. No replacement project is needed. Check the provider's current environment-scoping behavior before creating a service; do not assume an operation affects only the linked checkout/environment.

The saved Railway login had expired; the user completed normal sign-in. Read access resumed. Workspace metadata reported `HOBBY`, but the actual attempt to create empty isolated environment `integrated-preview-20261026` was rejected with **“Your trial has expired. Please select a plan to continue using Railway.”** The environment was not created. A separate attempted pre-deployment snapshot of the old preview volume was rejected because manual backups require a Pro workspace; no backup was created and no upgrade was purchased. Both old volumes were left untouched. Restoring deployment entitlement in the existing account is a user dependency; a plan label alone is not proof of deploy access.

## Package compatibility changes

`health.release` adds strict server-configured application SHA, environment name and Railway service/environment/deployment UUIDs. Missing or malformed values remain `UNKNOWN`. Request headers, credentials, other environment values and filesystem paths cannot supply the marker. This supports future trusted frontend-proxy-to-backend binding checks alongside provider metadata; it is not proof of isolation by itself.

`PORTWATCH_PUBLIC_EVIDENCE_SEED_MANIFEST` opts into a public-only import before collectors start. Absent configuration is a no-op. The importer verifies every declared file's SHA-256/size, normalized paths, exact database table/column allowlists and public row semantics before destination writes. Credentials, visitor scopes, private tasks, operator outcomes, station records, sealed benchmarks and correction-promotion artifacts are rejected. Source IDs, forecast origins, receipt/qualification clocks and revisions remain unchanged. Cloud import time is a separate audit event.

Existing destination databases receive consistent SQLite backups before additive merge. Identical records are no-ops. Existing conflicting rows/files remain in place; incoming public records/bytes are quarantined with hashes rather than replacing newer state. Compatible missing numerical outcome fields may be filled only when the frozen prediction basis agrees. Repeat import of a completed manifest is idempotent. Evidence databases, originals, audit and quarantine must remain inside configured durable state. No new scheduler, learner, authentication flow or public evidence-upload endpoint is introduced.

`.dockerignore` permits only the explicitly named `data/cache/preview_public_seed/` package in addition to existing public exceptions. Docker still runs one Uvicorn worker and Railway configuration still requests one replica. The restored eight role/twin files, passage/finance/ranking/deadline equations, hourly approach weather and rejected models are unchanged.

## Qualified public evidence export

The frozen export is `work/hosted-preview-20261026/public-seed-r2/manifest.json`, prepared **2026-10-26T05:43:04.217260Z** from the existing public stores under application `0cbfbb4`. Its manifest SHA-256 is `d00aa539dbbe96fb18777b24fb0c65e48fa59602d918969f56aeb5c6f9cb1587`. It contains **1,383 files / 57,960,310 bytes**, including three newly constructed allowlisted SQLite exports and their required public originals. All 545 referenced raw-original hashes were found; no missing original or source-path conflict was reported.

| Exported scope | Retained records |
| --- | --- |
| Public FX/news feedback | 644 allowlisted feedback rows and 10 economic predictions |
| Public weather | 9,365 provider forecasts, 7,685 forecast annotations, 351 ERA5 outcome-evidence rows, zero correction-version rows |
| Existing public-port pilot | 16 publisher snapshots, 130 frozen cases, two enrolling cohorts and 130 memberships; no sealed benchmark rows |

Each source database was read in a consistent read-only transaction including committed WAL. Entire runtime databases, identities, sessions, private tasks, operator/camera records and unrelated prediction domains were not copied. Public table bodies may retain internal historical archive metadata; semantic bodies/IDs are not rewritten to relocate files. Existing canonical public resolvers and explicit DTO projections remain responsible for source lookup and download restrictions.

A full **local-only** import into fresh isolated stores completed with zero conflicts. Its fixed as-of inspection reproduced three qualified FX matches and seven pending targets, with three source-original hash checks passing. This is the frozen export's historical checkpoint, not a required future cloud total. GAC remains unresolved after HTTP 403; importing authority evidence does not manufacture a secondary report, closure occurrence or operational outcome. Weather remains collecting/shadow-only and imported reanalysis is not relabelled as station measurement.

The evidence manifest's source revision identifies where the retained dataset was exported. The packaging commit adds transport/qualification safeguards; it does not claim that the cloud originally predicted those historical targets. No cloud import time exists yet.

## Local validation and clean artifacts

- **44 focused local tests passed** across seed import, release identity, research, current-input journey, passage workflow and feedback API. Tests cover invalid hashes, private/credential metadata, path escape, durable originals, conflicting retained records, backup identity, retry/restart behavior and existing visitor isolation. One inherited FastAPI/httpx deprecation warning remains. Earlier runs overlap and are not added to this count.
- TypeScript and an isolated `NITRO_PRESET=vercel`, production-authentication Vite/Nitro build passed, using the existing lockfiles/dependencies and same-origin `/api`. Targeted API-service ESLint and Python syntax checks passed. The package helper that stops previews was not invoked. No frontend source was changed; its source equivalence to the reviewed interface is checked in the package manifest. Built static assets contain zero source maps. Existing chunk-size and plugin notices remain.
- Actual public seed import and three imported FX-original hashes passed locally. These are not hosted checks. No source fixtures were inserted into a shared hosted store.
- The reusable clean-export helper reads the exact Git commit with CRLF conversion disabled and verifies every file against its Git blob. Separate backend/frontend allowlists exclude all 19 dirty CSV versions, credentials, private/session state, `debug.log`, runtime stores and previous build outputs. Public research artifacts retain their existing hashes. Final fingerprints and source SHA are recorded in the ignored `release-package.json` and keyed clean-source manifests generated after this commit.

Hosted API/browser start/resume harnesses are prepared under `work/hosted-preview-20261026/verification/`. Python syntax and ten browser-case discovery checks passed. **The hosted journey, four-role browser acceptance, actual preview restart, hosted retries/isolation, live preview collectors and unattended collection cycles have not been verified.** Old local successes are not substituted for these missing checks.

## Resuming deployment

1. Restore existing Railway deployment entitlement. Re-read service/environment/volume/domain consumers; do not change either existing backend or production configuration to make provisioning pass.
2. Provision the isolated candidate and prove its storage separation. Keep one worker/replica, `PORTWATCH_IDENTITY_MODE=verified`, `PORTWATCH_LICENCE_MODE=DEMO`, unsupported paid providers disabled, and consistent listen/domain ports.
3. Review and configure only that candidate: durable state `/app/state`, current environment `/app/state/current_environment`, public weather DB/report and feedback DB under state, research assets `/app/data/research_release`, and `PORTWATCH_PUBLIC_EVIDENCE_SEED_MANIFEST=/app/data/cache/preview_public_seed/manifest.json`. Bind the exact package SHA and preview environment through the non-secret release marker.
4. Regenerate clean artifacts at the chosen reviewed SHA. Copy only the separate public manifest's declared files into its named seed folder. Railway's uploader also reads `.gitignore`; use `--no-gitignore` only for the already audited clean upload context, and verify the final combined source/public-data allowlist. Never upload the dirty checkout or a dependency/build junction. The generated local `.vercel/output` is build evidence, not a published deployment.
5. Update only the candidate's backend routing through a reviewed preview-scoped configuration. Deploy through the existing Vercel project/team Preview environment. Verify returned target/environment, anonymous application entry, real JSON/media API responses, exact server SHA/provider IDs and absence of production fallback.
6. Run the prepared same-origin API/browser checks. Complete Company approval, perform a provider-recorded restart of the isolated backend, then resume Port issue → Vessel acknowledgement/acceptance → explicitly simulated outcome. Verify original/audit hashes, retries, another visitor's rejection, four original workspaces, maps/globe/layers/timelines, narrow/enlarged text and unavailable-provider behavior. Keep secret checkpoints/traces outside Git.
7. Record actual collector receipts and distinguish startup collection from an unattended six-hour cycle. Repeat read-only production binding/protection/routing and available immutable-evidence checks. No production promotion is authorized.

Current handoff status: **tested package; deployment blocked and deferred at the user's request**. A usable integrated public URL will be reported only after those hosted checks pass. Existing production deployment/domain/API configuration and existing volumes were not changed by this task; their pre-existing API outage remains visible.
