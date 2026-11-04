# First retained weather outcomes: 17 October 2026

The isolated restored preview's automatic backend reconciliation has now matched **231 archived forecast snapshots to 39 independent port-variable-day reanalysis targets**. Its retained archive contains 8,275 forecast snapshots and 1,000 independent targets. These counts were read from the preview at 14:17 UTC on 17 October; repeated snapshots do not add independent outcomes.

The verification source is **Open-Meteo ERA5 gridded reanalysis**, distinct from station or operator measurements. This does not establish a validated correction or an actual shipping benefit. The latest periodic report at 11:36 UTC had no newly due forecasts, retained 39 outcomes and scheduled the next eligible targets for 18 October. Its `WAITING_FOR_REANALYSIS` status describes that run; it does not mean earlier matches were erased. **351 claims without qualifying original responses remain excluded.**

## A real matched example

| Field | Frozen forecast | Later outcome |
| --- | --- | --- |
| Port | INNSA / JNPA | ERA5 grid near INNSA |
| Variable and target | Daily maximum of 24 UTC hourly wind-gust samples, 11 October 2026 | Same variable, day, sampling and units |
| Value | 12.1 kn | 14.0 kn |
| First available to preview | 10 October, 07:33:18.895824 UTC | 17 October, 05:36:28.930879 UTC |
| Provider run/publication instant | Unknown | Unknown |
| Spatial meaning | Forecast request 18.95, 72.95; returned grid 18.945517, 72.975365 | Reanalysis grid, not a station reading |

Forecast ID: `wx-5a7d20b456738ccb`. Target aggregate ends at `2026-10-12T00:00:00+00:00`. Forecast minus outcome is **−1.9 kn**. The example has a one-day forecast horizon and is separate from the five-day case.

The forecast original SHA-256 is `38e05c989f2ff674dd808bdffb1676cf741eaccb3e5c1e5e124401e5bfed7f4a`. The existing preview evidence endpoint returned this original successfully and its 24 target bins reproduced the frozen 12.1 kn maximum. The older preview's general inspection endpoint did not expose the matching outcome receipt metadata; a later local reanalysis fetch reproduced 14.0 kn but has its own receipt clock and response hash. Those local and hosted receipts must not be conflated.

The capability update adds `latestMatchedCase` to the existing verification response. It selects a resolved case only while both archived response hashes remain intact, includes each receipt's exact metadata and uses the existing source-response inspector. After deployment, its hosted outcome digest must be checked directly; the local fetch is not a substitute for that check. The existing Weather/Global Eye verification panel adds a collapsed matched-case inspection alongside the five-day archive.

## Learning and remaining eligibility

JNPA's port report contains 18 resolved snapshots across three independent variable-targets. The gust context has six snapshots of one independent target, rather than six independent training examples. Corrections remain **COLLECTING**, and the subsequent daily watch consumes no learned correction. The current residual version requires sufficient independent outcomes within its port, variable, provider, horizon and season, followed by chronological validation, calibration and later evaluation. A single day across many ports does not satisfy one context's evaluation requirement.

The retained five-day example targets 15 October and becomes eligible around **21 October**, subject to actual provider availability. The older five-day claim without its original response remains excluded. Daily aggregate results never modify hourly gust/visibility approach decisions. Both neural-fusion and constrained-RL candidates remain **REJECTED**.

Ignored validation evidence is in `work/operational-pilot-20261017/`: `weather-summary.json`, `weather-global-snapshot.json`, `weather-matched-forecast-cases.json`, `weather-matched-source-proof.json` and `model-snapshot.json`. It was collected through a new disposable preview demo session; no production setting, collection job or evidence was modified.
