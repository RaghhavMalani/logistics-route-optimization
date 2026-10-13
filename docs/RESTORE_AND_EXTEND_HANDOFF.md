# Restore the preferred PortWatch version, then extend it

October 10, 2026. This is the current implementation instruction following rejection of both the Milestone A UI and the local correction preview. It supersedes the replacement-layout instructions in `UI_GLOBE_CORRECTION_BRIEF.md`. The original product-improvement goal remains.

## User intent

The user liked their application before this branch and liked the original improvement plan. Restore that preferred application as the base. Add the agreed capabilities to it incrementally. Do not produce another interpretation of the interface, another stripped-down demonstration frontend, or another new product entry architecture.

The user confirmed `e906f6a6bd4388cd3c059b4d9a5de6759139528b` as the preferred snapshot, before the October recovery and redesign work. Restore its actual source and interactions. The user requires the restored application to be shown locally before further UI changes or publication. The local restoration checkpoint is documented in `RESTORATION_E906F6A_LOCAL_REVIEW.md`.

## Verified repository facts

The current branch is `fix/deploy-terminal-on-vercel`. Its HEAD is `e906f6a6bd4388cd3c059b4d9a5de6759139528b`, dated September 16, 2026. The October recovery/preview changes are in the working tree rather than later commits on this branch. This HEAD is now the user-confirmed restoration target.

Other saved references include:

| Reference | Date | Meaning |
|---|---|---|
| `523ba23` | September 16 | Parent from which the current deployment branch was created. |
| `e0c9628`, `feat/portwatch-x-world-twin` | September 16 | World-twin release-candidate branch. |
| `f890edb`, `feat/portwatch-agentic-maritime-os` | September 10 | Earlier agentic maritime application. |
| `3543c6e`, `feat/portwatch-digital-twin` | September 9 | Earlier digital-twin application. |

The frontend source difference between `523ba23` and `e906f6a` affects the failure-state panel and an Admin system route, rather than a full interface redesign. Merely switching between those two refs may not explain the version the user has in mind.

The existing Company, Vessel, Port and Admin route components are present in Git. The HEAD `AppShell` renders its route children within the original chrome and traffic provider. The original Global Eye has separate routes and substantial implementation history. The October demo initially bypassed these route children; the correction adapted some Company routes but introduced another scene presentation that the user also rejected.

## Restoration method

1. Identify the preferred revision from the user's answer, a named branch/commit, or a verified older deployment. If the answer is an earlier version, compare the saved candidates in isolated previews to establish the target. Do not make an aesthetic choice on the user's behalf again.
2. Preserve the current work and data before restoration. Use an isolated snapshot/checkout or targeted file recovery. Do not reset the dirty repository, rewrite published history, delete collected evidence or overwrite production state.
3. Render the preferred version as it actually was. Match its navigation, role screens, map behavior, layers, asset density, inspectors, timeline, interactions and entry experience. Do not present a newly reconstructed approximation as restoration.
4. Reconcile it with the useful new backend work. Keep verified operational sessions, private-data boundaries, isolated demo sessions and the advisory chain. Expose those services through the restored screens; avoid replacing the screens to simplify the API integration.
5. Review the restoration against the confirmed target. If an old capability used simulated data, keep its simulation label while preserving the useful behavior. Restoring appearance does not justify relabelling demonstration traffic as observed AIS.

The implementation recovered ten changed frontend screen files directly from the confirmed commit, retaining newer authentication and service adapters. The recovered screen bytes match Git; a preservation manifest checks the backend and evidence. A separate local review process renders all four original role workflows. It has not reset the repository, switched branches or published a replacement. The isolated demo services are now connected through adapters inside the original role screens. See `RESTORED_APP_CAPABILITY_REVIEW.md` for the implementation, actual experiments, local verification and remaining source-dependent work.

## The original improvement plan still applies

The goal is an improved PortWatch application that can be shown through a public link at capstone and research events, retaining Company, Vessel, Port and Admin workflows.

- **Weather learning:** retain the original five-day prediction, match later observations correctly, learn recurring residuals/provider reliability, and use validated corrections in later forecasting and affected recommendations. Separately learn errors in the predicted operational effect of weather. Use supervised correction for full-information prediction error; use bandits/RL for actual source-selection or sequential operational choices.
- **Broad God's Eye integration:** integrate global intelligence into the restored application, including weather/ocean, hazards, ships, aircraft/satellite context, news, economic signals, roads, rail and infrastructure. Selecting a signal should expose affected assets and existing decisions. Selecting a vessel or port should retain its existing workflow. The globe is an additional connected capability, not a replacement for the whole application.
- **Port cameras:** connect authorized viewpoints, retain their timestamps and coverage, then derive evaluated observations of berth occupancy, movement, queues or interruptions. Link them to port planning. Missing feeds constrain camera work, not every other improvement.
- **Neural upgrades:** implement specialist residual correction or expert fusion with defined targets, source-quality/missingness inputs and chronological evaluation. Audit the existing TFT before duplicating it. Explore network propagation where suitable labels and graph semantics exist.
- **Decision-policy/RL upgrades:** reuse the constrained simulator and existing policies. Train and evaluate a scoped candidate against strong baselines on separate scenarios/seeds. Show candidate/deployed status and actual results; preserve operator review.
- **Supporting engineering:** repair forecast freshness, evaluation leakage, calibration and useful intervention cases. Maintain source provenance, reproducibility and measured limits without making collection reports the product.

Preserve the full technical requirements in `PORTWATCH_IMPLEMENTATION_PROMPT.md` where compatible with this restoration instruction. Its prior layout prescription and immediate milestone order do not override the user's rejection or establish the preferred visual baseline.

## Current local deliverable and remaining work

The four demo roles now use the original screens and the visitor-owned terminal adapters. The original Company/Port/Vessel decision and advisory chain is verified. Rich surrounding traffic, maps, weather layers, inspectors, timelines and the port twin remain in place. The additional God's Eye globe connects the same traffic and original selections, with bounded aircraft, orbital, earthquake, cyclone and infrastructure sources.

Forecast refresh/export freshness is repaired and source lag is reported honestly. Real archived weather forecasts are displayed, but later matched observations are not yet available to validate correction. Actual neural fusion and constrained sequential Q candidates have been trained and evaluated; both were rejected and neither was promoted. Camera registration/playback, offline occupancy evaluation and reviewed evidence entering an original port-twin scenario are implemented. A real footage-based demonstration still requires authorized recordings and reviewed labels.

Read `RESTORED_APP_CAPABILITY_REVIEW.md` for exact source coverage, scores, artifacts, checks and limitations. Continue source-dependent work inside this application: obtain authorized camera inputs; collect available later weather outcomes; complete supported regional hazards, agency transit and credential-dependent layers; evaluate broader simulator stress families and new untouched promotion periods. Do not replace the application or publish this local review without the user's publication instruction.

## Short instruction for the implementation chat

Keep the restored `e906f6a` application as the base. Read `RESTORE_AND_EXTEND_HANDOFF.md`. Preserve the connected isolated demo adapters, original role screens, rich maps, layers, timelines, interactions and advisory chain. Read `RESTORED_APP_CAPABILITY_REVIEW.md` before continuing the weather-learning, broader intelligence, authorized camera demonstration and candidate evaluation work. Do not reset the repository, remount the replacement DemoShell or substitute a reduced scene.
