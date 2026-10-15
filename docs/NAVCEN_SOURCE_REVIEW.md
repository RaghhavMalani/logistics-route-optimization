# Reviewed NAVCEN bridge restriction

Reviewed October 14, 2026 for the noncommercial PortWatch research and demonstration preview. This review covers one authority notice, not a general bridge-description parser.

## Source access and use

The official [NAVCEN MSI Products page](https://www.navcen.uscg.gov/msi) links directly to the public [Bridges GeoJSON product](https://www.navcen.uscg.gov/sites/default/files/msi/bridge_1.geojson). Both returned public content without authentication. The [modernized LNM application FAQ](https://www.navcen.uscg.gov/LNM-and-LL-app-frequently-asked-questions) explicitly describes public GeoJSON access, fifteen-minute LNM refreshes and geospatial presentation. That refresh interval is a provider description, not a guarantee that a particular notice changes or that PortWatch has received every intermediate revision.

The official [USCG website disclaimer](https://www.uscg.mil/disclaim/) identifies information in its non-logged-in domain as public information that may be copied or distributed, and disclaims endorsement. The official [USCG community FAQ](https://www.uscg.mil/Community/faq/) also permits distribution, copying and linking by outside websites, but prohibits commercial use, implied Coast Guard endorsement and copying the Coast Guard site's branding. These two policy passages were available through the search index of their official URLs; direct retrieval returned HTTP 403 on this review date. Preserve that verification limitation. This integration is bounded to this noncommercial research/demo use, credits the United States Coast Guard Navigation Center as the source, and does not use its seal or imply endorsement. This is not authorization for a later commercial redistribution service.

[17 USC 105, published by GovInfo](https://www.govinfo.gov/content/pkg/USCODE-2024-title17/html/USCODE-2024-title17-chap1-sec105.htm), excludes U.S. Government works from U.S. copyright protection. That rule does not establish that every third-party enclosure, image or linked website is a government work; the reviewed integration does not ingest those products. [NAVCEN's NAIS sharing restrictions](https://www.navcen.uscg.gov/ais-data-sharing-categories-requirements) concern NAIS feeds and historical AIS disclosure. No NAIS feed is obtained by this adapter.

## Precisely reviewed record

The selected feature has `MSI_UID` and `ESRI_OID` **53842**, status **Approved**, district **5**, category **Bridges**, and type **Temp Deviation**. Its source point is **34.21828 N, 77.81259 W**, identified as the **74 State Route Bridge / S.R. 74 (Wrightsville Beach) Bridge**. Its waterway UID is `100119260597`; retain the source's full MRN and feature properties with the response. The point identifies an asset; it does not define a closure polygon, anchorage or full navigable route.

The notice describes the S.R. 74 bridge being held closed to navigation on **October 17, 2026, from 04:30 to 10:15**. It separately describes the Isabel S. Holmes bridge from 07:30 to 14:30. The reviewed point and consequence calculation select S.R. 74 only. They must not attach the Isabel S. Holmes window to this point or infer that both bridges are on the visitor's route.

The notice states a **20 ft vertical clearance above mean high water** for S.R. 74 in the closed position; vessels able to pass while closed may do so. Emergency opening is possible with at least fifteen minutes' notice. Closed-position clearance is context, not a tide prediction or clearance certification. A conditional calculation requires the operator to explicitly declare this passage and that an opening is required; destination-port membership alone cannot establish exposure. The ordinary comparison cannot model an emergency opening as guaranteed access.

The source's epoch-millisecond metadata decode to:

| Field | Decoded value | Interpretation retained |
| --- | --- | --- |
| `CREATE_DATE` | 2026-09-16 16:49:58 UTC | Source record creation metadata |
| `MODIFIED_DATE` | 2026-09-16 18:12:59 UTC | Source record modification metadata |
| `BEGIN_DATE` | 2026-10-10 00:00:00 UTC | Source record envelope |
| `END_DATE` | 2026-10-18 23:59:59 UTC | Source record envelope |

No public field definition establishes the first publication time. Do not label creation or modification as first publication or first PortWatch availability. Preserve the raw values and actual first receipt. The broad begin/end envelope is not the bridge's closure interval. `Approved` is source workflow status, not proof that an actual closure happened, an opening was requested or a vessel passed.

## Time precision and conditional calculation

The [district 5 preface linked by MSI](https://www.navcen.uscg.gov/sites/default/files/pdf/msi/D5.pdf) says times are local unless otherwise noted. It still bears a 2024 header, and the MSI page says introductory material is being revised. Therefore the implementation preserves the original local interval and requires explicit operator confirmation of the **America/New_York** conversion rather than representing that IANA identifier as a field in the notice.

With that declared conversion, October 17 falls in UTC-04:00: the restriction window is **08:30–14:15 UTC**. For a declared requested passage at **08:00 local / 12:00 UTC**, the conditional earliest passage is **10:15 local / 14:15 UTC** and restriction waiting is **2 h 15 min**. A revised arrival at the same 10:15 local moves that wait before arrival at the bridge; it does not create faster overall passage. For this example both options have **2 h 15 min total schedule shift** relative to the original requested passage. Exact arrival-to-berth wait, anchorage use, all-fast time, fuel, cost, capacity and safety benefits are unavailable.

The boundary is the end of the scheduled restriction, conditional on the notice remaining applicable and normal bridge operation resuming. It is not an observed reopening, reserved opening slot or clearance permission. A prospective comparison must be frozen before the target with the actual received source; later replay must retain its replay label.

## Revision, cancellation and verification limits

Archive the full response bytes and hash, selected feature, receipt, raw metadata and reviewed extraction version. A changed version of the same feature is an authority revision, not independent confirmation. Explicit cancellation or conflicting restriction text must block continued use until reviewed; disappearance from a later product or a missing report alone does not prove cancellation or non-occurrence. Unknown status and changed unreviewed prose must not silently inherit the old calculation.

This notice supports the fact that an authority published a scheduled restriction. It does not independently verify its own extraction, establish the actual closure or settle shipping-impact predictions. Independent operator/authority records must identify the particular episode, executed action and actual passage/wait reference. No real operational outcome is established by this source review. General construction notices, including the separate Walk Bridge construction feature, must not become closures. The previously considered BNM 70062230 has an explicit October 13 cancellation time and is excluded from prospective use.
