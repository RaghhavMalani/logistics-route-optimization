# Research release status: held before deployment

The Research fix is merged through [PR #11](https://github.com/RaghhavMalani/logistics-route-optimization/pull/11). All eight PR CI jobs passed. Main remains `7bdeb9690b7c501ef147ad36cf04f4f173900c0f`; all eight jobs on its [push CI run](https://github.com/RaghhavMalani/logistics-route-optimization/actions/runs/42025923232) passed before the production backup was attempted.

The release is held because the production `/app/state` volume has zero free bytes at its 500 MB capacity. Three fresh-backup attempts failed before acceptance. Their incomplete backup folders were removed by guarded cleanup. Each temporary SSH key was removed and API enumeration confirmed its absence. No accepted fresh backup exists. Existing state and the previous accepted backup were retained on-volume.

No new Railway deployment, release-variable change, Vercel promotion or automatic-promotion re-enable was performed. The production alias still serves Vercel `dpl_7M6Jy4gZetTzM28ppd4AmbcS2s3a`, frontend SHA `451492fafd6993c6c1573697465e9d202094a07b`. The production Railway rollback deployment remains `923268ac-7170-44f3-9f03-9dfa79411418`. Its old health payload does not identify an application SHA, so a production backend SHA is not claimed.

On 6 November 2026 IST, the old production API reported `status=degraded`: `/app/state/portwatch_ledger.db` and `/app/state/portwatch_advisories.db` could not open with `disk I/O error`. Railway still reported a 500 MB volume, approximately 495.87 MB used. The operator was asked to increase the volume to at least 1 GB without deleting state or backups. The authenticated CLI exposes no resize operation; the available dashboard session was not signed in.

The local rehearsal stack was restored using the existing detached launcher. `http://127.0.0.1:4264/login` returned 200, its backend returned `status=ok`, and both reported the existing rehearsal SHA `e33068c58183b8adee0d6ce6b86f60997337d1ad`.

After capacity is increased: verify current main and the exact-main gate again; refresh both rollback IDs; run the guarded fresh on-volume backup; verify all file hashes and key removal; deploy production Railway at the qualified main SHA; manually promote the matching staged Vercel deployment; run both production smoke sizes and the foreground ×60 split twin. Roll back both immediately on any production verification failure. Re-enable automatic promotion only after all checks pass.

Rollback commands for the currently recorded targets:

```powershell
vercel rollback dpl_7M6Jy4gZetTzM28ppd4AmbcS2s3a --scope flash2404s-projects --yes
railway api 'mutation { deploymentRollback(id: "923268ac-7170-44f3-9f03-9dfa79411418") }'
```

Full diagnosis: `work/integration/RESEARCH_FAILURES.md`. Rollback details: `work/integration/ROLLBACK.md`. Raw evidence: `work/integration/research-failures-20261105/` in the shared workspace.
