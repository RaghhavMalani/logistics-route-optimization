# Source trials

These are actual private trials, not adoption receipts. The fixed window starts **6 Nov 2026 18:00:34 UTC** and ends **8 Nov 2026 18:00:34 UTC**. First successful collection began about five minutes into that window. Startup/deployment gaps count against coverage. Restarts preserve the start/end and retry history. Source health exposes last success/error, seven-day attempts/rate and trial coverage summaries; private data remains unavailable to workspace decision inputs.

At least 48 elapsed hours, coverage/lag review and a recorded adopt/reject decision are required before publication. None of the new candidates changes the decision policy; docs/DECISION_POLICY_GATE.md remains required. Per-source reports below are interim and must be updated with the final measurements, including gaps, before any adoption.

Isolated API: https://api-live-now-live-now-preview-20261106.up.railway.app/api/public/sources. Collector/report commands: `python -m scripts.source_ingest report <product> --trial live-20261106180034 --start 2026-11-06T18:00:34.970026+00:00`, executed in the preview service with its configured snapshot store. The report command performs no provider requests.
