# Research release rollback record

Recorded 2026-11-06T09:41:40.338784+00:00. Exact-main CI passed before any production write.

- Qualified main: `7bdeb9690b7c501ef147ad36cf04f4f173900c0f`.
- CI: https://github.com/RaghhavMalani/logistics-route-optimization/actions/runs/42025923232 (all eight jobs green).
- Previous production Vercel: `dpl_7M6Jy4gZetTzM28ppd4AmbcS2s3a` at `https://india-portwatch-9isxjt105-flash2404s-projects.vercel.app`.
- Previous frontend SHA: `451492fafd6993c6c1573697465e9d202094a07b`.
- Previous production Railway: `573c7252-fb5c-4114-9421-7aac1203fbc2` (SUCCESS, rollback eligible).
- Railway image digest: `sha256:bdc94a60379ef2ead4bfbd678eff865c6dc20d1da12bbfb61a84d71fb4148155`.
- Railway service `128a61e8-a333-4c93-aa77-550d4e923495`, environment `7a940de4-9c13-411e-ad59-eb30ee42a9d4`, project `983b8896-688f-47ea-a693-6985e84ab03b`.
- Volume `e8138731-4d1a-408f-b453-7343c2adbe57`, instance `efeae9e5-c344-48de-beda-c6f3d96e3572`, mounted at `/app/state`.
- Main URL: https://india-portwatch.vercel.app; direct production API: https://india-portwatch-api.up.railway.app.
- Automatic Vercel production promotion is held (`autoAssignCustomDomains=false`) until production verification passes.

Run BOTH commands immediately if a production check fails:

```powershell
vercel rollback dpl_7M6Jy4gZetTzM28ppd4AmbcS2s3a --scope flash2404s-projects --yes
railway api 'mutation { deploymentRollback(id: "573c7252-fb5c-4114-9421-7aac1203fbc2") }'
```

Verify the old Vercel alias and restored Railway image digest. Railway creates a new deployment from the recorded image. Restore release-only environment values with `skipDeploys=true` from the pre-release receipt; preserve the volume. The old Vercel deployment retains its original isolated API rewrite.

Fresh on-volume backup pending; do not deploy until the metadata and key-removal receipt are recorded.

