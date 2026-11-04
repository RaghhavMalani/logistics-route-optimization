# Mobile map access, clocks and Indian-source review

October 30–31, 2026. Local work from `2b6120236b136d3975d2bfa8b7824eabd832eb3f` on `feat/portwatch-restored-intelligence`. The restored application now includes bounded Indian navigation-source review, explicit dependency reassessment, accessible mobile map controls and corrected clock boundaries. Hosting remains deferred.

Local compiled preview: [Company](http://127.0.0.1:4214/company/overview), [Paradip source inspection](http://127.0.0.1:4214/company/global-eye#intelligence-review?noticeId=NHO_NAVAREA_VIII%3A609%2F25&vesselId=PWD-001). Start the Company demo at login first. It uses an isolated backend on port 8815; the preserved prior build remains available on port 4213 for comparison.

## Mobile map panels

The shared `MaritimeMap` overlay owns a responsive panel context. Below 700px, existing inspector headers expose Layers and Timeline. Each opens the existing workspace controls in a bounded modal; the chart, selected vessel/option and filters stay mounted. Escape/Return restores the initiating control. Desktop composition is unchanged. No second layer or selection state is introduced.

Actual local visitor checks passed at 1366×768, 390×844 and 360×800 using ordinary pointer hit testing. They selected an owned vessel, changed Vessel traffic, reopened Layers, returned to its inspector, opened Timeline, closed fleet review and reopened Layers. The narrow checks included enlarged text and no page-level horizontal overflow. A first attempt stopped at an unavailable old backend before any feature interaction; it is excluded from product validation counts. The successful run used isolated backend state. TypeScript, changed-file lint and an isolated production build passed for the shared panel repair.

## Clock inventory and decisions

The starting scan reproduced five direct OS reads and 77 unjustified `wall_now` sites. The static audits and their domain coverage are unchanged. After repair, both lists are empty.

| Timestamp meaning | Clock and preserved boundary |
| --- | --- |
| Source-quality age, forecast inspection, daily shadow analysis, feedback inspection/consumption, shipping exposure, restriction applicability and call target validation | One explicit aware query or `world_now` fallback. Pinned scenarios/replays cannot silently evaluate against today's wall. Later receipt/outcome knowledge is withheld from earlier inspection. |
| Provider collection attempts, network completion, cache cadence and first extraction availability | `wall_now`, with a nearby specific rationale. Publication, observation, product date and first receipt stay separate. Unchanged content retains its first availability. |
| Company/Port live-only continuation and approval | One actual operation instant, after the existing live-mode authority boundary. A replay cannot authorize continuation or extend source validity. Fleet-triage operational receipt age remains distinct from simulated traffic replay. |
| Visitor credentials, operator declarations, call identity creation and simulated-action recording | Actual wall receipt/expiry. Scheduled passage and simulated target times remain separate domain fields. |
| Public seed import and research report generation | Actual import/report audit time. Historical source rows, model evaluations, rejected artifacts and dated hosting packages are not regenerated. No neural/RL experiment was run. |
| Camera frame validation | One aware supplied query instant or pinned world fallback. Reference/frame ordering and original captured times remain unchanged. Tests use labelled synthetic pixels, not real footage or camera authorization. |

The complete world-clock suite passed, including both formerly failing static audits. Coverage and assertions remain enabled. New behavioral checks cover replay/scenario isolation, actual visitor expiry, future receipt/outcome filtering, camera frame bounds and original seed availability. Model report generation uses an audit clock without retraining or rewriting candidate artifacts.

## Official source qualification

The selected family is Indian Naval Hydrographic Department **NHO NAVAREA VIII**, discovered through its [official warning catalogue](https://www.hydrobharat.gov.in/hi/web/guest/navarea-warnings). The actual [in-force PDF](https://www.hydrobharat.gov.in/documents/d/guest/in-force-navarea-viii-warnings-2) returned HTTP 200. An independent bounded adapter refresh retained the same 65,758-byte response. SHA-256: `e216905fa5edf106a6bae93a42256a3b34a72280b28a930cc189f75c2667f518`. Initial research receipt was `2026-10-30T04:16:32.362781+00:00`; runtime source receipts and immutable originals are retained separately under ignored local research storage.

The document explicitly says **warnings in force as on July 7, 2025**, date only. It is historical for the present query even after a successful new download. HTTP Last-Modified and catalogue access do not upgrade that date. The adapter discovered 65 provider notice identities across 10 extracted pages, retaining unsupported entries as unsupported.

One reviewed mapping is `NHO_NAVAREA_VIII:609/25`, page 8: Paradip lighthouse DGPS transmission reported off air. Its issuer DTG is `031001Z/JUL 25`, resolved to July 3, 2025, 10:01 UTC; this is not an established publication instant. The point `20.2553333333, 86.6563333333` identifies the issuer's named navigation-aid station, not a route, port boundary or closure polygon. The port relationship is INPRT. A future operator-declared named-aid passage is a review relationship, not observed AIS or proof of future aid condition.

The bounded alternative review inspected JNPA's official homepage, marine catalogue and dated operational update. The October 6/7 report describes normalization after earlier congestion; it supplies no new future closure. General marine reference material is not converted into restrictions. No operator message, access-control workaround or paid/API registration was used.

No product-specific blanket republication licence was established in the inspected NHO catalogue. Liferay website-code notices do not license the hydrographic publication. PortWatch exposes attributed metadata, issuer links, page references, clocks and hashes; full bulletin wording/PDF bytes are not publicly served. This is the selected application scope, not an invented legal prohibition or permission. Local originals remain retained for research audit.

**Current-source numerical acceptance remains pending.** This reviewed family has no qualified closure/access-window calculator. Historical/current date classification, a completed software demo or a cancellation cannot establish present navigation-aid condition, actual access, delay, fuel, cost, safety benefit or real outcome.

## Source lifecycle and decision dependencies

`indian_notices.py` discovers official in-force product links with bounded HTTPS hosts/redirects, timeouts, one transient retry, size/page bounds and conflicting-product refusal. Explicit backend refresh is a role-checked POST; source/worklist/audit GETs read retained state only. The existing intelligence worker can collect this family with `PORTWATCH_NHO_ENABLED=1`; it defaults off and adds no worker, task or host automation. Existing weather reconciliation configuration is unchanged.

Provider identity, source-document hash, semantic interpretation, parser version and receipt/check clocks are separate. Unchanged checks preserve first availability; semantic revisions, reversions and parser changes retain predecessor lineage. Catalogue snapshots support historical views. Omission means NOT_LISTED, not cancellation. Explicit cancellation remains source status, not actual restoration/clearance. Failed/malformed responses retain last good evidence and report failure. Hash-missing/corrupt originals cannot support an active binding.

Source-date qualification is conservative: a date-only product must match the UTC query date and have a successful check within six hours to support a new context review. This is an application review rule, not an invented exact publication/effective interval. A qualified new in-force product can confirm an older individual warning; the warning's issue date alone does not expire it.

`notice_catalogue.py` is a small retained read seam for NAVCEN and the new NHO family. Eastham keeps its dedicated lock/tide endpoint and calculator. Indian context never enters a bridge/lock opening formula. Existing source registry and NAVCEN archive/deep-link contracts remain available.

An explicit Company declaration supplies owned vessel, current call, named aid, direction, INPRT destination, aware future passage and onward hours. Its resulting destination/ETA are **operator assumptions**, with no notice-caused numerical delay. Destination-only association remains a possible source lead. A completed call requires an explicit distinct next call; ETA edits do not invent call identity.

The existing queue has one row per owned call. Qualified, applicable but unconsumed notices add separate Company source-review actions without changing workflow next-role or category ordering. Consumed source changes produce reassessment, with exact revision IDs, first availability, changed fields and remaining unknowns in existing disclosures. Multiple reasons do not multiply voyage counts or combine heuristic source scores with cargo slack/money.

The original input editor explicitly acknowledges each exact qualified source revision. `sourceReviewBindings` freeze metadata, latest confirming original hash, product date, source check, operator declaration and context-only calculation role in the existing comparison evidence. Hourly weather and declared passage/cargo assumptions retain their equations. Continuation checks original integrity, consumed revision/status, six-hour frozen receipt, declared call/plan and future passage. A linked successor must explicitly review all consumed identities; it cannot silently drop one. Earlier approvals/advisories stay inspectable and an unapproved successor never replaces the approved plan.

`GET /intelligence/indian-source-audit?noticeId=…&asOf=…` uses the same retained as-of notice projection as the inspector. It exports public metadata only, with no archive path, credential or full PDF; later-known revisions remain unavailable to earlier queries. Real resolved operational targets stay zero.

## UI and validation

[REA reference review](UI_REA_REFERENCE_REVIEW.md) records all five requested references, actual Evidence IDs, public-access limits, the optional Windy layout observation, matched screenshots and three bounded interaction improvements. No unavailable authenticated UI is claimed as observed.

The consolidated 17-file backend run reported **267 passed**, including complete clock audits, source lifecycle, triage, current-input recovery, NAVCEN, weather reconciliation/shadow and shared feedback. After final malformed-selection/coordinate guards, **40 focused tests passed** across Indian source/workflow, recovery and triage API; these overlap the consolidated run and are not independent extra samples. The existing Starlette/httpx deprecation warning remains. Repeated source/queue GETs preserve store hashes and do not fetch providers or create decisions.

Actual-source browser checks inspect the historical PDF metadata/hash, download the matching audit, declare a fictional owned Paradip approach and follow its exact current-input link. The retained-error test deliberately injects a labelled 503/read failure and fake refresh completion; this tests UI recovery, not a real provider outage. Fixture queue checks preserve exact option/call links, filter/paging return, signed values, separate Company source responsibility, structured changes and orientation behavior.

The final combined compiled-preview browser run reported **30 passed** at 1366×768, 390×844 and 360×800, with retries disabled. It includes exact-link/reload/return cases, source audit parity and read-error retry, ordinary Layers hit testing with an open inspector, enlarged text, all four role workspaces, retained visitor identity, timeline access, God’s Eye globe rendering and return to the same mounted maritime chart. Matched old/new revision screenshots use the same fixture projection and disclosure state. Earlier attempts exposed an unavailable baseline server, a desktop startup timeout and a test navigation race after Admin sign-in; the baseline was started, startup was checked explicitly and the test now waits for the role redirect. The clean combined result follows those corrections; failed attempts are retained in ignored logs rather than counted as passes.

A separate QA-only backend on port 8816 carried **synthetic source and weather fixtures** through Company approval, actual process termination/restart (PID 59212 → 15584), Port review/issue, Vessel acknowledgement/acceptance and the labelled simulated outcome. It recovered the exact chosen option, original binding and environment hash `e74eff949ac561a7565604a1d989a40c077c155df4bdb807d349e09ca385af26`. Advisory `ADV-INPRT-7AEC7734DE` retained that evidence. Retry identities and second-visitor refusals passed. The QA processes were terminated afterward. This is software/recovery evidence; it does not qualify the historical NHO bulletin or resolve actual shipping targets.

TypeScript, changed-file lint and the isolated production build pass. All **eight protected role/twin sources match `e906f6a`** after line-ending normalization; all 260 frontend TypeScript/TSX sources match the isolated build copy. Research evaluations/artifacts, stronger baselines and both rejected model candidates are preserved. No training, adoption, FX valuation, booking or autonomous approval was introduced.

The isolated QA server disables automatic collectors to avoid duplicate shared collection during tests. Existing backend weather reconciliation and learning/adoption code remain intact; no host automation or research run was started for this milestone.

The October 26 backend package, frontend package and public-seed manifest retain SHA-256 values `cb32aefab03d6f84fbd0defa0fe733250a63687e4a78606324a5cd646ad0c9fe`, `d6c4a99e0ee377f513ef4924bbc827402671e8c9a20dec3d3d98372f21257746` and `d00aa539dbbe96fb18777b24fb0c65e48fa59602d918969f56aeb5c6f9cb1587` respectively.

Runtime evidence, private visitors, QA screenshots/builds, debug logs and the 19 unrelated CSV changes remain outside source commits. No hosting, billing, public alias or production-volume action is part of this work.
