# Marine extension and ensemble — private trials in progress

Terms: Open-Meteo free service is noncommercial; data is CC BY 4.0 with attribution. Separate product entries record the Marine and ensemble documentation. Existing surface and wave forecasts have been refreshed for all 13 registered ports; these extended variables remain separate unpublished trials.

The fixed 48-hour window is in README.md. Ensemble's first successful response set was retained at 6 Nov 18:05:16 UTC. Marine initially failed because some near-port current fields were null. The corrected collector retains those nulls and per-variable coverage alongside usable wave/swell values; missing port responses are counted rather than invented. Each request is bounded to three forecast days and collection to two concurrent locations per product, on a six-hour cadence with retries/backoff/circuit breaker.

Provider issue times are unavailable. Receipt availability and forecast valid times are separate; receipt age is not observation lag. Ensemble member coverage is measured, and no uncertainty correction is applied to decision scores. Adoption/coverage/lag decision remains pending the actual 48-hour report. Raw response summaries and attempt evidence remain on the preview snapshot store.
