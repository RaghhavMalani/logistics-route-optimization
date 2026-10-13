# Milestone A public release — October 9, 2026

**Review status:** the user rejected this version's visual result. Its deployment
and workflow checks do not establish product acceptance. The separate
[UI/globe correction preview](UI_GLOBE_CORRECTION_PREVIEW.md) is local and has not
been published; the version identifiers below remain the historical release.

**Published and checked:** [PortWatch entry](https://india-portwatch.vercel.app/), [Global Intelligence](https://india-portwatch.vercel.app/explore), [research](https://india-portwatch.vercel.app/research), and the [GLAD YOUNG case](https://india-portwatch.vercel.app/research#case-9ee7f41bdb419cbe0fc5a697a84365464ac94d91e707f0ac8175e8059c29fd2d).

The entry exposes Company, Vessel, Port and Admin demos in one action each. Start with Company, compare and submit a voyage proposal, switch to Port to compare resource policies and approve an advisory, switch to Vessel to acknowledge it, then return to Port to record a demonstration outcome. Admin shows network forecasts, source clocks and model status. This is a visitor-owned fictional scenario; operational authorization and real public evidence remain separate.

See [the implementation and full-product status matrix](MILESTONE_A_ROLE_DEMOS.md) for architecture, role permissions, data meanings and remaining milestones. The brief explicitly asks for this working Milestone A review before further large layer expansion; this release does not complete Milestones B–D.

## Verified versions

| Component | Version and verification |
|---|---|
| Railway backend | `f6c38080-8971-4717-8620-eb81ee219bdc`, SUCCESS, existing project/service/volume, verified production identity. |
| Vercel frontend | `dpl_6Yi7aZM7xHWtGamk2Ts4oCxmjhJo`, Ready, promoted to the existing public alias. |
| Final stage | [Unaliased verified build](https://india-portwatch-cb7n8rpuf-flash2404s-projects.vercel.app). |
| Research release | `research-5479e694ecfc40df`; all 13 downloadable artifact hashes retained. |
| Public case | All three event PDF hashes, prepared/review clocks and −24-minute published ETA baseline error / 2.4-hour reported waiting retained. |
| Demo state | Separate `/app/state/demo/sessions.sqlite3`; 12-hour opaque sessions, visitor isolation, revocation/reset, bounded histories. |

No temporary SSH key, account ownership change, new hosting resource, billing enablement, private dataset migration, collector cadence change or cohort rewrite was used. The backend source release has an explicit 447-file public-only manifest. Local QA state was isolated and its collector disabled; the task-owned API/frontend processes were stopped after validation.

## Results and visual evidence

- **14 Python tests passed:** demo boundary and full advisory chain, selected policy, changed proposal review, assignment restrictions, persistence, reset/expiry/revocation, negative operational access, public scenario and authorization matrix.
- **TypeScript passed. Changed-source lint:** zero errors, two inherited AuthProvider hot-reload warnings. **Production build passed.**
- **21 demo browser checks passed** on the final HTTPS stage and again on the primary alias. All four entries, populated scenes, actual comparisons, input sensitivity, cross-role chain, reload/reset/logout, visitor isolation, deep links, revocation, mobile controls, deliberate source-failure recovery and preserved public links were exercised. No runtime exceptions or unexpected demo API errors.
- **7 public browser regressions passed** on stage and primary: complete investigation journey, research/downloads, mobile/private boundaries, source recovery, real case timeline, permalink selection and server/browser clock mismatch. The explorer clock is initialized after hydration; no placeholder clock is sent to feedback or inference.
- **10 public API checks passed**, including CORS, constraints, replay availability, preserved originals and protected-write rejection. Hash verification did not run model fitting, holdout analysis or cohort evaluation.
- **3 renderer-failure checks passed** with WebGL disabled: the scene reports unavailable, the actual six-option backend comparison still works, and logout/role controls remain usable without runtime exceptions.

Production screenshots were visually reviewed after renderer readiness:

| View | Screenshot |
|---|---|
| Company globe and planning | [Company](../work/demo-A-primary-validation/company.png) |
| Vessel bridge and timing gate | [Vessel](../work/demo-A-primary-validation/vessel.png) |
| Port twin and constrained policies | [Port](../work/demo-A-primary-validation/port.png) |
| Admin network/model status | [Admin](../work/demo-A-primary-validation/admin.png) |
| Mobile globe | [Mobile scene](../work/demo-A-primary-validation/mobile-vessel.png) |
| Mobile planning | [Mobile decisions](../work/demo-A-primary-validation/mobile-decisions.png) |
| Four-role entry | [Entry](../work/demo-A-primary-validation/entry.png) |
| Unavailable globe with working planning | [Scene fallback](../work/demo-A-primary-validation/globe-unavailable.png) |

Machine-readable evidence: [release result](../work/demo-A-release-result.json), [source manifest](../work/demo-A-release-plan.json), [primary role journey](../work/demo-A-primary-validation/report.json), [renderer failure](../work/demo-A-renderer-validation.json), [public API and hash checks](../work/demo-A-api-validation.json), [primary public-browser log](../work/demo-A-primary-public-browser.log), [Python log](../work/demo-A-python.log), [build log](../work/demo-A-build.log). These are local review artifacts, not public visitor downloads.

## Limits and next work

Fresh forecast delivery remains Milestone B: the role UI accurately marks old target/origin dates as stale. Displaying a forecast beside a comparison does not make it a causal delay input. The principal company voyage is outside the initial 72-hour berth horizon; its proposed ETA is a future twin input rather than a claimed within-window benefit. Cargo connection cutoffs and total costs remain unavailable.

Broader intelligence, observed AIS and authorized camera/CV coverage remain Milestone C. No observed MMSI or connected camera is claimed for the fictional demo vessels/port layout. Weather correction entering subsequent inference, an actually trained neural candidate, a reproducible constrained RL experiment and newly reserved chronological calibration remain Milestone D. No new operational accuracy or savings claim is made by this release.
