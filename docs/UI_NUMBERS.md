# Workspace scores

The port pressure index uses **0–100 points**, with **50 at that port’s own historical baseline**. It compares trailing seven-day vessel calls with the port’s historical calls. [Source definition](DATA_AUDIT.md#observed-port-state)

| Pressure points | Display band |
|---|---|
| Below 40 | Quiet |
| 40 through 60 | Normal |
| Above 60 through 75 | Busy |
| Above 75 | Severe |

The display bands come from `src/lib/score-bands.ts` in the terminal. Forecast ranges use the band at each endpoint. Operational alerts retain their published thresholds. A chart beside an observed score uses the observations in the seven calendar days through the latest retained observation. The date appears in its tooltip. A historical chart requires at least two observations. A forecast band displays the retained forecast endpoints, and exposure displays the available snapshot score.

Exposure uses a **0–1 index** with Low below 0.30, Medium from 0.30 up to 0.55, and High from 0.55. Severity, source confidence, time decay, and route or port adjustments feed that score.

## Forecast clocks and current weather

“Checked” is the time of the last successful, validated fetch for that port. It advances when identical values are returned. “Forecast issued” uses the provider's run time when it can be bound to the returned forecast. The current Open-Meteo Best Match response combines models without identifying the contributing run, so the display uses the time the port's forecast values last changed, prefixed with `~`. This estimate is stored separately as `forecastIssuedAt` with `forecastIssueBasis=VALUES_LAST_CHANGED`. The provider's `issuedAt` remains unknown. The immutable first-availability and original-response evidence are retained.

Current requires a successful check within **90 minutes**, an issue estimate within **8 hours**, and finite forecast values covering the current hour. The issue budget uses a **6-hour** global-model update interval plus a declared **2-hour margin**. The check budget permits a 60-minute collection cycle plus a 30-minute margin. A successful repeated check alone cannot extend the issue budget. Miniature effects use these same clocks and stop when either age limit or current-hour coverage fails. Simulated weather retains its simulation label.

The current UI reads “Checked 5 min ago · forecast issued ~19 Nov 06:00Z (latest available)”. The `~` marks the value-change estimate. “Latest available” means confirmed by a successful fetch inside the check policy.

On 19 November the metadata endpoints `/data/ncep_gfs013/static/meta.json`, `/data/dwd_icon/static/meta.json` and `/data/ecmwf_ifs025/static/meta.json` returned model initialisation, availability and update intervals of 21,600 seconds. The individual run timestamps were excluded from the mixed Best Match forecast because the provider documents that they do not directly identify its constituent runs. Metadata is evidence for the declared update interval. [Model metadata semantics](https://open-meteo.com/en/docs/model-updates) · [Global model update frequencies](https://open-meteo.com/en/docs/historical-forecast-api).
