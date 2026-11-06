# Live-now preview evidence

All runtime receipts are under `D:/LogisticOptimization-_Capstone_168/work/live-evidence-20261106/`. Deployment packages contain Git archive bytes and qualified public seeds; the ignored local `.env`, visitor stores, operational databases and backups are excluded.

- `production-health-before.json`, `production-provenance-before.json`: read-only production baseline, main 7bdeb96, origin 2 October and expired horizon. Production is unchanged by this feature.
- `before/`: two-size screenshots of the preserved pre-change fallback, with JSON receipts naming its origin. Its old weather cursor says NOW at 23 October. This visual baseline is the fallback, not a claim that production's retained origin was 23 October.
- `after/`: login Environment, Data now, live pulse, Company and Vessel Bridge/timeline at 1366×768 and 1280×720; JSON receipts include origin and browser errors.
- `hosted-smoke/`, `hosted-smoke.log`: S10 → Company → Port issue → Vessel acknowledge/accept → outcome → Company outcome → Admin → Research at both sizes. Expected upstream degradation is explicit; durable stores, SHA binding and every workflow assertion still have to pass.
- `binding.json`, `package-manifest.json` in the clean preview package: Vercel/Railway IDs, source fingerprints and exact release SHA. Both services are isolated previews.
- `sse-receipt.json`: two source-age frames about 15 seconds apart on one existing handoff stream, with no credentials retained.
- `preview-health-final.json`: retained core source status, error/rate history and private trial coverage. New candidate observations remain unpublished.
- `backend-full-3.log`/`.xml`: 1,798 passing backend tests, two baseline skips. Later AIS permission/cleanup and freshness regressions have separate targeted runs and hosted CI. `browser-freshness-final.log`: five role/login/Sources fixed-clock regressions. `build-final.log`: production build. The PR checks record full hosted CI at the branch SHA.

Repository-wide lint has pre-existing style/type findings, dominated locally by CRLF formatting; it is not reported as green. The new shared-stream/pulse code passes substantive ESLint checks. The original scheduler deadline was preserved and its Windows throttling cause corrected.

Trials are **in progress**, ending 8 Nov 18:00:34 UTC. BigQuery awaits billing project/credentials/cap; AIS and IMD await reuse permission. IMF refresh currently returns quota errors, so congestion remains historical and health degraded. See the per-source reports for measured coverage and limitations. No adoption, production refresh or decision-policy change is claimed.
