# One qualifying future JNPA call

The milestone is **one real future call, frozen before arrival and reconciled after all-fast**. It is not a larger public-report archive or another model benchmark. The nine already-berthed public entries remain historical supporting evidence and cannot become prospective claims.

## Handoff status — October 7, 2026

| Dependency | Status |
|---|---|
| Operational owner / terminal or agent | Not yet agreed |
| Call identity, event meanings and timezone | Supplier confirmation pending |
| Future call and verified MMSI | Not supplied |
| Individual scheduler estimate before arrival | Not supplied |
| Frozen issue-time weather and observed AIS for that call | Not yet collected |
| Confirmed arrival/all-fast and availability records | Await the future call |
| Qualifying prospective calls | 0 |

The next external step is an introduction to an authorized data owner. The prepared [request](first_call_handoff/OPERATOR_REQUEST.md) asks for one call and a small manual/CSV handoff. It does not ask for private cameras, operational changes or an unevaluated model deployment.

The [Paradip and Chennai public-data pilot](PUBLIC_PORT_PILOT.md) proceeds independently while this JNPA handoff is pending. Its published ETA/reported berth targets remain separate from the confirmed arrival/all-fast protocol below.

An unsent Gmail draft of this request was saved and verified with the source-confirmation form and both header-only CSV files attached. Sending requires the user's explicit instruction. Creating the draft does not establish contact or a data-sharing agreement.

The [official JNPA contact directory](https://www.jnport.gov.in/page/contact-us/N3BzcmRpa0gzQU9sRkNiMEwzc0E1Zz09), checked October 7, lists **cmt@jnport.gov.in / +91 22 6781 4191** for Traffic and **harbourmaster@jnport.gov.in / +91 22 6781 4173** for the Harbour Master. Traffic is a proposed introduction route to the responsible terminal/agent; Marine is a proposed route for event-definition questions. Neither contact has agreed to supply data. The request is prepared for Traffic alone.

## What to hand to the operator

- [Source confirmation form](first_call_handoff/SOURCE_CONFIRMATION.md): named owner, allowed research use, canonical call mapping, MMSI evidence, timestamp definitions and timezone.
- [Individual arrival/scheduler CSV](first_call_handoff/operator-arrival.csv): one future call and its existing individual waiting-hours estimate.
- [Confirmed outcome CSV](first_call_handoff/operator-outcome.csv): the same reference/MMSI, confirmed arrival/all-fast, separate availability times and source/berth references.

The CSV files contain headers only. They are not sample operational records. The supplier can return CSVs or log extracts with a confirmed transcription. Check that the supplier is authorized for these records and retain their acknowledgment before completing the internal [handoff manifest](first_call_handoff/handoff.json). Its blank fields deliberately prevent an incomplete pack from passing reconciliation.

## Capture the first call

1. **Agree the source.** Confirm the owner, terminal, canonical VIA/call reference, vessel/MMSI match and documentary identity reference. Agree what anchorage arrival and all-fast mean in the actual logs; confirm the source timezone and availability meaning. Do not assume the public “Berthed on” field means all-fast. Retain the source owner's acknowledgment and research-use reference.
2. **Obtain the individual baseline.** The supplier returns the arrival CSV before actual arrival. Planned arrival must be in the next seven days. The scheduler's issue/availability times must already exist; its start/end events must match the measured waiting target. An expected completion time or aggregate queue cannot replace the individual estimate.
3. **Check collection inputs before committing.** Use the verified JNPA authority workspace with LIVE clock and durable ledger storage. Arrange an authorized AIS source through the existing ingest or recorder import. Confirm two timestamped positions for this exact MMSI in the preceding 24 hours, latest source age at most one hour, and an archived maximum-wind forecast covering planned arrival. AIS proximity alone does not establish JNPA call identity. A weather fetch or AIS import after registration cannot repair an earlier frozen claim. Select a future call with enough lead time for these inputs.
4. **Freeze and save.** Start the prospective cohort, preview and commit the supplier's arrival CSV, and immediately export the cohort JSON as `frozen-export.json`. Check the actual frozen AIS/weather references, source/receipt/recording times, baseline reference and registration actor. Numerical model output may remain unavailable on this first call; a fitted GBM is not required for collection qualification.
5. **Receive the measured record.** After all-fast, get the confirmed outcome CSV and log/confirmation reference from the same authorized source. Both event availability times are required. Preview/commit the outcome and save a new `final-export.json`. Measurements can be collected without an advisory or actual-action record; absence remains explicit.
6. **Return the chain for reconciliation.** Ask the source owner to confirm the exported call identity, scheduler row, arrival/all-fast, availability times and berth against their records. Record that separate acknowledgment. Preserve corrections/discrepancies for investigation; do not edit immutable originals or silently substitute another call.

Actual scheduler and port-call records may be supplied through an agreed private transfer channel. Only the empty templates belong in the handoff draft. Keep filled records, documents, manifests and exports in a private work directory outside version control, such as `work/jnpa-first-call`.

## Reconcile without changing operational state

Copy `handoff.json` into the private handoff directory. Fill the agreed source definitions and selected call, then name the retained source files with paths relative to that directory. Every evidence file requires its exact source reference and SHA-256. The agreement/identity references must match the manifest; the scheduler/outcome references must match the frozen ledger. Put the operator-returned CSVs in that directory, preserving their original bytes and offset-bearing timestamps. Keep pre-arrival and final exports as separate files.

To obtain a retained file's hash on Windows:

```powershell
(Get-FileHash -LiteralPath .\work\jnpa-first-call\operator-arrival.csv -Algorithm SHA256).Hash.ToLowerInvariant()
```

First check the pre-arrival export:

```powershell
python -m scripts.reconcile_jnpa_call work/jnpa-first-call/frozen-export.json --handoff work/jnpa-first-call/handoff.json --phase frozen --output work/jnpa-first-call/frozen-check.json
```

After the source owner reconciles the final export:

```powershell
python -m scripts.reconcile_jnpa_call work/jnpa-first-call/final-export.json --handoff work/jnpa-first-call/handoff.json --frozen-export work/jnpa-first-call/frozen-export.json --phase complete --output work/jnpa-first-call/final-check.json
```

The checker uses the standard library and no API credentials. It reads the exports and source files, compares normalized timestamp instants and numeric values, verifies hashes and retained references, recomputes waiting hours, checks the named audits and qualifying flag, and compares every frozen original against the pre-arrival export. Evidence paths cannot escape the handoff directory. It writes only an explicitly requested new report file; it never writes a ledger, backdates availability or changes the qualifying count.

`FROZEN_INPUTS_RECONCILED` confirms the first export matches the supplied baseline and available inputs; it is not a completed call. `QUALIFICATION_RECONCILED` requires the final measurement, a pre-arrival export, unchanged originals, qualifying status and the source owner's reconciliation acknowledgment. Any mismatch produces named blockers and a nonzero exit. The checker verifies consistency, not the authenticity or authority of a document's sender; the project must establish those through the operational contact.

Once one real call passes both the workspace qualification and source reconciliation, repeat this handoff toward the documented evaluation cohort. One call establishes collection feasibility; it does not establish model accuracy, weather/AIS value or savings.

Validation: all **five handoff reconciliation tests passed** using isolated synthetic source documents. They cover the frozen/final chain, immutable originals, retrospective exports, identity mismatches, late source agreement, missing reconciliation acknowledgment, changed file hashes, evidence-path confinement and late weather. The standard-library CLI also refused the empty operator pack against an empty operational export. Production arrival-event count remained zero. The API/frontend were unchanged in this handoff step; their earlier suite results were not rerun.
