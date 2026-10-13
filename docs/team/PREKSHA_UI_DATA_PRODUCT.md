# Preksha — richer original UI, data quality and trustworthy outputs

Prepared October 13, 2026. Owner: Preksha. Suggested separate branch: feat/preksha-ui-data-quality.

## Assignment and intended result

Improve PortWatch as a usable, detailed and interactive shipping product. Preserve the restored interface the user preferred, while improving information hierarchy, interactions, data contracts, source quality and the clarity of operational outputs.

This is product engineering with frontend design and data work. The user does not want another replacement dashboard, stripped globe, generic card grid or a research page substituted for the application. More detail should appear through useful selection, comparison, exploration and evidence inspection.

The desired experience remains:

    Global intelligence / port / vessel
        → relevant evidence and affected assets
        → forecast or conditional operational consequence
        → comparison of actions
        → role-specific review and advisory
        → observed or explicitly simulated outcome

The integration owner is developing the feedback and consequence engines. Your work makes the information feeding those engines more dependable and makes their outputs easier to understand and use.

## Branch starting point and coordination

Read [the shared work plan](D:/LogisticOptimization-_Capstone_168/docs/team/PARALLEL_WORK_AND_FEEDBACK_PLAN.md).

The shared base is feat/portwatch-restored-intelligence, created from main after the earlier deployment branch was merged. Fetch that remote branch and create your own branch from its tip. Record that exact SHA as your base. The older e906f6a commit is the restored-interface reference; the new shared branch contains the later application updates and these briefs.

Use a separate checkout/worktree and isolated development data. Do not switch the integration owner's active branch, reset its changes, rewrite pushed history or connect your preview to writable production stores. Read [frontend AGENTS.md](D:/LogisticOptimization-_Capstone_168/india-portwatch-terminal/AGENTS.md).

## Read and reuse

- [Latest release and limitations](D:/LogisticOptimization-_Capstone_168/docs/AUTHORITY_RESTRICTION_RELEASE.md).
- [Restoration intent](D:/LogisticOptimization-_Capstone_168/docs/RESTORE_AND_EXTEND_HANDOFF.md) and [full original brief](D:/LogisticOptimization-_Capstone_168/docs/PORTWATCH_IMPLEMENTATION_PROMPT.md).
- [Admin data screen](D:/LogisticOptimization-_Capstone_168/india-portwatch-terminal/src/routes/admin/data.tsx).
- [Weather verification panel](D:/LogisticOptimization-_Capstone_168/india-portwatch-terminal/src/components/intelligence/WeatherVerificationPanel.tsx).
- [Shipping intelligence panel](D:/LogisticOptimization-_Capstone_168/india-portwatch-terminal/src/components/intelligence/ShippingIntelligencePanel.tsx).
- [Operational notice panel](D:/LogisticOptimization-_Capstone_168/india-portwatch-terminal/src/components/intelligence/OperationalNoticePanel.tsx).
- [Decision panel](D:/LogisticOptimization-_Capstone_168/india-portwatch-terminal/src/components/decision/DecisionPanel.tsx) and [advisory screen](D:/LogisticOptimization-_Capstone_168/india-portwatch-terminal/src/components/advisory/AdvisoryScreen.tsx).
- [Source catalogue documentation](D:/LogisticOptimization-_Capstone_168/docs/DATA_SOURCES.md), [port registry](D:/LogisticOptimization-_Capstone_168/src/utils/port_registry.py) and [source products](D:/LogisticOptimization-_Capstone_168/src/portwatch_os/fabric/products.py).

## Scope ownership

Own source/data-quality diagnostics, normalized presentation contracts, runtime response validation for your components, UI polish, detailed inspectors and interactive comparison presentation.

Suggested new areas:

    src/ingestion/data_quality/
    backend/app/routes/source_readiness.py
    india-portwatch-terminal/src/components/data-quality/
    india-portwatch-terminal/src/services/data-quality.ts
    india-portwatch-terminal/src/types/source-quality.ts
    tests/test_source_quality_*.py
    docs/data_quality/

These are proposed areas. Reuse existing APIs and modules where suitable. Avoid creating a second independent source catalogue or replacing the established world/session store.

