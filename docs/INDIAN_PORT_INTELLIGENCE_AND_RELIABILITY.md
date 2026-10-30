# Mobile map access, clocks and Indian-source review

October 30, 2026. Local work from `2b6120236b136d3975d2bfa8b7824eabd832eb3f` on `feat/portwatch-restored-intelligence`. Hosting remains deferred. The eight restored role/twin sources and the historical October 26 hosting package remain protected.

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

The complete world-clock suite passed (25 tests), including both formerly failing static audits. A 73-test focused run covered world clock, new wall/domain boundaries, public-seed import and existing authority families. A separate 180-test integration run had 179 passes and one outdated clock-injection fixture; its route now correctly uses a world query. Follow-up tests preserve the same as-of, future-evidence and read-only assertions. These runs overlap and are not added as independent evidence. Final integrated counts are recorded after the remaining source/UI phases.

## Source and UI phases

Source qualification and the reference-guided UI phase continue in this milestone. Current-source numerical acceptance is not established by the clock/mobile repair. Retained official originals, supported semantics, source dates, lifecycle bindings and final validation will be documented here with the integrated change. The reference review will be recorded in `UI_REA_REFERENCE_REVIEW.md`.

Runtime evidence, private visitors, QA screenshots/builds, debug logs and the 19 unrelated CSV changes remain outside source commits. No hosting, billing, public alias or production-volume action is part of this work.
