# Isolated Railway Hobby preview — 2 November 2026

This is the release procedure for the restored interface, public-source profile
and Company-private commercial/shadow capability. Production promotion is not
authorized. Deployment results must be recorded separately from local checks.

## Verified target and preservation boundary

| Resource | Candidate |
|---|---|
| Railway project | `india-portwatch-api` / `983b8896-688f-47ea-a693-6985e84ab03b` |
| Environment | `integrated-preview-20261102` / `678352b2-e032-4c0c-b900-60f68fa3562f` |
| Service | `api-integrated-20261102` / `c7dfe1db-2fd0-4c24-8a59-dde1d34239c2` |
| Dedicated volume | `98bef1f2-c3b9-46a8-bcc6-2f654e094fd8`, 5 GB, `/app/state` |
| Region/replicas | `sfo`, one replica; one Uvicorn worker |
| Backend | `https://api-integrated-20261102-integrated-preview-20261102.up.railway.app`, port 8000 |
| Vercel team/project | `flash2404s-projects`, `prj_7rUm8f8iofYg1cSMlrROZsK7iWP0` |
| Vercel target/root | Preview / `india-portwatch-terminal` |

Empty candidate environment/service and a new volume were provisioned through
the authenticated CLI. No production environment was duplicated. Provisioning
succeeded; this is stronger evidence of restored access than the plan label.
The Vercel connector lacked a team grant, so the already authenticated CLI is
used in that same existing team. No plan or protection setting was changed.

Production remains environment `7a940de4-9c13-411e-ad59-eb30ee42a9d4`, service
`128a61e8-a333-4c93-aa77-550d4e923495`, volume
`e8138731-4d1a-408f-b453-7343c2adbe57`. Its current deployment before this work
was `734e4a9f-4a18-452b-81e3-4d74e8da3f24`; an older October outage is not its
current status. The legacy `restored-preview` service
`0b60aa68-6b07-4854-bea3-8ace1e684e27` retains volume
`f3317bc8-f667-4e7c-9038-01854fa95174` and its original hostname.
Neither is attached to the candidate volume.

The Vercel production branch is `main`; its production deployment baseline is
`dpl_A1h2oea2ujsFCgL5BCx3hYvjYyYQ`. Existing production-host-specific and legacy
catch-all API rewrites are preserved in the repository. Only the clean uploaded
candidate copy changes the final catch-all to the new candidate. Old generated
Vercel URLs therefore retain their old upstream. No `--prod`, production alias,
global preview variable or protection change is part of this procedure.

Full configuration snapshots stay private under ignored
`work/hosted-preview-20261102`; sanitized fingerprints contain no credentials.
Pre-provision versus pre-deploy Railway production/legacy configurations matched.
The feature branch is outside the current GitHub Actions push trigger list.

## Clean source and evidence package

After local validation, commit and push scoped files normally on
`feat/portwatch-restored-intelligence`. Preserve the nineteen unrelated dirty
activity CSVs and `debug.log`; do not stage or export their working-tree bytes.

Run `scripts/prepare_integrated_preview.py` with the full reviewed commit,
a fresh ignored output directory, the explicit candidate API, the reviewed
`work/hosted-preview-20261026/public-seed-r2/manifest.json` and `data/cache`.
The helper exports Git blobs, checks hashes/path containment/credential patterns,
validates the public seed, and separately qualifies thirteen public runtime caches.
It refuses private/session databases, local dependencies and old build directories.

The historical public seed originates at
`0cbfbb465d8fbfece67de238b49b63b5694cb992`; it is not newly collected evidence.
Original issue, receipt and availability times survive import. The importer runs
before collectors, is idempotent and quarantines conflicts rather than replacing
retained evidence. The runtime cache's old filesystem age is retained only while
its body hash matches; a Docker copy must not make old intelligence current.
These static research/demo caches are separate from current port forecasts.

The backend image includes `data/preview_release/source-manifest.json`.
Startup verifies packaged Git blob identities and SHA-256/byte counts; a required
manifest failure prevents readiness. `/api/health` exposes this proof separately
from server-configured release/provider identifiers, durable-store checks and
process boot identity. The uploaded frontend has a nonsecret `/release.json`.
Match all three against provider deployment/image metadata; an environment
variable by itself is insufficient release proof.

