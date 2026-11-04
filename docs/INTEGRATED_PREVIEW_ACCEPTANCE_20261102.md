# Verified integrated preview

Validation completed on 2 November 2026 UTC. This is an isolated Preview release;
the production domain was not promoted or repointed.

**Application:** [open the four-role demo entry](https://india-portwatch-ah5ecru6b-flash2404s-projects.vercel.app/login).
**Deployed source:** [`a80a42768e84ebced9a08bdee16feca918dd7fd7`](https://github.com/RaghhavMalani/logistics-route-optimization/commit/a80a42768e84ebced9a08bdee16feca918dd7fd7).
Branch: `feat/portwatch-restored-intelligence`. A subsequent documentation-only
commit records acceptance; it does not change the deployed application SHA.

## Source and deployment proof

| Item | Verified identity |
|---|---|
| Vercel deployment | `dpl_HBADe18PGeeD2czsdBQbySzSsZeQ`, READY, Preview, no aliases |
| Railway deployment | `cc20087c-805a-4e6e-ad0c-b15b9454765d`, SUCCESS |
| Railway environment | `678352b2-e032-4c0c-b900-60f68fa3562f` / `integrated-preview-20261102` |
| Railway service | `c7dfe1db-2fd0-4c24-8a59-dde1d34239c2` |
| Dedicated volume | `98bef1f2-c3b9-46a8-bcc6-2f654e094fd8`, `/app/state`, 5000 MB |
| Provider image digest | `sha256:3625adf8ce82a07f3531c7bb5d838b07dbd4d91b9711268e72fa3da05b07574b` |
| Image source manifest | `083f337fe8f42443e2429d0049c87fb41bd7af65aa81d29b5015ace63fe2d3d4` |
| Backend package fingerprint | `f318d809aa2c9b718b45b62845296dfed8a9561b093fc73989e7106c37cbe2d9` |
| Frontend source fingerprint | `a50627b43f8039725d25a813fe3ee2cd0fe21ba44af1996533626a68dbf50750` |
| Historical public seed manifest | `d00aa539dbbe96fb18777b24fb0c65e48fa59602d918969f56aeb5c6f9cb1587` |

Startup verifies 579 Git-source files and thirteen separately qualified retained
runtime caches. Direct backend and same-origin `/api/health` agreed on artifact,
source SHA, environment/service/deployment and process identity; `/release.json`
agreed with that source and the Vercel metadata. The frontend source fingerprint
is unchanged through the backend cancellation fix: the restored UI was preserved.
The historical seed remains labelled as originating at `0cbfbb4`; its receipt,
forecast and availability times were not renewed by import.

The candidate backend is
`https://api-integrated-20261102-integrated-preview-20261102.up.railway.app`.
It runs one Uvicorn worker and one `sfo` replica, with app sleep disabled and port
8000 matching the domain target. All durable stores remain on the candidate volume.

Readback of the provider service-instance API confirmed `/api/health` and a
300-second timeout after the final restart. Sparse deployment metadata had shown
null healthcheck fields, and the environment-edit CLI returned a no-op. Neither
was accepted as configuration proof. The supported service-instance mutation set
the candidate fields explicitly; redeployment reused the verified image, then
the fields were read back again. This did not change production or legacy settings.
Deployment readiness is distinct from provider freshness and continuous monitoring.

## Cancellation and recovery

The demo adapter previously serialized cancellation behind the running study's
visitor write lock. The fix exempts only its internally named job-cancel route;
server-owned identity, Company permission and job ownership checks still apply.
All other world mutations retain serialization.

The real hosted check observed RUNNING → CANCELLATION_REQUESTED → CANCELLED.
The calculation returned the expected HTTP 409; retained elapsed compute was
0.874 seconds, and concurrent health completed in 0.453 seconds. The workload was
an explicitly fictional S16 declaration: 4096 draws, twelve consignments and two
options, 98304 draw×shipment×option units within the existing 100000 cap, with
bounded zero-valued test components. It was not operational or learning evidence.

A provider-recorded redeploy and another restart replaced the process. The same
visitor recovered the CANCELLED job from durable ledger events after its in-memory
registry was gone. This is not inferred from a browser reload. Earlier pre-fix
cancel attempts that completed behind the write lock were retained as failed
diagnostics and were not counted as successful cancellation.

The final normal-login recording then completed Company private commercial and
insurance review, a seeded 256-draw shadow study, a linked successor and Company
approval; an actual candidate restart; Port review/issue; Vessel acknowledgement
and acceptance; and explicitly simulated closure. Fifteen scenes completed in
189.4 seconds with no application runtime errors. The restored map, globe,
timelines, inspectors, role navigation and digital twin remain available.

## Completed checks

| Check | Result | Local evidence under ignored `work/hosted-preview-20261102` |
|---|---|---|
| Current backend release subset, including concurrent same-visitor cancellation through ASGI | 48 passed | `cancel-adapter-tests.log` |
| Anonymous one-click Company, Vessel, Port and Admin, desktop and mobile; reload and twin | 8 passed | `cancel-roles.stdout.log`, `verification-cancel-fix/` |
| Exact decision/option links, reload, worklist/source reopening, globe mount/focus, 360/390/landscape, Layers/Timeline, enlarged text, visitor refusal | 21 passed, zero runtime errors | `audit-cancel-fix/browser-audit.json` |
| Old frozen options/approval history, source/audit bytes, private studies/jobs, wrong-role/visitor refusal, bounded inputs, replay/future filtering | 16 passed | `cancel-extra-checks.json` |
| Actual cancellation and durable recovery | PASS | `actual-cancellation.json`, `cancel-recovery-proof.json` |
| Normal connected UI journey across a provider restart | PASS | `ui-cancel-fix/manifest.json`, captions, video and screenshots |
| SQLite-consistent backup and isolated restoration | RESTORE_VERIFIED | startup log and health proof |
| Production/legacy preservation | PASS | `preservation-final.json` |

These counts describe separate runs and are not summed into an invented suite
total. Earlier local regression runs are documented in [UI validation](UI_UPGRADE_VALIDATION.md).
Hosted tests used the real Preview and normal server-issued demo sessions, without
response mocks, forced clicks, browser identity seeding or protection relaxation.
Private checkpoints, databases, raw hosting configuration and generated media
remain excluded from Git.

Three original public-evidence downloads matched their SHA-256 hashes. A frozen
as-of audit remained byte-identical across source upgrades and restarts. Retries
did not duplicate studies, advisories or outcomes. Another visitor and wrong role
could not inspect/cancel private Company records. Replay withheld later-available
public products and current-only feeds without changing another visitor's clock.

## Collection, storage and limits

At final inspection the scheduler was running with its existing 30-second tick.
Successful automatic USGS runs were retained at 18:41:46 and 18:46:17 UTC in the
final process. These were scheduled backend work, not GET-triggered or manually
manufactured receipts. This observes repeat collection during verification;
day-long unattended availability is not claimed. The backend remains running.

The final Company screen showed current weather for thirteen ports and separately
labelled stale activity. INNSA's qualified surface response hash was
`4574ae8c284e22221822f22dcf4a055d8724c5c47d53db6e88ea89d82ccdef9b`, first
available at 17:58:10 UTC; provider issue time remained unavailable. Source checks
and first availability stay separate. Weather reconciliation is **collecting**;
daily correction/shadow evidence does not change hourly approach calculations.
Both rejected model candidates and their historical research artifacts remain
unchanged. No correction or model was promoted.

Current additional-product inspection found USGS current; JWC and Comtrade
historical; GDELT and the two FRED products unavailable after timeouts; and IMF
unavailable after failed qualification. Historical feedback evidence remains
inspectable despite current collection failures. Chennai attempts also timed out.
AIS access/live coverage and authorized CCTV footage remain unavailable. No
generated fallback, invented closure, measured saving or insurance cover is implied.
Monte Carlo remains declared-assumption shadow sensitivity, not calibrated risk.

The candidate-only backup restored 1748 files and 41 SQLite databases into separate
scratch stores, with integrity/content/file-hash checks. Its manifest is
`bb9291a06dd8f5de21be8afcebe82a4b0267186600f7e5d4da1e3168d1f41e60`.
It is the retained snapshot created under `c3ea154`, not a fresh snapshot at every
later boot. The same request receipt remained idempotent through later restarts.
Backups contain private state and are never public seeds or downloads.

The measured 15-minute window ending 18:50:11 UTC averaged 0.090 vCPU (peak 0.549),
with current/peak RAM 794.7 MB and volume use 559.2 MB of 5000 MB (peak 578.5 MB).
These are short test-window observations, not monthly pricing or an unlimited
allowance. Keep the storage thresholds, backup procedure and schema-compatible
rollback guidance in [operations](INTEGRATED_PREVIEW_20261102.md). No extra worker,
scheduler service, paid provider, queue, database or plan upgrade was introduced.
The provider warns that legacy config-as-code support ends 1 December 2026;
its migration is a future maintenance task, not a change made to production here.

## Preservation and review media

Production remains on Railway deployment `734e4a9f-4a18-452b-81e3-4d74e8da3f24`
and Vercel production deployment `dpl_A1h2oea2ujsFCgL5BCx3hYvjYyYQ`. Production
and legacy configuration hashes, service/volume/domain bindings, production branch,
project protections and tracked upstream rewrites matched their baselines.
The candidate has its own volume and hostname; no production alias was assigned.
Nineteen unrelated dirty activity CSVs and `debug.log` remain outside the commits.

Sixteen full-size before/after pairs, their board and the captioned local
walkthrough are available at `http://127.0.0.1:8922/` on the development computer.
The paired presentation captures share saved cases/cameras and a fixed display
clock, with frozen shared responses; new or uncaptured endpoints retain their own
explicit status. The mixed worklist is a labelled synthetic UI fixture. These
captures are presentation evidence, distinct from unmocked hosted validation.
The original 7:25 recording remains unchanged. No review media was publicly uploaded.
The final visible hosted Company screenshot is retained locally as
`work/hosted-preview-20261102/final-hosted-company.jpg`.
