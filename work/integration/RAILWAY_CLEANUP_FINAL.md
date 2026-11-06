# Railway cleanup completion

Authorized by the user's explicit request to remove the stopped performance and twin preview services and empty environments, while retaining production, fallback, volumes, backups and rollback dependencies. Executed 6 November 2026 IST.

## Service removal

Verified each target belonged only to its retired environment, had no volume, and had `deploymentStopped=true` with instances `STOPPED` before removal.

| Removed service | Service ID | Former environment |
| --- | --- | --- |
| `api-home-perf-preview` | `766f2e8d-42f4-45a1-a476-2cdd1cff5efe` | `role-home-perf-preview-20261104` |
| `api-twin-preview-20261104` | `b990f246-9314-4661-b104-b23320e101c2` | `twin-preview-20261104` |

Both are absent from the project's global service list after deletion. Their former environments and `sar-data` were confirmed to have zero services and zero volumes. Empty-environment removal and the final preservation check follow separately.

## Protected resources

- Production: environment `7a940de4-9c13-411e-ad59-eb30ee42a9d4`, service `128a61e8-a333-4c93-aa77-550d4e923495`, deployment `082b734f-9efb-4348-b7f9-16cb585c640e`.
- Working isolated fallback: environment `ac05145c-5d4f-448e-8476-338bf7013af0`, service `b051a10f-6691-4c7a-9eff-490eb217752e`.
- Older API required by the recorded Vercel rollback deployment: environment `678352b2-e032-4c0c-b900-60f68fa3562f`, service `c7dfe1db-2fd0-4c24-8a59-dde1d34239c2`.
- Historical `restored-preview` environment and service remain because its volume must be preserved.
- All three project volumes: `e8138731-4d1a-408f-b453-7343c2adbe57`, `98bef1f2-c3b9-46a8-bcc6-2f654e094fd8`, `f3317bc8-f667-4e7c-9038-01854fa95174`.
- No volume file, accepted backup, release setting, source setting, production deployment or Vercel alias is targeted by this cleanup. No SSH key is needed or created.

Raw before/after snapshots and mutation receipts: `D:/LogisticOptimization-_Capstone_168/work/railway-operations-20261106/` (`cleanup-*`, `deleted-*.json`). These receipts contain infrastructure metadata, not database contents or secret values.
