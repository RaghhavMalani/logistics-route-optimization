# India port evidence capability: local validation and release status

18 October 2026. Development continues from published `c854e60b4404c0763818f49a780bc2764c668450` on `feat/portwatch-restored-intelligence`. The eight protected role/twin files remain equal to `e906f6a` after line-ending normalization. Production promotion has not occurred.

## What this version supports

The existing Global Eye intelligence panel now exposes retained official public-port reports and separately aged IMF aggregate activity. A Company user selects an exact publisher record and an owned voyage, explicitly confirms candidate-port context, and creates a durable inspection task. Company or the task's Port authority can append an attributed context review. The original task, operational episode, source receipt and prior evidence remain frozen and inspectable. Vessel and Admin can inspect within their existing visitor scope.

`CONTEXT_REVIEWED` answers the bounded question of whether this published port context was inspected. It does not verify source accuracy, associate a demo hull with a real vessel, observe execution, or establish waiting, schedule, fuel, cost or safety benefits. News verification remains pending when its separate question has not been answered. No numerical advisory is created from these records alone. See [pilot scope and source semantics](INDIA_OPERATIONAL_EVIDENCE_PILOT.md) and [additive presentation/API contracts](team/INTELLIGENCE_CONTRACT_ADDITIONS.md).

The existing Weather panel can inspect a real matched forecast and later ERA5 reanalysis, alongside the separate five-day archive. Both source responses must remain hash-checked before a matched case appears. Independent target counts remain distinct from repeated forecast snapshots. Correction is still **COLLECTING** and is not consumed by the subsequent daily watch or hourly approach decisions. Both rejected model candidates remain **REJECTED**. [Weather evidence details](WEATHER_MATCHED_EVIDENCE_20261017.md).

OCEANS-X remains an inactive, document-qualified API candidate. Its anonymous arrival request returned 401. Authorized product subscription, private backend configuration, authenticated payload and operational-semantic review remain necessary. [Qualification and exact dependency](OCEANS_X_QUALIFICATION.md).

## Actual October 18 local validation

The reviewed backend package ran locally with separate durable state, public-source collectors and automatic weather reconciliation. It did not use production sessions or state. The frontend ran at `http://127.0.0.1:4199/login`, against `http://127.0.0.1:8798/api`.

All four retained public products were downloaded and their original hashes checked:

| Product | Printed/source date | Rows | Age at inspection |
| --- | --- | ---: | --- |
| Paradip traffic report | October 16 | 67 | STALE, 2 days |
| Chennai vessel position | October 16 | 19 | STALE, 2 days |
| Chennai expected arrivals | October 16 | 47 | STALE, 2 days |
| IMF JNPA daily aggregate | October 9 | 32 | STALE, 9 days |

A successful October 18 receipt did not make these observations current. The October 17 pilot's 33-row IMF response remains a different retained receipt; the bounded query's rolling date range explains why row counts must not be treated as independent outcomes. Current PDFs, publication/observation instants and missing vessel identifiers are presented with their actual limits. There is no claim of fresh individual AIS or official all-fast coverage.

A genuine expected-arrival row for **O7 ALSACE**, dimensions 145.56 × 18.25 m, published ETA `2026-10-18T12:30:00Z`, supported a context-inspection task and disposition. The selected visitor voyage remained fictional and unassociated with this real vessel. API checks verified original task preservation, stable retry IDs, role-owned writes, cross-visitor rejection and all four original role contracts. The Company browser independently completed a Chennai context review inside the original Global Eye panel.

An actual local backend process restart preserved the immutable task, one disposition, operational episode, original evidence and visitor isolation. The review added **zero real resolved operational targets**. A crash between ledger append and world-pointer update is also covered by regression tests.

The local matched weather case was a daily UTC gust forecast of **13.4 kn**, later ERA5 **15.6 kn**, raw error **−2.2 kn**, with 24 matched hourly bins in each original. Forecast SHA-256: `df4f506f3f6899cd31e21b4199d2dd05dd70ff6b19bed9ebb415643856dbf13e`; outcome SHA-256: `9563350d4acbf5839afd8e30993de7cff04a62e1da2ee9544d77230c32f7a66c`. The local archive had 78 independent resolved weather targets at that snapshot. This separately seeded local archive must not be conflated with the October 17 hosted snapshot of 39 targets. The retained five-day October 15 target remains pending; earlier missing-original claims remain excluded.

Validation comprised 182 passing existing regression cases, followed by 78 passing final targeted cases, including the revised registry assertion: **260 distinct passing tests**. TypeScript, focused ESLint and the Vercel frontend build passed. Provider failures, malformed responses, raw-original retention, revisions, future availability, units, stale context, retries, interrupted writes, restart and visitor isolation are covered. The browser verified Company/Global Eye maps, original traffic/weather timeline controls and the context review. At 390 × 844 the page width was 390 px and the dialogue content width equalled its 357 px scroll width; temporary viewport overrides were reset. Hosted desktop/mobile and hosted restart checks have not passed for this update.

Ignored validation artifacts are under `work/operational-pilot-20261017/`: `final-local-validation.json`, `local-api-validation.json`, `local-api-recovery.json`, source snapshots and browser captures. Private disposable-session recovery payloads remain separately ignored. Public originals, databases, caches, captures and unrelated local CSV refreshes are excluded from the source commit.

## Hosted release is blocked

The frontend-only Vercel preview built successfully: deployment `dpl_CCkbE73XPza9dVdpaVoUCtDgRsH5`, `https://india-portwatch-14m9uwqpn-flash2404s-projects.vercel.app/login`. **This is not a validated working capability preview:** it still targets the existing hosted backend, which has not received this update.

Railway rejected the backend upload with **“Your trial has expired. Please select a plan to continue using Railway.”** No replacement host, subscription purchase, production promotion or production-state migration was performed. The account owner must restore access to the existing Railway project before deployment can continue. The reviewed backend package retains the existing `/app/state` volume configuration and uses a manifest of reviewed code and public seeds, without visitor/operator databases.

After access is restored, deploy the reviewed package to `api-restored-preview` / `restored-preview`, verify real hosted receipts and failure labels, repeat the source → voyage context → disposition interaction and matched-weather inspection, then perform hosted restart/isolation and browser checks. Preserve production until those checks pass. Local validation and a ready frontend build are not substitutes for those checks.
