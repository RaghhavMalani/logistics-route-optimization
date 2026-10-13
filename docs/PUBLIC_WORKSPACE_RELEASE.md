# Public globe release — October 9, 2026

The first product recovery iteration is published at [PortWatch](https://india-portwatch.vercel.app/explore). Anonymous visitors enter the globe workspace from `/` and `/explore`. [Research](https://india-portwatch.vercel.app/research) and the [GLAD YOUNG case](https://india-portwatch.vercel.app/research#case-9ee7f41bdb419cbe0fc5a697a84365464ac94d91e707f0ac8175e8059c29fd2d) remain supporting links.

Select a maritime report, inspect exposed ports and routes, open a dated port forecast, then configure a shipping scenario. The report's compatible chokepoint is consumed by the existing constrained decision engine. Selecting an option redraws its route and the assumed vessel position. Duration, speed, sea height and cost rates remain explicit visitor assumptions. Port congestion forecasts provide context; they are not a calibrated causal routing input.

## Released artifacts

- Vercel project/team: `india-portwatch` / `flash2404s-projects`.
- Frontend deployment: `dpl_G97UwLztev2bYpgzZqFcF1KHPXys`, staged at `india-portwatch-166xcr8j4-flash2404s-projects.vercel.app`, then promoted to the main alias.
- Railway backend deployment: `577a5424-3274-4fdc-950a-d446cfda02c3`, production `api`, with the existing durable `/app/state` volume.
- Backend source manifest: `work/workspace-release-plan-r4.json`; 443 explicitly selected files. Operator databases, local outputs, credentials and QA state were excluded.
- Historical research release: `research-5479e694ecfc40df`; reviewed publication: `case-publication-420ed130487e4cda`.

The Docker context allows only the approved public source snapshots. Initial pipeline report bundles use the enclosing `live_status.exportedAt` clock; independently refreshed bundles use `refreshedAt`. Availability is bounded by the later source receipt/export clock and the actual present. Missing clocks withhold a feed instead of failing the workspace. The current single cache vintage is never treated as an earlier replay snapshot.

## Verification

The final staged frontend passed 16 full-journey checks in fresh anonymous Chromium contexts and all six public browser regressions. After promotion, the main public domain passed the same 16 journey checks. The checks exercised report → affected assets → dated forecast → selected chokepoint comparison, rendered Cape diversion, changed restriction duration, weather safety rejection, layer markers, weather original/observation availability, replay, research navigation, source failures and mobile panels. Desktop and mobile screenshots were visually inspected after the globe tiles loaded. No browser runtime exceptions or horizontal overflow were detected.

Focused Python public workspace/research/decision/clock suites passed **58 tests**. The subsequent legacy export-clock regression passed the three workspace tests. TypeScript, changed-file lint and the Vercel production build passed. Validation did not fit a model or evaluate prospective cohorts.

Hosted read-only API verification checked:

- 13 ports, 22 source-linked reports, 13 dated weather rows and ten catalogue lanes. Eight international lanes have route geometry; the two coastal memberships have no distinct offshore origin.
- Six default Suez scenario options. A restriction at Bab-el-Mandeb consumes that location and preserves the earlier Suez timing gate, yielding four options rather than an instant Cape diversion.
- Increasing the assumed restriction from 72 to 120 hours changes baseline ETA shift from 50 to 98 hours. A nine-metre assumed sea rejects options through the marine safety constraint.
- Finite bounded inputs and timezone-aware visitor clocks; forged administrator headers fail with 401 for private cameras and collection/scenario writes.
- All 13 previously published research artifact hashes and all three GLAD YOUNG event PDF hashes; original raw clocks, availability times, preparation/review times and sanitized audit remain intact.
- Retained durable public counts: Paradip 23 frozen ETAs, three matched arrivals and one complete call; Chennai 41 frozen ETAs and no matched arrival/complete call at the check. These are collection counts, not an accuracy result.

Records: `work/workspace-staged-validation-r4/report.json`, its screenshots, `work/workspace-regression-report.json`, `work/workspace-api-validation.json`, `work/workspace-frontend-promotion.log`, `work/workspace-production-validation/report.json`, and `work/workspace-release-result.json`. Primary-domain browser results are recorded separately from staged results. The external web-fetch tool could not access these URLs during this run, so this release does not claim a new independent off-computer verification. Anonymous browser and HTTPS API checks use public domains without cookies, credentials or protection bypasses.

## Review scope

This is the first workspace iteration for product review. Observed public AIS, continuous global weather fields, live berth/inland feeds and authorized port camera viewpoints remain unavailable. The globe labels the configurable vessel as simulated. Current weather feedback has original forecasts but no resolved public observation pairs at verification; it does not establish a learned correction improvement. Neural fusion, constrained RL and newly reserved-period interval calibration remain subsequent research work.

The collection cadence, Windows tasks, cohort enrollment dates and existing case review were unchanged. Collection continues through the backend scheduler. No new SSH key was registered, no Git history was rewritten or pushed, and no paid provider was enabled. GLAD YOUNG remains a **−24-minute published ETA baseline error** and **2.4-hour reported arrival-to-berth wait**, not an ML outcome or confirmed all-fast interval.
