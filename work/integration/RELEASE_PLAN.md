# Production release plan

Updated 11 November 2026 IST after recovering production on `7bdeb96`. Execution requires explicit authorization for the release SHA. Refresh the rollback IDs in the table from the live services immediately before each cutover.

## Mandatory exact-main CI gate

Every production release requires completed green full CI on the exact current main SHA, in addition to green PR CI. Record the normal merge SHA and wait for its push workflow to finish successfully. Run this gate before taking the production backup, changing production variables, uploading Railway, or promoting Vercel.

```powershell
python scripts/verify_release_gate.py --sha <full-main-sha> --output work/integration/main-ci-gate.json
if ($LASTEXITCODE -ne 0) { throw 'Production release gate failed' }
```

The gate checks the live GitHub main ref, the latest push workflow for that SHA, all backend/build jobs, all four browser shards and the isolated Research browser job. It rejects missing, queued, running, skipped or failed jobs. Save the run URL and gate receipt with the release evidence. Run the gate again immediately before Railway upload and Vercel promotion. If main advances, qualify the new SHA before continuing.

Hold automatic Vercel production alias assignment from the PR merge through production verification. A Git-created build may remain staged. Assign production traffic only after the exact-main gate passes and Railway reports the same SHA. Re-enable automatic production promotion only after every production check passes. The next release repeats this entire gate and hold procedure.

## State volume reserve and backup retention

Measure the mounted `/app/state` filesystem. Use its actual free bytes since the provider's volume usage display can lag. Create a fresh on-volume backup for the release after exact-main CI passes and record its path, file sizes, SHA-256 hashes, SQLite integrity verification and temporary SSH key removal in the rollback evidence. The backup refuses to start with less than 1.5 times the estimated full copy size, including SQLite WAL pages and filesystem overhead. It also refuses a copy projected to leave less than 20% free. Keep at most two verified release backup sets once the new set verifies. The latest verified set is always retained. Before pruning, record the older sets' file names, sizes and hashes in rollback history. Delete only the oldest verified sets after the newer two verify. Preserve unverified folders for investigation and leave other production files untouched.

Use `scripts/Invoke-ProductionVolume.ps1 -Action inventory -EvidenceDir <release-evidence>` to read free bytes and backup hashes. For a release, run the same script with `-Action backup -Name <dated-backup-name> -ExpectedSha <full-main-sha>`. Record the retention decision and file receipts first. Pass `-Action prune -PruneReceipt <receipt.json>` with the rollback history path under `history` and the exact oldest names and signatures under `signatures`. The prune operation rechecks both the candidates and the protected sets. Record free bytes before and after the backup and retention in the release evidence.

Use `scripts/Deploy-ProductionRailway.ps1 -ExpectedSha <full-main-sha> -Package <clean-backend-package> -EvidenceDir <release-evidence>` for the production upload. It requires green CI on that SHA, a verified matching backup with its temporary key removed, and at least 20% actual free space after backup. The backend reports `stateCapacity.freeBytes`, `totalBytes`, `freePercent` and the 20% reserve in `/api/health` and reports degraded below the reserve. Verify the mounted capacity again after startup. Keep mutable provider inputs, caches and outputs under `/app/state/live` so restart-time integrity checks still match the reviewed image. Confirm the frontend and backend artifact SHAs before starting the public smoke.

