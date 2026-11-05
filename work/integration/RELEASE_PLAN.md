# Production release plan

Prepared 5 November 2026 IST. Execution requires explicit merge authorization. The production resources below were inspected read-only.

| Resource | Current rollback reference |
| --- | --- |
| Vercel project | `india-portwatch` in `flash2404s-projects` |
| Production alias | [india-portwatch.vercel.app](https://india-portwatch.vercel.app) |
| Vercel deployment | `dpl_7M6Jy4gZetTzM28ppd4AmbcS2s3a`, ready at `451492fafd6993c6c1573697465e9d202094a07b` |
| Immutable Vercel URL | [Current deployment](https://india-portwatch-9isxjt105-flash2404s-projects.vercel.app) |
| Railway project | `983b8896-688f-47ea-a693-6985e84ab03b` |
| Railway production environment and service | `7a940de4-9c13-411e-ad59-eb30ee42a9d4` and `128a61e8-a333-4c93-aa77-550d4e923495` |
| Railway production deployment | `734e4a9f-4a18-452b-81e3-4d74e8da3f24`, successful |
| Railway production API | [india-portwatch-api.up.railway.app](https://india-portwatch-api.up.railway.app) |
| Isolated preview API | [feature-integration preview](https://api-feature-integration-20261104-feature-integration-20261104.up.railway.app) |

## Before the cutover

1. Review the CI baseline and release gates. Confirm the rollback deployment IDs again immediately before the release. Capture the current alias's frontend SHA and same-origin backend release identity separately. The current production frontend was released with an isolated API rewrite, so the old Vercel alias and old production Railway service can report different SHAs.
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

1. Deploy the **production Railway service** at the recorded merge SHA. Confirm the deployment is healthy at its direct `/api/health`, that its artifact and release SHA match, and that production's volume and required data are ready. Save the Railway receipt.
2. Deploy the same frontend SHA to production and assign the production alias after Railway passes. Check the alias's Vercel deployment ID and SHA. On the alias, verify `/api/health` resolves to the verified **production** Railway service, environment, deployment and SHA. Recheck the preview alias is still isolated.
3. On [the production terminal](https://india-portwatch.vercel.app), confirm `/login` says **Data service: Reachable**, `/tour` renders 3D, and all four demo buttons open their workspaces. Use isolated demo sessions for the S10 → Company approval → Port review/issue → Vessel acknowledgement/acceptance → Port outcome → Company completed → Admin → Research benchmark path at 1366×768 and 1280×720. Confirm role screen packets, no unexpected browser or API errors, and record screenshots and the SHA receipt.
4. Before running `qa/panel-smoke.mjs production`, review its hosted receipt guard. The old production path still expects the former isolated service and environment IDs. At release time, bind it to the exact production service and environment listed above and the new production deployment ID, while retaining the SHA and host assertions.

## Rollback

- **Vercel** — restore the deployment captured immediately before cutover using `vercel rollback <id> --scope flash2404s-projects`. The current reference is `dpl_7M6Jy4gZetTzM28ppd4AmbcS2s3a`. Verify the alias and its original same-origin API binding after rollback. [Vercel Instant Rollback](https://vercel.com/docs/instant-rollback)
- **Railway** — in the production environment, open the production service's Deployments tab and select **Rollback** on the recorded previous successful deployment. The current reference is `734e4a9f-4a18-452b-81e3-4d74e8da3f24`. Confirm the deployment is eligible under retention and verify direct health and state. Use the backup and incident process if writes need recovery. [Railway Deployment Actions](https://docs.railway.com/deployments/deployment-actions)
- If the alias regression starts after cutover, restore the previously working alias immediately, then roll back Railway if its direct health, data, or operational checks fail. Recheck both old bindings and repeat a minimal demo smoke.