You can improve Admin Data and shared information components with focused changes. Shared decision/advisory panels and the intelligence panels are also active integration surfaces: agree the patch boundary with the integration owner before parallel edits, or contribute small components through a defined prop contract. Ananya owns twin geometry, renderers, transforms and geographic layer alignment. You own surrounding UI consistency and shared source-quality presentation.

## Milestone 1 — audit the real journeys

Record the present desktop and mobile experience before editing. Review all four roles, including:

- One-click demo entry, same-visitor role switching, refresh and return navigation.
- Map/globe selection, layer controls, asset search and time controls.
- Weather original/outcome/error inspection and pending-data explanations.
- Authority restriction applicability and declared-voyage inputs.
- Comparison, approval, advisory issue, acknowledgement/acceptance and outcome.
- Admin source status, errors, provenance and model candidate status.

Write a short, ranked issue list with the affected user action, screenshot/state and a specific proposed fix. Choose two high-value screens for the first iteration: Admin Data and one evidence/decision inspector. Include real interaction issues, not just colours and rounded corners.

Capture before/after at the same viewport, role, selected asset, clock and data state. Do not claim a visual improvement by removing the existing map, traffic, inspector or timeline.

## Milestone 2 — make freshness and quality intelligible

Build a consistent source-quality view with drill-down. Each source/product should expose, where available:

| Field | What the user needs to know |
| --- | --- |
| Receipt / last check | When PortWatch last obtained or checked the product |
| Observation / acquisition | When the underlying measurement or imagery describes reality |
| Forecast origin and target | When the forecast was available and what time it predicts |
| Event validity | Whether the event/restriction still applies |
| Coverage | Which ports, variables, areas and times are actually supplied |
| Completeness | Missing variables, partial periods and invalid records |
| Provenance | Original source, retained receipt/hash and derivation |
| Operational use | Context only, calculation input, scenario assumption or observed outcome |

A successful refresh does not make an old observation current. A current hazard feed does not make an expired event active. A source listed in a catalogue is not necessarily wired into this deployment.

Show a readable summary with targeted expansion; avoid a wall of technical fields in every operational screen. Important exceptions should remain visible without expanding. Never substitute zero for missing, unknown, withheld or not applicable.

Retain domain distinctions:

- Weather forecast, station measurement and ERA5 reanalysis.
- Actual AIS, deterministic simulated traffic and an assumed voyage declaration.
- Reported news, inferred asset exposure and a confirmed authority restriction.
- Economic observation, forecast, operator cost assumption and calculated cost.
- Verified geometry, imagery-derived geometry and illustrative 3D assets.
- Real camera recording, model-derived observation, reviewed evidence and simulation.

Use explicit statuses with their existing meaning. Add a product quality summary based on documented checks, rather than inventing a numerical confidence score from field completeness.

## Milestone 3 — improve the data models and contracts

Separate these entities instead of passing one loosely typed object through every screen:

1. Source receipt: provider/product, retrieval, original reference/hash, parse version and status.
2. Observation: variable/entity, value/unit, measurement period, source availability and quality.
3. Forecast/claim: origin, target, location, value/distribution, model version and source inputs.
4. Event/restriction: identity, effective period, affected geography/assets, applicability, revision and exceptions.
5. Decision basis: exact consumed versions plus declared/assumed inputs.
6. Outcome: target being evaluated, availability, measurement or simulation kind and links.

Preserve the existing backend semantics and record IDs. Use additive/versioned presentation DTOs with compatibility adapters. Do not silently rename ledger keys, migrate stored evidence, change approval meaning or reinterpret an unknown value.

Validate responses at runtime in the new data-quality/UI boundary. A TypeScript cast alone does not validate a server response. Prefer the project's existing schema approach; inspect installed dependencies before introducing another validation library. Provide useful malformed-response states and request cancellation/timeouts where the current client supports them.

Canonicalize ports through the existing registry, with reviewed aliases. Keep date-only precision, timezones, units and aggregation definitions. Distinguish hourly samples, preceding-hour precipitation sums, daily maxima and actual continuous measurements.