| Resource | Current rollback reference |
| --- | --- |
| Vercel project | `india-portwatch` in `flash2404s-projects` |
| Production alias | [india-portwatch.vercel.app](https://india-portwatch.vercel.app) |
| Vercel deployment | `dpl_CaL7pM197KbrJozKkm6YUchapfVQ`, ready at `7bdeb9690b7c501ef147ad36cf04f4f173900c0f` |
| Immutable Vercel URL | [Current deployment](https://india-portwatch-gj8z8uoeq-flash2404s-projects.vercel.app) |
| Railway project | `983b8896-688f-47ea-a693-6985e84ab03b` |
| Railway production environment and service | `7a940de4-9c13-411e-ad59-eb30ee42a9d4` and `128a61e8-a333-4c93-aa77-550d4e923495` |
| Railway production deployment | `e7eb1e73-6e54-487c-acf5-eee29eb57f22`, restored from the `7bdeb96` image |
| Railway production API | [india-portwatch-api.up.railway.app](https://india-portwatch-api.up.railway.app) |
| Isolated preview API | [live-now preview](https://api-live-now-live-now-preview-20261106.up.railway.app) |

## Before the cutover

1. Complete the mandatory exact-main CI gate and save its receipt. Review the CI baseline. Confirm the rollback deployment IDs again immediately before the release. Capture the current alias's frontend SHA and same-origin backend release identity separately. The current production frontend was released with an isolated API rewrite, so the old Vercel alias and old production Railway service can report different SHAs.
2. Prepare the two static rewrite rules below in `india-portwatch-terminal/vercel.json` as part of the future reviewed release change. Keep the production host match first. Use an exact hostname and verify any additional production aliases explicitly. Retain the Vercel framework and build configuration.

   ```json
   "rewrites": [
     {
       "source": "/api/:path*",
       "has": [{ "type": "host", "value": "india-portwatch.vercel.app" }],
       "destination": "https://india-portwatch-api.up.railway.app/api/:path*"
     },
     {
       "source": "/api/:path*",
      "destination": "https://api-live-now-live-now-preview-20261106.up.railway.app/api/:path*"
     }
   ]
   ```

   Prove the preview hostname still resolves to the isolated provider IDs. Check the production alias separately after cutover, since an immutable deployment hostname does not match the production host condition. [Vercel static rewrite configuration](https://vercel.com/docs/project-configuration/vercel-json#rewrites)

3. After authorization, use a normal merge and record its actual full SHA. Coordinate Vercel's production-domain assignment so the frontend is staged while Railway is built and verified. If automatic assignment cannot be gated safely, settle the release order with the operator before merging. Prepare the production Railway build from the exact merged Git archive or its reviewed Git integration, retaining the production volume and service settings.

## Configuration checks

- **Vercel** — `NITRO_PRESET=vercel`, `VITE_PORTWATCH_AUTH_MODE=production`, and `VITE_PORTWATCH_API_BASE` unset or same-origin `/api`. Confirm the project root is `india-portwatch-terminal` and preview build settings still route to the isolated service.
- **Railway identity and release** — `PORT=8000`, `PORTWATCH_IDENTITY_MODE=verified`, `PORTWATCH_RELEASE_SHA=<merge SHA>`, `PORTWATCH_RELEASE_ENVIRONMENT=production`, and `PORTWATCH_REQUIRE_RELEASE_MANIFEST` matching the reviewed archive manifest. Check Railway's injected environment, service, and deployment IDs against the selected production deployment.
- **Durable storage** — verify the existing volume mount, `PORTWATCH_STATE_DIR`, `PORTWATCH_AUTH_DB`, `PORTWATCH_FLEET_PROVIDER`, `PORTWATCH_PUBLIC_FEEDBACK_DB`, `PORTWATCH_CURRENT_ENVIRONMENT_DIR`, `PORTWATCH_WEATHER_FEEDBACK_DB`, and retained public artifact paths. Back up state before rollout and verify volume compatibility. A deployment rollback restores the deployment, while any volume recovery requires its own verified backup procedure.
- **Source and network policy** — confirm `PORTWATCH_CORS_REGEX`, `PORTWATCH_LICENCE_MODE`, `PORTWATCH_FRESHNESS_SCHEDULER`, `PORTWATCH_PUBLIC_PORT_AUTOREFRESH`, `PORTWATCH_PIPELINE_AUTOREFRESH`, `PORTWATCH_INTELLIGENCE_RECONCILIATION`, `PORTWATCH_WEATHER_RECONCILIATION`, and the approved provider toggles and credentials. Confirm a single writer for the production volume and keep credentials in the service's environment. Use the checked-in `.env.example` for optional provider and store names.

## Cutover and production smoke

1. Run the guarded production Railway upload described above. Confirm direct `/api/health` has matching artifact and release SHAs and that `status` and `service.status` both read `ok`. Check the durable stores, at least 20% free space, an advancing scheduler and no unresolved writes. Save the Railway receipt.
2. Run the mandatory exact-main gate again. Stage or select the same frontend SHA and manually promote it after Railway passes. Check the alias's Vercel deployment ID and SHA. On the alias, verify `/api/health` resolves to the verified **production** Railway service, environment, deployment and SHA. Recheck the preview alias is still isolated.
3. On [the production terminal](https://india-portwatch.vercel.app), confirm `/login` says **Data service: Reachable**, `/tour` renders 3D, and all four demo buttons open their workspaces. Use isolated demo sessions for the S10 → Company approval → Port review/issue → Vessel acknowledgement/acceptance → Port outcome → Company completed → Admin → Research benchmark path at 1366×768 and 1280×720. Confirm role screen packets, no unexpected browser or API errors, and record screenshots and the SHA receipt.
4. Run `qa/panel-smoke.mjs production` with a fresh verified receipt. Its production guard must identify the production service and environment listed above, the deployed Railway ID and the exact-main gate SHA. Save `data.status` and each source's status and observation or availability date in the report. Upstream freshness does not gate release. Confirm the UI preserves dates and freshness labels, including for expired forecasts and unavailable data.
5. Check the foreground split twin at ×60 and record the model clock and both panes' metrics. After every production check passes, restore automatic Vercel production alias assignment and save the final receipt. If any check fails, immediately restore both recorded deployments and verify both health endpoints.

## Rollback

- **Vercel** — restore the deployment captured immediately before cutover using `vercel rollback <id> --scope flash2404s-projects`. Verify the alias and its original same-origin API binding after rollback. [Vercel Instant Rollback](https://vercel.com/docs/instant-rollback)
- **Railway** — in the production environment, open the production service's Deployments tab and select **Rollback** on the recorded previous successful deployment. Confirm the deployment is eligible under retention and verify direct health and state. Use the backup and incident process if writes need recovery. If a legacy container restart rejects a changed image input, restore a clean container from the recorded immutable image and keep the attached volume. [Railway Deployment Actions](https://docs.railway.com/deployments/deployment-actions)
- If any production verification check fails, immediately restore both recorded deployments. Recheck the Vercel alias, the restored Railway image identity and both health endpoints. A Railway rollback creates a new deployment from the recorded image. Save that new ID and verify its image digest matches the rollback record.