## Durable stores and bounded operation

Candidate variables explicitly bind verified identity and DEMO licence, with:

| Store | Location |
|---|---|
| Identity, visitor worlds, advisory/decision ledgers, private commercial studies/jobs | `/app/state` and visitor subdirectories |
| Current forecasts, hazards, notices and immutable originals | `/app/state/current_environment` |
| Public news/economic feedback | `/app/state/portwatch_ledger.db` |
| Weather forecasts/outcomes | `/app/state/public_weather_forecasts.sqlite3` |
| Weather report | `/app/state/public_weather_feedback.json` |
| Public port collections, cohorts, audits, evidence | `/app/state/public_port_pilot` |
| Additional public product originals/receipts | `/app/state/public_products` |
| Import audit, consistent backups and conflict quarantine | `/app/state/public_evidence_import` |
| Retained research exports | `/app/data/research_release` (immutable image assets) |

Rebuildable model/presentation caches and outputs are image/ephemeral assets;
they do not contain the sole copy of visitor decisions or source originals.
Global activity CSV pipeline refresh and paid VesselFinder are disabled. Optional
AIS keys remain absent unless separately supplied server-side; absence is not
coverage. Authorized camera footage is still unavailable. Weather reconciliation
remains **collecting**, with daily correction separated from hourly approach rules.
Rejected neural and RL artifacts/evaluations remain rejected and unchanged.

Use the existing coordinator/reconcilers in the backend lifespan, one worker and
one replica. `sleepApplication=false`, configured `PORT=8000`, the domain target
and listener must agree. Graceful shutdown stops collectors. Do not add a cron,
scheduler service, external queue or training process. Startup receipts, scheduled
receipts and unattended cycles must be reported separately with real timestamps.

Commercial Monte Carlo is declared-assumption shadow sensitivity, not validated
operational risk. Inputs/draws are bounded (16–4096 draws and a 100000 combined
work budget), with one concurrent study per backend, a cooperative 20-second
budget and Company-private cancellation/status. Completed result hashes, seed,
configuration, job events and successor binding persist in the existing ledger.
A restarted unfinished job is interrupted, not silently completed. API health
and cancellation remain served by the existing request executor. Draws do not
increase independent operational target counts or promote a policy.

## Backup, storage and rollback

On the candidate only, run `python scripts/candidate_state_backup.py` through
explicit project/environment/service selectors. It refuses other release markers
and paths. The utility uses SQLite's backup API, detects concurrent source
commits/file changes, and accepts only a quiescent snapshot. It then restores into
a distinct scratch directory and checks SQLite integrity, schema/content digests,
row counts and file hashes. It never copies an active SQLite file without WAL
semantics, overwrites a live store or restores into an old volume. A concurrent
write invalidates that attempt; retry in a quiet window. Backups contain private
state and must never be committed, published or used as public seeds.

The existing account has no configured SSH key, so the initial SSH attempt did
not execute a command. No SSH credential or account access was added. For this
release set a fresh 32-character lowercase hexadecimal
`PORTWATCH_CANDIDATE_BACKUP_REQUEST` on the candidate only. Startup runs the same
backup/isolated restore check after idempotent seed import and before collectors
or HTTP requests. A durable request receipt makes subsequent boots idempotent;
the same request does not create more copies. It verifies the retained manifest
hash before accepting a repeated receipt. A non-candidate marker/path, malformed
request or failed restoration prevents startup. `/api/health.candidateBackup`
reports aggregate proof without private record IDs, paths, contents or keys.
This adds no public backup mutation endpoint, account key or scheduler.

The 5 GB volume is finite. Retain frozen evidence, source revisions, prospective
cases and approvals. No automatic purge of them is enabled. Disposable process
logs remain outside the evidence stores. Inspect volume usage with Railway
metrics; at 70% review growth and redundant verified backup/restore-check copies,
and at 85% pause new collection/operator submissions before exhaustion, preserving
inspection and existing evidence. Cleanup requires explicit operator review and
an independently verified export; never delete referenced originals or silently
remove expired-session evidence. No automatic backup rotation is claimed.

