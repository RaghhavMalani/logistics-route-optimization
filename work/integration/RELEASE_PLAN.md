# Production release plan

Updated after the verified 6 November 2026 IST release. Execution of a future release requires explicit merge authorization and the exact-main CI gate below. Current production is `7bdeb9690b7c501ef147ad36cf04f4f173900c0f`; Vercel `dpl_CaL7pM197KbrJozKkm6YUchapfVQ` and Railway `082b734f-9efb-4348-b7f9-16cb585c640e`. Both viewport smokes and the foreground ×60 split twin passed with zero recorded errors. Automatic promotion was re-enabled only after those checks. The completed release's prior rollback targets and fresh on-volume backup are in `ROLLBACK.md`; `RESEARCH_RELEASE_STATUS.md` records its final receipts.

## Mandatory exact-main CI gate

Every production release requires completed green full CI on the exact current main SHA, in addition to green PR CI. Record the normal merge SHA and wait for its push workflow to finish successfully. Run this gate before taking the production backup, changing production variables, uploading Railway, or promoting Vercel.

```powershell
python scripts/verify_release_gate.py --sha <full-main-sha> --output work/integration/main-ci-gate.json
if ($LASTEXITCODE -ne 0) { throw 'Production release gate failed' }
```

The gate checks the live GitHub main ref, the latest push workflow for that SHA, all backend/build jobs, all four browser shards and the isolated Research browser job. It rejects missing, queued, running, skipped or failed jobs. Save the run URL and gate receipt with the release evidence. Run the gate again immediately before Railway upload and Vercel promotion. If main advances, qualify the new SHA before continuing.

Disable automatic Vercel production alias assignment BEFORE merging the next release PR, and hold it through exact-main CI and production verification. Re-enabling it after one successful release does not waive this gate for the next merge. A Git-created build may remain staged. Assign production traffic only after the exact-main gate passes and Railway reports the same SHA. Re-enable automatic production promotion only after every production check passes. The next release repeats this entire gate and hold procedure.

| Resource | Current rollback reference |
| --- | --- |
| Vercel project | `india-portwatch` in `flash2404s-projects` |
| Production alias | [india-portwatch.vercel.app](https://india-portwatch.vercel.app) |
| Vercel deployment | `dpl_CaL7pM197KbrJozKkm6YUchapfVQ`, ready at `7bdeb9690b7c501ef147ad36cf04f4f173900c0f` |
| Immutable Vercel URL | [Current deployment](https://india-portwatch-gj8z8uoeq-flash2404s-projects.vercel.app) |
| Railway project | `983b8896-688f-47ea-a693-6985e84ab03b` |
| Railway production environment and service | `7a940de4-9c13-411e-ad59-eb30ee42a9d4` and `128a61e8-a333-4c93-aa77-550d4e923495` |
| Railway production deployment | `082b734f-9efb-4348-b7f9-16cb585c640e`, successful |
| Railway production API | [india-portwatch-api.up.railway.app](https://india-portwatch-api.up.railway.app) |
| Isolated preview API | [feature-integration preview](https://api-feature-integration-20261104-feature-integration-20261104.up.railway.app) |

## Before the cutover

1. Complete the mandatory exact-main CI gate and save its receipt. Review the CI baseline. Confirm fresh rollback deployment IDs again immediately before the release. Capture the current alias's frontend SHA and same-origin backend release identity separately. The current production alias uses the production API rewrite; older rollback targets may retain an isolated API rewrite and depend on that older service. Preserve those dependencies through the rollback window. Check free volume capacity before the fresh state backup. Production's volume is now 1,024 MB; do not delete state or accepted backups to bypass a failed backup gate.
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
       "destination": "https://api-feature-integration-20261104-feature-integration-20261104.up.railway.app/api/:path*"
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

1. Run the mandatory exact-main gate again. Deploy the **production Railway service** at that exact SHA. Confirm the deployment is healthy at its direct `/api/health`, that its artifact and release SHA match, and that production's volume and required data are ready. Save the Railway receipt.
2. Run the mandatory exact-main gate again. Stage or select the same frontend SHA and manually promote it after Railway passes. Check the alias's Vercel deployment ID and SHA. On the alias, verify `/api/health` resolves to the verified **production** Railway service, environment, deployment and SHA. Recheck the preview alias is still isolated.
3. On [the production terminal](https://india-portwatch.vercel.app), confirm `/login` says **Data service: Reachable**, `/tour` renders 3D, and all four demo buttons open their workspaces. Use isolated demo sessions for the S10 → Company approval → Port review/issue → Vessel acknowledgement/acceptance → Port outcome → Company completed → Admin → Research benchmark path at 1366×768 and 1280×720. Confirm role screen packets, no unexpected browser or API errors, and record screenshots and the SHA receipt.
4. Run `qa/panel-smoke.mjs production` with a fresh verified receipt. Its production guard must identify the production service and environment listed above, the deployed Railway ID and the exact-main gate SHA. Retain its host, source-artifact and release-identity assertions.
5. Check the foreground split twin at ×60 and record the model clock and both panes' metrics. After every production check passes, restore automatic Vercel production alias assignment and save the final receipt. If any check fails, immediately restore both recorded deployments and verify both health endpoints.

## Rollback

- **Vercel** — restore the deployment captured immediately before the future cutover using `vercel rollback <id> --scope flash2404s-projects`. Current production to record for a future release is `dpl_CaL7pM197KbrJozKkm6YUchapfVQ`. To undo the completed 6 November release itself, use its separately recorded prior ID in `ROLLBACK.md`. Verify the alias and its same-origin API binding after rollback. [Vercel Instant Rollback](https://vercel.com/docs/instant-rollback)
- **Railway** — in the production environment, open the production service's Deployments tab and select **Rollback** on the freshly recorded previous successful deployment. Current production to record for a future release is `082b734f-9efb-4348-b7f9-16cb585c640e`. The completed release's prior image is separately recorded in `ROLLBACK.md`. Confirm eligibility under retention and verify direct health and state. Use the backup and incident process if writes need recovery. [Railway Deployment Actions](https://docs.railway.com/deployments/deployment-actions)
- If any production verification check fails, immediately restore both recorded deployments. Recheck the Vercel alias, the restored Railway image identity and both health endpoints. A Railway rollback creates a new deployment from the recorded image. Save that new ID and verify its image digest matches the rollback record.
