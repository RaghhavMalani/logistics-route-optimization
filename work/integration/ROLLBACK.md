# Production rollback record

Recorded 5 November 2026 IST before release changes. Authorized release starts from `feat/integrated` at `2e43af315d75faa5d138830b274dc6406ef4df1c`.

| Resource | Recorded value |
| --- | --- |
| Main SHA | `451492fafd6993c6c1573697465e9d202094a07b` |
| Vercel project and scope | `india-portwatch`, `flash2404s-projects` |
| Production alias | `https://india-portwatch.vercel.app` |
| Vercel rollback deployment | `dpl_7M6Jy4gZetTzM28ppd4AmbcS2s3a` |
| Vercel immutable URL | `https://india-portwatch-9isxjt105-flash2404s-projects.vercel.app` |
| Railway project | `983b8896-688f-47ea-a693-6985e84ab03b` |
| Railway production environment | `7a940de4-9c13-411e-ad59-eb30ee42a9d4` |
| Railway production service | `128a61e8-a333-4c93-aa77-550d4e923495` |
| Railway rollback deployment | `734e4a9f-4a18-452b-81e3-4d74e8da3f24` |
| Railway production API | `https://india-portwatch-api.up.railway.app` |
| Persistent volume | `e8138731-4d1a-408f-b453-7343c2adbe57` mounted at `/app/state` |
| Volume instance | `efeae9e5-c344-48de-beda-c6f3d96e3572` |
| Vercel automatic alias assignment before release | `true` |

Run both restoration commands immediately if a production verification check fails.

```powershell
vercel rollback dpl_7M6Jy4gZetTzM28ppd4AmbcS2s3a --scope flash2404s-projects --yes
railway api 'mutation { deploymentRollback(id: "734e4a9f-4a18-452b-81e3-4d74e8da3f24") }'
```

The Railway mutation was verified against the current authenticated API schema. It identifies the recorded production deployment explicitly. The Vercel command restores the production aliases to the recorded deployment. Confirm both deployment identities and health after restoring them. The old alias uses its original isolated backend rewrite, recorded separately from the direct production API in `release-20261105/alias-health-before.json` and `release-20261105/railway-health-before.json`.

Restore any release environment variables from the private pre-release snapshot after rollback. Preserve the production volume. Retain the pre-release volume backup for state recovery if needed. Recheck automatic Vercel alias assignment against the recorded value after the release or rollback.

The Git history remains available for an ordinary follow-up revert commit if needed. A merge revert uses `git revert -m 1 <merge-sha>`.
