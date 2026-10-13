# Public cloud release — October 8, 2026

The public research application is published at [PortWatch Explore](https://india-portwatch.vercel.app/explore) and [Research](https://india-portwatch.vercel.app/research). The [GLAD YOUNG case permalink](https://india-portwatch.vercel.app/research#case-9ee7f41bdb419cbe0fc5a697a84365464ac94d91e707f0ac8175e8059c29fd2d) selects its reviewed evidence timeline.

The frontend connects to `https://india-portwatch-api.up.railway.app/api`. Archived PDFs, the sanitized case audit and research downloads use public HTTPS endpoints. Visitors do not need a login or a deployment-protection bypass. Private camera access and collection writes require verified identity; asserting an administrator header returns 401.

## Released artifacts

- Vercel team: `flash2404s-projects`; authenticated deployment permission verified as OWNER.
- Frontend deployment: `dpl_3rEuuCzbwSxxKZxsUBV7UK6eFpdU`, promoted to `india-portwatch.vercel.app`.
- Railway project/service: `india-portwatch-api` / `api`, production.
- Backend deployment: `ef62c155-8156-4ec7-9e5a-efc5d23eff5d`.
- Historical research release: `research-5479e694ecfc40df`.
- Reviewed case publication: `case-publication-420ed130487e4cda`.
- Durable state: existing Railway volume mounted at `/app/state`.
- Preserved public pilot: 62 frozen ETAs, eight document snapshots, two fixed enrollment cohorts. Paradip has 23 frozen cases, three matched arrivals and one complete chain; Chennai has 39 frozen cases and no complete chain.

The public database and evidence were transferred before deployment. All 22 retained files initially matched their local SHA-256 hashes. A subsequent read-only audit after cloud replacement confirmed identical snapshot, case, parser revision, cohort, membership and collection rows, with SQLite integrity checks passing. No original collection times, frozen estimates, cohort definitions or visual reviews were changed.

The release includes five inspected public-source bootstrap caches: `provenance.json`, `port_state.json`, `forecast_by_port.json`, `news_bundle.json` and `live_status.json`. Their original timestamps are retained. At validation, Explore listed 13 ports, supplied 120 forecast rows across 12 ports and showed 20 public events. The October 2 forecast origin remains visibly stale. These caches provide initial visitor content while the backend scheduler rebuilds data; they do not imply fresh observations or operational accuracy.

The backend enables one scheduler process, public-port collection, verified identity and the packaged research/case directories. VesselFinder stays disabled. A later elapsed three-hour cloud collection cycle has not yet been verified. The previously configured local service was left running; this release did not change Windows tasks or monitoring.

## Verification

The published domain passed 54 checks in a fresh anonymous Chromium context, covering desktop and mobile pages, model/horizon selection, route-speed assumptions, case selection and clock switching, raw publisher clocks, public HTTPS requests, all research download hashes, all three case-event PDF hashes, sanitized audit contents, CORS and rejected unverified writes/private access.

An additional check executed inside the Railway container, outside the user's computer, without HTTP credentials or cookies. Both public pages, the case API/audit, original PDFs, metrics CSV and results ZIP returned 200; document/artifact hashes agreed. No localhost URL or authentication bypass was used.

Validation records and screenshots are retained under:

- `work/cloud-production-validation/report.json`
- `work/cloud-production-validation/`
- `work/cloud-external-verification.log`
- `work/cloud-preservation-verification.log`
- `work/cloud-release-plan.json` — uploaded source manifest and public bootstrap list
- `work/cloud-release-result.json` — deployment identifiers, checks and limitations

The user-approved temporary SSH key was removed from Railway after verification. Its two local copies and public halves were deleted. No credentials were packaged in either deployment. This release used local uploads; it did not push Git changes.

GLAD YOUNG's −24-minute result remains **published ETA baseline error**, and 2.4 hours remains **reported arrival-to-berth waiting**. Public berth time is not confirmed all-fast. The case validates an evidence workflow, not ML accuracy or savings. No prospective cohort evaluation, interval-calibration experiment, neural fusion or RL was performed during publication.
