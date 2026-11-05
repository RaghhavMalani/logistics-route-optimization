# Persisted state audit

Compared `451492fafd6993c6c1573697465e9d202094a07b` with `2e43af315d75faa5d138830b274dc6406ef4df1c`. Release preparation `d46ef33` changes the frontend rewrite, smoke identity assertions and release documents.

The backup condition applies because the release introduces a durable snapshot family and its planned public-seed configuration can write public state on startup.

| Area | Finding and source |
| --- | --- |
| SQL schemas | No new migration, table, column, dropped table or schema-version transition was found. Ledger, advisories, public-port pilot, camera and cost-assumption store implementations are unchanged. `backend/app/auth_store.py` and `backend/app/services/demo_store.py` retain their SQL schema definitions and persisted encodings. Their environment reads now use `src/utils/settings.py`. |
| New durable JSON family | `src/portwatch_os/intelligence/capability_layers.py`, `_path()` and `collect()`, introduces `current_environment/capability_layers/{layer}-{scope}.json`, with status, receipt time, source, coverage, features and records. It writes through a temporary file and `os.replace`. Under the production Docker environment the root is `/app/state/current_environment`. This collector is an optional writer. The release API route reads retained snapshots and does not call it on startup. |
| Startup public seed | `backend/app/main.py`, `lifespan()`, calls `src/portwatch_os/learning/public_evidence_seed.py`, `import_configured_seed()`. That call and importer already exist at the main SHA. The existing production environment has no seed manifest configured. The planned release sets `PORTWATCH_PUBLIC_EVIDENCE_SEED_MANIFEST=/app/data/cache/preview_public_seed/manifest.json`, matching the verified isolated archive. Thus this deployment activates the importer. It can insert missing rows in the feedback, weather and public-port databases, fill resolved outcome fields on eligible open predictions, append an import audit and add public evidence files. Conflicting existing files are preserved. This is a release configuration change with durable effects. |
| Existing startup seeding | `src/portwatch_os/intelligence/current_environment.py` already copies missing packaged receipts and records missing packaged weather predictions on import. Its algorithm and locations are unchanged. The release replaces its environment reads with the shared settings object. |
| Simulated timelines | `src/portwatch_os/twin/simulation.py` adds optional in-memory presentation frames. The existing serialized result fields and the demo-session SQLite `world` representation remain compatible. This introduces no database migration or startup rewrite. |
| Other background writes | The freshness and weather/intelligence reconciliation workers retain their established store formats. Their settings access changes without a new startup record rewrite. |

Before deploying, back up production state on the mounted production volume. Return only filenames, lengths and SHA-256 metadata. Register, use and remove the temporary SSH key in the same guarded command. Restore state through the recorded offline startup command if recovery requires it.
