# Railway cleanup completion

Authorized by the user's explicit request to remove the stopped performance and twin preview services and empty environments, while retaining production, fallback, volumes, backups and rollback dependencies. Executed 6 November 2026 IST.

## Service removal

Verified each target belonged only to its retired environment, had no volume, and had `deploymentStopped=true` with instances `STOPPED` before removal.

| Removed service | Service ID | Former environment |
| --- | --- | --- |
| `api-home-perf-preview` | `766f2e8d-42f4-45a1-a476-2cdd1cff5efe` | `role-home-perf-preview-20261104` |
| `api-twin-preview-20261104` | `b990f246-9314-4661-b104-b23320e101c2` | `twin-preview-20261104` |

Both are absent from the project's global service list after deletion.

## Empty-environment removal

Immediately before each deletion, the authenticated project inventory was refreshed and checked for the exact environment ID/name, zero service instances and zero volumes. The project also had no buckets.

| Removed empty environment | Environment ID |
| --- | --- |
| `role-home-perf-preview-20261104` | `4f2036f8-d8c7-42c2-9456-dcc8412a14e5` |
| `twin-preview-20261104` | `c5ad2026-e8a2-48d3-930b-a296126bc152` |
| `sar-data` | `b806aafc-2cda-4cd1-861f-77a57186e769` |

The final inventory contains four services and four environments, down from six services and seven environments. Every remaining resource is listed below. The retired service objects were removed globally, rather than merely left stopped or unlinked.

## Protected resources

- Production: environment `7a940de4-9c13-411e-ad59-eb30ee42a9d4`, service `128a61e8-a333-4c93-aa77-550d4e923495`, deployment `082b734f-9efb-4348-b7f9-16cb585c640e`.
- Working isolated fallback: environment `ac05145c-5d4f-448e-8476-338bf7013af0`, service `b051a10f-6691-4c7a-9eff-490eb217752e`.
- Older API required by the recorded Vercel rollback deployment: environment `678352b2-e032-4c0c-b900-60f68fa3562f`, service `c7dfe1db-2fd0-4c24-8a59-dde1d34239c2`.
- Historical `restored-preview` environment and service remain because its volume must be preserved.
- All three project volumes: `e8138731-4d1a-408f-b453-7343c2adbe57`, `98bef1f2-c3b9-46a8-bcc6-2f654e094fd8`, `f3317bc8-f667-4e7c-9038-01854fa95174`.
- No volume file, accepted backup, release setting, source setting, production deployment or Vercel alias is targeted by this cleanup. No SSH key is needed or created.

## Final verification

The sorted project volume ID lists are identical before and after deletion; all three volumes remain attached to their retained environments. Production deployment `082b734f-9efb-4348-b7f9-16cb585c640e` remains successful, and recorded prior Railway deployment `573c7252-fb5c-4114-9421-7aac1203fbc2` remains eligible for rollback.

| Retained endpoint | Health | SHA / identity |
| --- | --- | --- |
| `india-portwatch.vercel.app/api/health` | `ok` | Main SHA `7bdeb9690b7c501ef147ad36cf04f4f173900c0f`, production service and deployment unchanged |
| Feature-integration isolated API | `ok` | `2e43af315d75faa5d138830b274dc6406ef4df1c`, service `b051a10f-6691-4c7a-9eff-490eb217752e` |
| November 2 rollback API | `ok` | `33f27ecf3be54c2054b7e035fea5b054266980a3`, service `c7dfe1db-2fd0-4c24-8a59-dde1d34239c2` |

Vercel's production alias still identifies ready deployment `dpl_CaL7pM197KbrJozKkm6YUchapfVQ` at the same main SHA. No main push, application deployment, volume deletion or backup-file operation was performed.

Raw before/after snapshots and mutation receipts: `D:/LogisticOptimization-_Capstone_168/work/railway-operations-20261106/` (`cleanup-*`, `deleted-*.json`). These receipts contain infrastructure metadata, not database contents or secret values.
