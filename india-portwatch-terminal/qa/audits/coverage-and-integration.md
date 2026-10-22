# Coverage and integration audit

Date: 2026-10-18

Branch: `feat/preksha-ui-data-quality`
Purpose: Milestone 5 review and handoff boundaries for the next deliverable.

## What this audit can establish

The UI's provenance response describes four feeds in the captured walkthrough: IMF PortWatch port activity, IMF PortWatch satellite-AIS activity, Open-Meteo ERA5 archive weather and Open-Meteo marine weather. In that state, the two PortWatch feeds had a last source observation of 02 Oct 00:00Z, were fetched on 16 Oct, and were marked stale at 15 days. The shown counts were 4,692 rows for each feed. The ERA5 archive was historical training data, not the current forecast feed. The selected evidence inspector now makes the receipt time and the underlying observation window separate, shows `DATE_ONLY`, and labels missing port/variable coverage and original hashes as unknown.

These values are a captured product state, not a claim about today's upstream response. A successful fetch is not a new PortWatch observation. This branch does not alter provider records, write a new export, or change source freshness policy.

The generated source catalogue lists IMF PortWatch as `AVAILABLE` while showing no adapter in its product row; the runtime provenance view separately shows PortWatch rows. `AVAILABLE` is catalogue/provider availability, not proof that this deployment's adapter is connected. The integration owner should reconcile those two descriptions against the actual collector and export path before changing the generated catalogue. Do not edit `docs/DATA_SOURCES.md` by hand; it is generated from product metadata.

## Ranked coverage follow-ups

| Rank | Coverage gap and user impact | Evidence / availability | Effort | Owner and safe next step |
|---|---|---|---|---|
| 1 | Port-call and trade-activity recency is hard to trust when upstream observation time is delayed. | The walkthrough showed a 15-day-old observation despite a 16 Oct fetch. The provenance record includes the age and row count but not exact port/variable coverage or a retained receipt hash. | Low for diagnostics; medium for collector or normalization work. | Preksha can keep these fields legible. Integration owner verifies adapter, source mapping, retained original and export freshness; retain the current dataset until a candidate passes checks. |
| 2 | Headlines and inferred exposure do not establish that an authority restriction applies now. | GDELT and GDACS are catalogue products; neither alone is an authority confirmation. The current source contract permits event-validity and applicability gaps to remain unknown. | Medium. | Integration owner owns ingestion and consequences. Add authority confirmation/revision evidence only through the existing event contract; show validity and applicability separately. |
| 3 | Economic observations and forecasts need their own vintage, unit and target-period context before costs can be compared. | FRED appears in runtime provenance, but the generated catalogue excerpt does not define its product. Existing UI shows many unpriced costs as unavailable. | Medium. | Integration owner verifies product metadata and series vintages. Do not turn a dated price observation into a forecast or a cost saving. |
| 4 | Port capacity and infrastructure evidence needs provenance and scope before it can support access or schedule claims. | The existing port registry carries operational fields, but the source-quality receipt does not provide survey/measurement metadata for them. | Medium to high. | Coordinate with integration owner for source ownership and Ananya for geometry/asset metadata. Do not infer surveyed accuracy from a rendered twin. |
| 5 | Camera and imagery coverage is not ready to present as operational observation. | The catalogue does not establish an authorized camera product for this workflow. Public URLs do not establish redistribution rights; the God's Eye source note says its camera helpers are not imported as observations. | High, due to access/licensing and reviewed labels. | Wait for an authorized source and explicit access/attribution terms from the integration owner. Keep simulation and model-derived observation distinct. |

The first useful improvement in this branch is diagnostic: it exposes date precision, missing coverage, missing retained originals, and distinct observation/fetch times for existing feeds. No new collector or source name has been added without a verified adapter.

## Acceptance boundary

- **Delivered in this branch:** Admin Data source inspection, runtime validation for its optional quality contract, preserved legacy provenance on malformed quality metadata, role audit and first-pass before/after evidence.
- **Still requires integration review:** reconciliation of IMF PortWatch catalogue/adapter status, a verified candidate port-activity refresh, authoritative event validity, economic product metadata, and any source collector or shared decision/advisory-panel change.
- **Automated verification completed:** typecheck, changed-file ESLint, production build, and three focused Playwright checks at both 1920px and 390px. Those automated browser checks use a demo session and recorded fixtures; they do not prove live provider behavior.
- **Live local demo checks completed:** `/api/health` returned healthy with isolated durable-store paths; the Admin Data view displayed the actual four-feed provenance response; the evidence inspector opened; a demo session switched through all four roles with HTTP 200 responses; refresh restored the current role; and browser Back returned from Learning to Data Sources. The operator also confirmed all four feed inspectors opened and the evidence pane scrolled on mobile. The 390px Admin Data layout keeps document width at the viewport and exposes the inspector.
- **Still requires integration review or broader manual browser review:** a verified candidate port-activity refresh, authoritative event validity, economic product metadata, comparison/advisory flows, and mobile review of workflows beyond Admin Data. Background collection remained disabled during the local checks.

No production store, collector, model weight, approval state, geometry transform, or provider data was changed by this audit.

## Verification recheck — 2026-10-19

TypeScript, changed-file ESLint, the production build, and direct source-quality parser smoke checks passed. A fresh Playwright run could not launch in this Codex environment: its configured browser cache has no `.links` directory, and the system Chrome override stalled before the first test reported. The historical focused Playwright results above are retained as the 2026-10-18 run; this recheck does not claim a new browser-suite pass. The app's running demo servers were left untouched.
