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
