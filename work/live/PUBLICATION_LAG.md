# IMF PortWatch publication lag

The preview retained two successful collections with different newest Indian port activity dates. Earlier preview observations seeded from a package lack a comparable first collection receipt.

| Newest observation (UTC) | Successful collection evidence (UTC) | Elapsed |
| --- | --- | ---: |
| 30 Oct 2026 | 7 Nov 2026 09:00:29 (retained successful pipeline attempt) | 201.0 h |
| 6 Nov 2026 | 11 Nov 2026 01:02:26 (retained activity provenance) | 121.0 h |

Median elapsed time was 161.0 hours (6.71 days). The feed supplies observation dates. The timestamp at which PortWatch collected each batch is an upper bound on when it was published. Two collections support a provisional estimate. The activity collector records the newest observation and receipt time for every successfully retained batch before the forecast runs. Health and Sources recompute the estimate from the earliest receipt for each observation day in a rolling 90-day window. A repeated fetch of the same observation day counts once. Sources displays the number of distinct collections used.

Use the daily observation cadence for current data, then the measured median for expected publication lag. With fewer than two observation days, the lag estimate is unavailable. An expired congestion forecast stays stale even within the activity publication window. Hourly weather and hazard feeds keep their own response-age and valid-time policies.
