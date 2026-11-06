# Research release status: LIVE

Verified 6 November 2026 IST. Production frontend and production Railway both report `7bdeb9690b7c501ef147ad36cf04f4f173900c0f`.

| Receipt | Value |
| --- | --- |
| Main terminal | https://india-portwatch.vercel.app |
| Production API | https://india-portwatch-api.up.railway.app |
| Fix PR | https://github.com/RaghhavMalani/logistics-route-optimization/pull/11 |
| Green PR CI | https://github.com/RaghhavMalani/logistics-route-optimization/actions/runs/42024365020 |
| Green exact-main CI | https://github.com/RaghhavMalani/logistics-route-optimization/actions/runs/42025923232 |
| Production Vercel | `dpl_CaL7pM197KbrJozKkm6YUchapfVQ` |
| Production Railway | `082b734f-9efb-4348-b7f9-16cb585c640e` |
| Automatic Vercel promotion | Restored to `true` after all production checks passed |

The original test failures were renderer contention and deadline overruns, not evidence dates or startup imports. The fix retained original assertions and timeouts, isolated Research CI rendering, explicitly settled unrelated traffic motion and added an assertion that corrupt originals never trigger a download. Each affected test passed ten repeated checks after the fix. PR CI was green before the normal merge; all eight jobs on the resulting main push CI were green before production writes. Exact-main gate receipts were saved before backup, Railway upload, Vercel promotion and finalization. The backend CI job reported 1,772 passed and two existing skips.

The full production path passed at 1366×768 and 1280×720: reachable login, 3D tour, S10, Company approval, Port review/issue, Vessel acknowledgement/acceptance, Port outcome, Company completion, Admin, Research benchmark and all four direct demo entries. Both JSON reports have empty error arrays. The foreground ×60 split twin advanced from +04:00 to +24:00; all 22 samples were foreground, both metric clocks reached hour 24, both displayed metrics changed and its errors array is empty. The comparison capture and 20-second MP4 are retained.

The storage blocker was repaired by a reviewed single safe resize from 500 MB to 1,024 MB. No state, old backups, archives or credentials were deleted. The fresh accepted backup is `/app/state/.release-backups/20261106-151145-research-7bdeb969`: 2,391 files and 42 SQLite databases with integrity checks. All backup bytes stayed on-volume. `ROLLBACK.md` contains every name, size and SHA-256, confirmed key removal and the exact guarded restore command.

The superseded performance and twin preview deployments are stopped, with instances confirmed `STOPPED`; their configurations and history remain. The old November 2 preview API is retained because the previous Vercel rollback target rewrites there. The verified isolated fallback remains healthy at SHA `2e43af315d75faa5d138830b274dc6406ef4df1c` and service `b051a10f-6691-4c7a-9eff-490eb217752e`. Local login remains running at http://127.0.0.1:4264/login on the existing rehearsal checkout.

Immediate rollback for this release restores BOTH recorded prior images:

```powershell
vercel rollback dpl_7M6Jy4gZetTzM28ppd4AmbcS2s3a --scope flash2404s-projects --yes
railway api 'mutation { deploymentRollback(id: "573c7252-fb5c-4114-9421-7aac1203fbc2") }'
```

The Railway target is the healthy prior image after volume resizing, whose digest matches the earlier restored deployment. A rollback creates a new deployment from that image. Restore the four release-only environment values from `release-vars-before.json` with `skipDeploys=true`, and verify both endpoints and image identities. Volume restoration, if required, follows the separately verified maintenance start command in `ROLLBACK.md` before application workers start. Do not force-push or rewrite main.

Evidence root: `D:/LogisticOptimization-_Capstone_168/work/integration/research-failures-20261105/`. Receipts include `FINAL_RELEASE.json`, all exact-main CI gates, production binding, two viewport reports/screenshots, `production-twin/capture.json`, `production-twin/twin-comparison-20s.mp4`, key-removal confirmation and backup metadata. Infrastructure repair/cleanup receipts are in `work/railway-operations-20261106/`.
