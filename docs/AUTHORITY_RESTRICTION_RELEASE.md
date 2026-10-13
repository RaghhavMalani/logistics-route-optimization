# Restored PortWatch: collecting weather and authority restriction

October 12, 2026. Public application: [India PortWatch](https://india-portwatch.vercel.app/login). The restored `e906f6a` interface remains the application: Company, Vessel, Port and Admin, maps, traffic, weather, globe, digital twin, inspectors and timelines. The eight protected role/twin source files match that commit after normalizing line endings. Capability panels and service adapters extend the existing workflow.

The previously validated learning capability was published first, using frontend `dpl_JARh8yMYPjjxfeHrxh2Ano5gPPua` and backend `24f8ea54-ac01-4f66-a11b-3bdbab264890`. Its production visitor world, public case evidence and 13 research-download hashes were preserved. Weather is **COLLECTING**, with no real matched outcome or promoted correction.

## Source-supported operational example

The new source is Manchester Ship Canal Company / Peel Ports **MNTM 2026-18**, published July 15, 2026: [original authority PDF](https://www.peelports.com/media/joolgbfb/mntm-2026-18-temporary-closures-of-eastham-80-lock.pdf), discovered on the [authority's marine notice index](https://www.peelports.com/marine/). Its retained PDF SHA-256 is `04a5847e17eae7787aa2feecd017039e6ab3020f9070d314319f15d5ec63e332`.

The notice expressly closes **Eastham 80-foot Lock** to vessel movements October 6Ã¢â‚¬â€œ15 and gives the first operational high-water tide as **October 16, 02:42 BST / 01:42 UTC**. Queen Elizabeth II Lock is explicitly unaffected. The application does not infer a closure of the whole canal or availability of an alternative lock. Closure dates retain date-only precision; normalized midnight is not a stated work-start time. The first published tide is a conditional planning point, rather than a confirmed reopening, navigation clearance, precise earliest permitted slot or measured access time.

From Company Ã¢â€ â€™ Global Eye Ã¢â€ â€™ Global intelligence, a visitor explicitly declares the fictional PW Meridian voyage's outbound route through the affected lock, dimensions, passage request and onward travel duration. The schematic traffic position and broad EuropeÃ¢â‚¬â€œIndia lane membership cannot establish exposure. Declared length 140 m, beam 19 m, draught 6 m and air draught 25 m do not validate this vessel's suitability for the canal or lock. The closure applies to all vessels using that lock. Alternate-lock suitability and booking remain unverified.

The demonstrated passage request is **October 15, 11:00 UTC**, with an **operator-assumed 180-hour onward voyage**. The calculation preserves the source, declaration and assumption separately:

| Option | Requested lock passage, UTC | Requested destination arrival, UTC | First published operational tide, UTC | Planned lock waiting | Total destination schedule shift |
|---|---|---|---|---|---|
| Keep the request | Oct 15 11:00 | Oct 22 23:00 | Oct 16 01:42 | 14 h 42 m | 14 h 42 m |
| Revise the request | Oct 16 01:42 | Oct 23 13:42 | Oct 16 01:42 | 0 h | 14 h 42 m |

Both options reach the same **conditional** destination arrival, October 23, 13:42 UTC. Revising the request relocates planned waiting before arrival at the lock. It does not shorten total delivery time or establish measured savings. Actual earliest permitted access, slot, reopening, clearance, berth, alternate-lock eligibility, fuel, cost and safety benefits are unavailable. The dated example becomes non-actionable after its declared passage time; no authority dates are moved to fabricate an evergreen example.

The notice also lists September and November windows. November calculation is blocked because its published withdrawal at November 19, 02:06 GMT precedes its first operational tide at 06:06 GMT. Authority clarification is required; the application does not guess which time is correct.

## Evidence and connected workflow

Original index and PDF bytes are immutable, hash-addressed receipts. Parsed revisions retain publication precision, first successful availability, previous revision, area, applicability, effective windows, cancellation status and exceptions. Later checks append source receipt times and hashes without replacing earlier originals. A future scheduled withdrawal is distinct from a present cancellation. Unsupported revisions, missing/ambiguous authority links, provider failures, cancelled/withdrawn notices and missing or corrupt original hashes block further actions. General construction wording cannot become a restriction without the supported explicit closure and operational-tide facts.

The independent authority worker checks at startup and every six hours. It shares the existing persistent source-evidence root on `/app/state`, while visitor declarations, comparisons, approvals, advisories and outcomes remain isolated in the existing durable visitor stores. Backend packaging includes public originals and research artifacts only; it excludes visitor/session/operator state.

The existing demo access policy lasts **12 hours**. Active visitor progress survives restarts within that session; a new demo is a different isolated visitor. A prior October 11 token had expired normally, so its older private records could not be checked through the API. Host archive inspection was unavailable without existing SSH credentials. No expired credential was restored and no longer retention guarantee is claimed. Public source and research evidence use the separate persistent evidence stores.

Company's named approval carries its frozen comparison into the original Port advisory screen. Port reviews and approves the same option, hands it into the existing advisory register and issues it. Vessel acknowledges and accepts. Port then records a visibly labelled **SIMULATED_DEMO_OUTCOME**, reproducing the frozen schedule assumptions. This outcome neither confirms actual lock reopening nor verifies weather. Ownership, role, changed route/dimensions/passages, ETA, source revision, source integrity and freshness are checked before continuing. Expired evidence can create an explicit linked successor comparison; prior comparisons, approvals and advisories remain retained. Retries reuse advisory and outcome records.

## Weather collection and remaining research

The backend weather reconciliation worker remains independent of the original freshness scheduler and runs at startup and every six hours. Complete retained targets first become eligible **October 17**; the retained five-day gust example becomes eligible around **October 21**. Provider eligibility does not guarantee returned data. The older five-day claim with missing original provider bytes remains visible and excluded from automatic reconciliation and correction fitting. No newer forecast can verify an older forecast. Station and ERA5 reanalysis cohorts remain distinct; daily correction results cannot alter hourly gust/visibility approach decisions.

Broader economic, hazard and news evidence remains available alongside this operational example. General infrastructure references remain contextual. The authorized-camera registry and reviewed planning adapter remain available, but no authorized footage has been supplied for a real evaluation. Neural fusion and constrained RL retain their rejected historical candidates, evaluations and stronger baselines. Their next evaluation targets and availability-safe protocols remain in [the learning preview record](WEATHER_INTELLIGENCE_LEARNING_PREVIEW.md); no research model or learned correction is promoted in this release.

## Validation and release evidence

- Final preview frontend: `dpl_5b5QJgC78mtHyFwJCkyfWEZbPFfR`, [preview](https://india-portwatch-7fmeof22d-flash2404s-projects.vercel.app/login). Preview backend: `3d8cfb05-2400-45ad-8deb-c412ad6eeb37`.
- `work/operational-restriction-20261012/packaging-r2.json`: all 897 uploaded backend files and hashes, protected-original assertions, retained public source originals, no operator state, existing `/app/state` mount.
- `tests-r4.log`: 32 backend checks passed, two existing authorization skips. Final field-semantics regression: four restriction checks passed. Test fixtures cover authoritative PDF parsing, BST conversion, the November contradiction, construction/cancellation handling, provider failure/revision/original corruption, frozen approvals, resource eviction, role permissions, retry safety and visitor isolation. These are software checks, not observed operational benefit.
- `restriction-api-validation.json`: anonymous hosted preview, real source hashes, fictional declarations, 14.7-hour consequence, Company Ã¢â€ â€™ Port Ã¢â€ â€™ Vessel Ã¢â€ â€™ simulated outcome; continuation after an actual backend restart following Port approval.
- `restriction-completed-recovery.json`: second actual preview restart preserves completed outcome, comparison and Vessel acceptance audit; checked again through the final preview's same-origin API.
- TypeScript passed. Targeted lint passed with two existing fast-refresh warnings. Final Vercel preview build passed. Browser captures and deployment IDs are retained beside `release-journal.json`.
- `work/capability-publication-20261012`: initial capability publication and production-preservation evidence. `work/operational-restriction-20261012/production`: final production evidence. Local `.private.json` session files are excluded from upload and public evidence.

The final production deployment IDs and post-promotion validation are recorded in `work/operational-restriction-20261012/release-journal.json` after promotion.

Final production frontend: **`dpl_EfptrcPf2M26GmRevdZMth7EDrMF`**. Production backend: **`3d01cead-9e3e-4e6b-a4ca-064461408f8c`**, using the unchanged volume `e8138731-4d1a-408f-b453-7343c2adbe57`. The project-level client address is `/api` in Production and Preview, preserving the validated proxy when Vercel rebuilds during promotion. The first promoted build exposed a legacy absolute API setting in the public browser; its fetch failure was corrected by persisting `/api` and re-promoting the same preview source. Public visitor, port-case and all 13 research-download hash checks passed; the archive retains 6,053 weather claims and zero matched outcomes. Counts can increase during collection and do not represent independent verification evidence.

The final public browser completed the entire connected workflow: Company decision `dec-notice-8a40f7fdc9abf8d31023`, recovered after Company approval and a page reload; Port review/approval and advisory `ADV-INNSA-20B5E71E2A`; Vessel acknowledgement/acceptance; Port's labelled simulated outcome. `production/public-browser-validation.json` and `production/public-completed-outcome.png` retain the proof. Production API checks also verified all four role adapters, retry safety and a different visitor's 404 isolation. The fresh visitor's world, existing public case and historical research hashes survived deployment; the two actual preview restart checks retained frozen approvals and completed outcomes.

The same public visitor also opened the original Admin Learning workspace, where weather remains collecting and both neural fusion and constrained RL remain rejected. Returning to Port recovered the completed outcome. All four public role workspaces were observed through the original role switcher; no new visitor was created during that native journey.
