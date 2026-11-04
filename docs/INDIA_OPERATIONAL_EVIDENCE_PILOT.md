# India operational evidence pilot

The existing official-public-report pipeline now supports a bounded, read-only evidence adapter in the original intelligence panels. It uses `PublicPilot`, its immutable PDFs, SQLite snapshots, versioned parses, future ETA enrollment, availability barriers and fixed cohorts. The IMF contextual adapter uses the existing `app.data.portwatch._query` paging/validation path with a receipt sink. It does not refresh or reinterpret unrelated local `data/portwatch` CSV files.

## Genuine collection inspected on October 17, 2026

The backend collector successfully retained the following official Chennai Port Authority originals. Their printed report date remained **October 16**; receiving them on October 17 does not change that date.

| Product | Actual pilot receipt (UTC) | SHA-256 | Extracted rows |
|---|---|---|---|
| [Vessel position](https://www.chennaiport.gov.in/api/static/default/vessel_report/pos.pdf) | 2026-10-17 14:16:22.554602 | `e29fface237bcfc277876eb8ca49df56230620bbe202068671aa3469fe404561` | 19 |
| [Expected arrivals](https://www.chennaiport.gov.in/api/static/default/vessel_report/eta.pdf) | 2026-10-17 14:16:23.061716 | `9784ded66b5c85a24047a645d278a615e42ac44374afc7e8e2e812d928911e92` | 47 |

The existing enrollment logic froze **43 future expected-arrival cases**, with **0 matched arrivals and 0 reported arrival-to-berth outcomes** at that receipt. These are prospective research cases, not demonstrated prediction accuracy or demo-vessel actuals. The current PDFs were also fetched during the October 16 qualification audit; that earlier separate audit receipt is retained in ignored work evidence. It is not backdated into this pilot's first availability.

Those counts describe the clean local pilot archive. An existing hosted volume may already contain the same bytes under an earlier parser. Reprocessing them preserves old frozen cases and adds a parse view; it does not retroactively enroll new cases from corrected fields. Report actual hosted counts after deployment rather than copying the local 43-case figure. A genuinely changed later report can enroll eligible future arrivals through the existing collector.

The Chennai expected-arrival parser is now `public-port-report-v1.3`. It derives cell boundaries from the reviewed table header. The old fixed horizontal bands clipped dimensions: the October 16 TIGER CHENNAI row prints LOA 199.98 m, beam 35.20 m and draft 11.00 m. The corrected extraction retains those full values. Earlier snapshot bytes, parser views, fact availability and frozen cases remain unchanged; a revised parse becomes available only when it runs. Existing October 7/8 fixtures remain supported, including conflicting printed date headings, which still fail closed.

The IMF PortWatch query returned **33 daily aggregate rows**, latest source date **October 9**, at **2026-10-17 14:16:24.456699 UTC**. Its raw response SHA-256 is `7242f981c6a6dbb22c33df0ebed5c6692ae704be6688488ec43483a3cf863f69`; receipt ID `63bd4c535976d8dfea7cd378f8320f534d8363171203bf86da75a9f6b353d9c1`. This is **8-day-old aggregate context**, not current individual vessel evidence. The query is restricted to IMF physical port `port776` (JNPA, `INNSA`). Existing canonical port catalogue points may focus the map; they are not vessel coordinates.

The public Paradip index was reachable during qualification and listed an October 16 daily report. A catalogue listing alone is not a successfully parsed report receipt. Its product remains unavailable until the existing Paradip collector retains and validates a genuine PDF.

## Semantics and source use

Chennai/Paradip PDFs are attributed to the port authority named in the selected original, with original URLs and report dates visible. They are bounded research inspection of the already integrated public reports. No blanket open-content licence, endorsement or permission for unrelated material is asserted. The Chennai homepage was reachable during qualification, but its client-rendered policy content was not established as a specific dataset licence. Do not expand this adapter into general website mirroring on that basis.

IMF PortWatch is attributed to the International Monetary Fund and linked to [data and methodology](https://portwatch.imf.org/pages/data-and-methodology) and [IMF copyright and usage terms](https://www.imf.org/external/terms.htm). The adapter selects fields and normalizes daily dates for inspection; it does not claim IMF endorsement. The public methodology page describes an open monitoring platform. The ArcGIS layer's blank copyright field is not treated as a licence. Dataset/source conditions remain applicable. Trade fields remain raw attributes with unverified units; only the reviewed aggregate `portcalls` count is labelled calls/day.

Printed date, first original receipt, revised parse availability, last collection check and failed checks are separate. Exact publication/observation instants remain null when unestablished. The PDF age policy labels a report current only on its printed date or following day in the explicitly assumed Asia/Kolkata timezone; older reports remain visibly stale. This is a reporting-age rule, not evidence that every vessel event in a report occurred recently. IMF daily series dates remain date-only and separately aged. HTTP `Last-Modified` is retained for aggregate responses but is not substituted for publication or observation time.

Public expected arrival, publisher-reported arrival/position, reported berth and operator-confirmed all-fast are different targets. Public names/dimensions do not establish a real-vessel association to a visitor's declared demo voyage. Future expected times are allowed; future reported actual events, mismatched physical ports, missing originals, source hash failures and parsed rows that disagree with originals are rejected for review. Repeated receipts retain first known fact availability. Revisions retain separate raw responses. No collection creates visitor actual execution, bridge waiting, delay, fuel, monetary or safety claims.

## Interface contract and useful loop

`GET /intelligence/operational-evidence` projects the latest retained product for each supported PDF kind and the JNPA aggregate product. It performs no network collection. It includes source identity, exact selectors, original hash verification, clocks, report age, missing fields, record semantics, scope, collection failure and visitor-owned voyage options. `GET /intelligence/operational-evidence/original` serves hash-checked retained originals within the existing authenticated visitor boundary. There is no demo collection-write endpoint.

An exact selector is either `{product:"PUBLIC_PORT_PDF",portCode,snapshotId,recordId}` or `{product:"IMF_PORTWATCH_DAILY",portCode,receiptId,recordId}`. The server resolves every selector from the archive and rechecks its row against the original source. The browser cannot submit arbitrary actual records as evidence.

A Company user explicitly selects a voyage and port context. A different candidate port requires confirmation; the selection does not silently alter the route or identify a real hull. The existing review-task ledger preserves the source row, original question, stable episode and actor. A suitable new evidence disposition can answer **inspection of published port context** as `CONTEXT_REVIEWED`. Original task evidence and other unresolved source/actual questions remain inspectable. This is a completed bounded context-review loop, not an operational accuracy claim. No unsupported numerical comparison is passed into Company → Port → Vessel approvals.

PDF collection remains in the existing independently retried port jobs. Aggregate receipt collection uses the same backend freshness coordinator and persistent public-pilot root. Network errors and failed provider responses retain check times separately from the last good response. Restart recovery does not relabel old observations as current. OCEANS-X is separately qualified; authenticated suitability remains unverified and it is not a replacement restriction feed. See `OCEANS_X_QUALIFICATION.md`.

Weather reconciliation and the rejected neural/RL candidates are independent of this adapter. Real resolved weather/operational targets must be reported from actual backend snapshots; no context disposition adds one.