Add data-quality checks for duplicate entity/target IDs, invalid dates/coordinates, non-finite values, incompatible units, source age, missing retained originals and impossible availability ordering. Preserve rejected records with reasons in an audit artifact instead of quietly deleting them.

For Ananya, expose the geometry quality metadata she supplies; do not invent positional accuracy or change her coordinate transforms. For the integration owner's feedback loops, supply trustworthy source/target metadata; do not train reliability weights or decide whether a model should be promoted.

## Milestone 4 — improve the outputs and interactivity

Make comparisons answer the user's practical questions:

- What changed and which input/version caused it?
- Which ship/port/route/cargo is affected, and why does the source apply?
- What is reported, inferred, conditional or assumed?
- How do requested arrival, permitted/conditional access, waiting and overall schedule differ?
- Which quantities are unavailable, and what evidence would make them calculable?
- What action can this role perform next, and what is already approved or completed?

The current Eastham example reduces planned lock waiting from 14 h 42 m to zero while keeping the same total schedule shift. Preserve that distinction. Do not display this as time saved in delivery, confirmed lock access or reduced fuel use.

Provide compact side-by-side options, synchronized highlighting on supported maps/timelines, and an inspectable impact chain. Selecting an event should retain its context while selecting an affected asset opens the existing inspector. Restore back navigation and selected filters without creating a different visitor.

Improve forms with correct units, date/time precision, valid ranges, inline reasons and useful defaults. Make loading, partial source failure, expired evidence and linked refresh clear. Disable pending action submission and keep backend idempotency protections; a frontend button alone cannot enforce retry safety.

Use progressive disclosure for evidence and derivations. Keep important stale/simulated/conditional labels beside the relevant output, using concise text instead of burying them in long footnotes.

Make interactions keyboard-accessible, provide visible focus and descriptive button labels, and avoid colour as the only status signal. Preserve the desktop information density. On mobile, use closeable/scrollable inspectors with reachable controls; do not replace the original application with a new mobile shell.

## Milestone 5 — data coverage that helps the product

Audit the existing port-activity source for last actual observation, fetch status, mapping, coverage and export freshness. Work through a separate diagnostic/normalization path first. Retain the current data until a candidate refresh is checked and integrated. If the provider itself is delayed, report the delay instead of manufacturing current activity.

Inventory useful missing coverage across news, economic products, infrastructure, camera sources and spatial assets. Rank by operational relevance, reliable availability and integration effort. Coordinate new collectors with the integration owner, who owns those feedback/consequence pipelines. One quality improvement that repairs an actual missing or ambiguous field is preferable to adding many unconnected source names.

A public camera or imagery URL does not by itself establish permission to redistribute it. Record the product's actual access/attribution constraints. Do not place private feeds, credentials, operator files or visitor state into public assets or exports.

The source catalogue documentation is generated. Correct its underlying product/adapter metadata and regenerate it; do not maintain contradictory descriptions by editing only the generated table.

## Deliverables and acceptance

First PR: journey audit, concrete before/after previews for two screens, source-quality DTO and fixture states.

Second PR: reusable quality/evidence inspectors, runtime validation, normalized IDs/units/time semantics and read-only quality diagnostics connected to existing data.

Third PR: interaction and comparison polish, verified data-coverage improvements, exports with context, mobile/accessibility/failure evidence and a concise integration report.

Meaningful tests should cover malformed/partial responses, null versus zero, date-only and timezone handling, stale receipt versus stale observation, invalid event applicability and public/private boundaries. Browser checks should cover selection, comparison, refresh/recovery and one role handoff against the real development backend. Run TypeScript, changed-file lint and build checks.

Completion means users can investigate sources, understand the comparison and continue the original role workflow more easily. The map/globe, layers, timelines and operational density remain intact. No new accuracy or operational-savings claim is introduced by a UI change.

## Copyable starting instruction

Work on your separate branch from the shared current-release source commit. Read this brief and the shared plan. Audit the existing four-role application, then improve Admin Data and one evidence/decision inspector first. Preserve the restored visual identity, maps and workflows. Own UI interaction, source/data-quality diagnostics and presentation contracts. Coordinate shared panels with the integration owner and twin interfaces with Ananya. Deliver small PRs with screenshots, runtime validation, useful failure states and tested data semantics.
