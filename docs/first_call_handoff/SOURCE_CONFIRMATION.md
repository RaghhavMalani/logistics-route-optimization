# Source confirmation for one future JNPA call

This form is incomplete until an authorized terminal, agent or port operator confirms it. A public berth list or vessel-name lookup does not supply this confirmation. Please return the completed fields in a reply or an agreed document; the project operator will retain that acknowledgment and transcribe it into `handoff.json`.

| Item | Operator's confirmation |
|---|---|
| Organisation and terminal | |
| Data owner's name, role and contact | |
| Confirmation date/time with timezone | |
| Permission/reference for this research use and preferred transfer channel | |
| Canonical call/VIA reference and any alias/voyage mapping | |
| Vessel name and nine-digit MMSI | |
| Identity-verification document/reference | |
| Expected future anchorage arrival, with timezone | |
| Source timezone (for example Asia/Kolkata or UTC; confirm explicitly) | |
| Anchorage-arrival event: exact meaning and authoritative log/field | |
| All-fast event: exact meaning and authoritative log/field | |
| Scheduler estimate: whose individual waiting estimate, hours, and start/end events | |
| Availability: when each record first became accessible to the supplying operator | |
| Berth reference (confirm final berth after the call if not assigned yet) | |

Proposed target: elapsed hours from **confirmed anchorage arrival to confirmed all-fast**, including a confirmed zero wait. The supplying operator must agree that both timestamps represent those events. “Berthed on,” pilot boarding, cargo start and expected cargo completion must not be substituted without an explicit verified mapping to the agreed event.

Use ISO 8601 timestamps with offsets in the CSVs. `plannedArrivalAt` describes the future plan. `baselineEstimatedAt` and `baselineAvailableAt` describe an estimate that already exists before we freeze it. After the call, `arrivalAvailableAt` and `allFastAvailableAt` separately identify when each confirmed timestamp was accessible. `availableAt` is the combined record's availability, no earlier than either individual availability time. The project records its own later server receipt time independently.

Please provide the individual scheduler row **before actual arrival**. Provide the confirmed outcome row when both events are documented. Preserve the exact call reference/MMSI in both files. If a call is cancelled, delayed or renamed, tell us with its source/reference; do not silently replace the original row.

The project will return the frozen export and final evidence chain for reconciliation. The source owner should confirm the exported identity, scheduler estimate, two event times, availability times and berth against the original records. This acknowledgment is separate from approval of an advisory, actual action or model accuracy.
