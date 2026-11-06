# Live freshness work log

Base: main `7bdeb9690b7c501ef147ad36cf04f4f173900c0f`. Work is on `feat/live-now`; production changes require a separate explicit merge authorization and exact-main green CI.

1. Diagnosis committed as `f28653b`. Read-only production health, provenance, settings and logs establish the profile mismatch, swallowed activity fetch failures and false-green health condition.
2. Reused the existing retained-source branch with a normal merge (`72edbad`). The single Vessel UI conflict kept main's camera-padding annotation and the source branch's valid block wrapper/source health content. No history was rewritten.
3. Worker hardening: durable seven-day attempt journal and saved last-good/backoff state; secret-redacted failures; per-source bounded retry cycles and explicit circuit state; round-robin dispatch; kernel-held shared-volume owner lock, plus SQLite trial locks; queued admin refresh requests; only the owning scheduler starts the ancillary collectors. Current Open-Meteo/GDACS jobs can run in an eligible noncommercial deployment independently of the optional research bundle. A strict activity fetch fails instead of claiming a new forecast from a stale CSV. Incremental activity refresh preserves older history and writes CSVs atomically. API/export paths can share an explicit persistent data/cache/output root.

Validation for this item: 39 freshness, public-collector and snapshot tests passed, one existing skip. New regressions cover journal/backoff recovery across restart, preserved last-good data after failed probes, exclusive ownership/release, enqueue without provider I/O, credential redaction, strict fetch failure retaining the original CSV and current-weather eligibility without research-profile flags. Tests used workspace temporary folders and the project's PDF parser dependency; assertions and original test deadlines were retained.

The retained-only marine/AIS adapters behind the world's `fetch` method were inspected: those adapters read retained state and do not perform provider HTTP calls on the request path. The source diagnosis's route audit therefore identifies the refresh queue boundary to preserve, not a confirmed HTTP leak from that read adapter.

Outstanding: apply shared freshness truth to health/read responses and UI, SSE pulse, real preview refresh and evidence, licensed candidate collectors and actual 48-hour trial decisions. BigQuery and AIS remain awaiting project/cap/credentials; no paid queries or AIS subscriptions have been started.
