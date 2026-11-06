# Railway cleanup and storage repair

Inspected 6 November 2026 IST using authenticated CLI/API reads. Project: `india-portwatch-api` (`983b8896-688f-47ea-a693-6985e84ab03b`).

The final authorized removal of the retired services and empty environments is recorded in `RAILWAY_CLEANUP_FINAL.md`. The initial repair below preserved all data; the later cleanup also retained every volume and backup.

## Completed without deleting data

- Imported production infrastructure with all environment values represented as `preserve()`. The baseline plan had zero changes. The reviewed resize plan contained exactly one safe update: `api-volume` from 500 MB to 1,024 MB. No service, credential, replica, source, mount or region changes were planned or applied.
- Railway applied that resize. The volume remained mounted at `/app/state`; health recovered from degraded/disk I/O errors to `status=ok`, with durable stores healthy. Railway restarted the same prior application image as deployment `573c7252-fb5c-4114-9421-7aac1203fbc2`; image digest remained `sha256:bdc94a60379ef2ead4bfbd678eff865c6dc20d1da12bbfb61a84d71fb4148155`. This current healthy deployment was recorded as the new rollback target before release upload.
- Initially stopped the superseded role-home performance preview deployment `754535f2-2781-46cb-9ec3-318799123d03` and twin preview deployment `74dee4d1-0f15-4c62-b397-d5ef38772d35`. API/status receipts confirmed `deploymentStopped=true` and instances `STOPPED`. Following explicit authorization, both service objects and their now-empty environments were removed; see the final cleanup record.
- The fresh backup then completed on-volume at `/app/state/.release-backups/20261106-151145-research-7bdeb969`: 2,391 files and 42 SQLite databases, integrity checked. File names, sizes, hashes, temporary-key absence and the exact restore command are recorded in `ROLLBACK.md`. No backup bytes were copied off the production volume.

## Resource inventory and retention

| Environment | Service | Volume | Disposition |
| --- | --- | --- | --- |
| `production` | `api` | `api-volume`, now 1,024 MB | Keep: production service and all state/backups |
| `feature-integration-20261104` | `api-feature-integration-20261104` | No dedicated volume | Keep: verified isolated preview fallback |
| `integrated-preview-20261102` | `api-integrated-20261102` | 5,000 MB capacity; about 1,552 MB used | Keep through rollback window: the recorded old Vercel production deployment rewrites here |
| `role-home-perf-preview-20261104` | `api-home-perf-preview` | None | Removed after explicit final cleanup authorization |
| `twin-preview-20261104` | `api-twin-preview-20261104` | None | Removed after explicit final cleanup authorization |
| `restored-preview` | `api-restored-preview` | 500 MB capacity; about 146.8 MB used | Already inactive; preserve historical volume pending an explicit retention decision |
| `sar-data` | No service | None | Confirmed empty and removed |

Stopping the two experiment deployments reduces unnecessary running workloads. Deleting another environment's volume would not free space inside production's separate volume. All volumes, accepted backups, archived evidence, current records and secrets were retained.

## Production storage findings before repair

The filesystem reported zero available bytes. The largest groups were the accepted release backup (145.2 MB logical), importer safety backups (54.1 MB), weather forecast database (44.0 MB), environment archive (34.7 MB logical), collection-run evidence (25.9 MB logical) and weather feedback JSON (22.0 MB). A 15.7 MB unfinished weather `.tmp` file was also present. None was deleted as a shortcut to deployment.

Future retention work should distinguish accepted rollback snapshots, importer restore points, source evidence and reconstructible exports. The temporary weather file needs an age/open-writer check before removal. Existing producer retention must be bounded to avoid filling the enlarged disk again; this is separate from the qualified release and must not silently discard decision evidence.

Raw inventory and SSH metadata receipts: `work/integration/research-failures-20261105/`. Infrastructure baseline, pinned resize plan/result and stopped-instance receipts: `work/railway-operations-20261106/`. The SDK's Windows launcher/version check was satisfied by calling the already-installed Railway 5.57.4 native executable; the SDK and compatibility check were not modified.
