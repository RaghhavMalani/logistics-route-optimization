# Source trial decisions

The isolated 48-hour window started **6 Nov 2026 18:00:34 UTC** and ended **8 Nov 2026 18:00:34 UTC**. The first qualifying collection was about five minutes into the window. Scheduled intervals, retries and startup gaps count in the results. Scope `trial-live-20261106180034` retains the snapshots and attempts on the preview volume.

| Product | Decision |
| --- | --- |
| [GDELT BigQuery](GDELT_BIGQUERY.md) | Deferred. Billing project, workload credentials and a daily scan budget are required. |
| [Open-Meteo marine and ensemble](OPEN_METEO.md) | Adopt the marine fields for covered ports and the wind member range for all covered ports as modelled context. |
| [AISStream](AISSTREAM.md) | Deferred pending retention and display rights. Replay remains primary. |
| [IMD RSMC](IMD.md) | Rejected for this iteration pending reproduction permission. |
| [Frankfurter ECB FX](FRANKFURTER.md) | Adopt the dated daily reference rates for display. |
| [NAVAREA VIII](NAVAREA_VIII.md) | Reject the candidate as a current warning feed. The existing validity filter remains. |

The adopted products publish fresh collections in a separate scope on the eligible preview. Trial records remain private. No new input changes the decision policy. [Decision policy gate](../../../docs/DECISION_POLICY_GATE.md)

The [isolated Sources API](https://api-live-now-live-now-preview-20261106.up.railway.app/api/public/sources) shows collection health and the completed trial decisions. The review used the read-only coverage and attempt metadata retained at 11 Nov 08:18 UTC. The detailed report command is `python -m scripts.source_ingest report <product> --trial live-20261106180034 --start 2026-11-06T18:00:34.970026+00:00`. Run it with the preview snapshot store configured. The report performs no provider requests.