Record measured CPU/RAM/volume use after startup and a study. One always-running
replica and a 5 GB volume incur recurring usage; do not infer a monthly price or
unlimited allowance from Hobby. The source cadence/request budget is documented
in `UI_AND_FREE_PROVIDER_COVERAGE.md`. No new paid provider/database/queue is used.

A code rollback targets only this candidate and must preserve schema compatibility.
Use a verified candidate backup before incompatible migrations. A rollback does
not undo a migration. Volume-backed redeployments may briefly interrupt service;
deploy-time health readiness is not continuous monitoring or zero downtime.

## Acceptance and handoff

Before declaring the integrated preview accepted: verify anonymous access and
all four normal demos, actual maps/globe/mobile Layers/Timeline, source dates and
missing-provider states, private commercial and shadow review, exact saved links,
Company approval, a provider-recorded candidate restart, then Port review/issue,
Vessel acknowledgement/acceptance and explicitly simulated outcome. Compare
frozen hashes/inputs after reload and retries; test another visitor and wrong role.
Hash-check original/audit downloads and replay filtering. Test the candidate-only
backup/restore and compare production/legacy preservation fingerprints afterward.
Do not mark pending checks passed or substitute local screenshots for hosted tests.

Deployment IDs, commit, package/seed hashes, verified frontend URL, resource
measurements and final acceptance evidence will be appended after execution.

## Initial candidate acceptance, before the backup follow-up

Source `82756d5b7fe533603549768b9cff64fcd5a81661` was pushed and exported cleanly.
Railway deployment `87042b15-5397-42b0-a63c-5f86647a2bd1` and Vercel Preview
`dpl_49fSk4BMmcWqk7LLhs8j61raCM7d` served that revision. Direct and same-origin
health matched the source manifest hash
`66e9bef2aa0c095d217635b2069ce1106be536377cd8121876f84d89eccff94c`
(579 source files, thirteen retained runtime caches). The seed manifest hash is
`d00aa539dbbe96fb18777b24fb0c65e48fa59602d918969f56aeb5c6f9cb1587`.
Vercel had no aliases assigned and no production target. This is an initial
candidate, not a production promotion or the final backup-enabled build.

The unmocked hosted UI passed 21 behavior checks and the complete 127.1-second
normal-login commercial/shadow/advisory recording, including a provider-recorded
restart. A separate genuine-current-forecast API comparison
`dec-arrival-29d14d60808dc2706a56` retained source
`719e6294a3652d18866c9e6ffd5ac530ca8e09cd039ed587f71112beb6a5e421`, then
recovered across another real restart and completed Port/Vessel workflow as
`ADV-INNSA-015972E390`. Frozen audit bytes and three original downloads matched;
handoff/outcome retries were idempotent and another visitor was refused access.
This is a fictional voyage driven by a genuine forecast, followed by a simulated
outcome; no realized saving is established. The reported provider issue time was
unavailable and stayed null. Actual source receipt was retained separately.

Early browser-role harness attempts used obsolete assumptions about server-rendered
login markup and uppercase traffic DOM text; current roles are hydrated and the
visible uppercase label is styled text. A recorder attempt separately hit a DOM
replacement between explicit scrolling and clicking. Normal locator clicking and
the actual rendered text contract resolved these harness failures; no forced click,
response substitution or application authentication relaxation was used. One role
attempt overlapped the deliberately requested restart and saw its brief 502.
Final role entry must be checked after restart completion.

The 30-minute startup/test observation window ending 13:23:20 UTC measured average
CPU 0.112 vCPU (peak 1.143), current/peak RAM 786.4 MB, and current volume use
217.7 MB (peak 235.2 MB) of 5000 MB. These are short-run samples, including idle
time and active demonstration visitors, not steady-state estimates or a monthly
price. Startup and scheduled weather/public-source receipts are distinct from
long-running unattended availability. The new backup's additional disk use must
be measured after it runs.

References: [Railway environments](https://docs.railway.com/environments),
[healthchecks](https://docs.railway.com/deployments/healthchecks),
[serverless behavior](https://docs.railway.com/deployments/serverless),
[volumes](https://docs.railway.com/volumes/reference),
[Vercel environments](https://vercel.com/docs/deployments/environments).
