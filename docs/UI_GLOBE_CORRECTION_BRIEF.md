# PortWatch UI and globe correction — implementation handoff

**Superseded after product review on October 9:** the user rejected the resulting local preview and wants their preferred pre-branch application preserved. Follow [Restore and extend](RESTORE_AND_EXTEND_HANDOFF.md). The visual references and replacement-layout prescriptions below are historical review material, not the current design instruction. The exact preferred snapshot still requires identification.

October 9, 2026. The user rejected the Milestone A interface and globe. This is the immediate product correction, ahead of Milestone B in `PORTWATCH_IMPLEMENTATION_PROMPT.md`. The larger intelligence and learning goal remains intact.

## Assignment

Repair the existing application's visual and navigation regression. Keep the isolated demo sessions, persistence, role permissions and working advisory chain. Restore real role screens and improve the global renderer. Deliver a reviewable application preview showing the actual rendered scenes before treating this recovery as accepted or promoting another production release.

The previous implementation brief specified useful workflows but did not anchor visual acceptance tightly enough to the original application. This brief supplies those anchors. A passing click test or a `data-ready` renderer flag does not establish visual quality.

## What the review actually found

The live entry, Company and Port demos were inspected in the browser. The published Admin screenshot and earlier role screenshots were compared with their source code.

| Finding | Evidence | Consequence |
|---|---|---|
| Demo entry replaces the existing application screens. | `AppShell.tsx` returns `<DemoShell />` for demo mode without rendering its `children`. | The original Fleet Command, bridge, national command and other route components never appear to demo visitors. |
| Several routes are section selectors inside the same page. | `DemoShell.tsx` maps route suffixes to `demo-*` elements and `scrollIntoView`. | Cargo, forecasts, weather and learning navigation can feel like different labels for one long form rather than real product views. |
| One layout dominates all roles. | Shared fleet cards, globe/twin slot and long inspector in `DemoShell.tsx`. | Role switching changes content, but loses much of the original role-specific composition and interaction. |
| The global scene uses the bundled Natural Earth II texture. | `IntelligenceGlobe.tsx` loads `Assets/Textures/NaturalEarthII`; the live Company view shows a bright pastel relief globe and star background. | Its appearance conflicts with the dark operational interface and the intended richer global intelligence experience. |
| The selected voyage does not get a useful default framing. | Demo `focus` uses fleet centre `55,25`; globe focus uses a fixed altitude of 13,000,000 metres. | A small global sphere carries a selected route that should instead be inspectable at voyage scale. |
| Vessel symbols are circles with constantly visible outlined labels. | `IntelligenceGlobe.tsx` vessel entities use points and unconditional labels. | Vessel identity, heading and selection hierarchy are weak; names crowd the scene. |
| Panels dominate the desktop. | At the inspected 1280 × 720 viewport, fixed 280/370-pixel side columns leave roughly half the width for the scene. | Forms and explanatory copy crowd out investigation. Several bottom notes overlap in the scene. |
| The Port scene is presented in a constrained central slot. | Live Port view and shared demo layout; the existing twin component is reused. | The dark schematic twin needs better framing, lighting and inspection. Reusing a component alone does not make the presentation successful. |

These are specific product and architecture findings. Do not reduce the correction to a font swap, different border radius or a new landing-page headline.

## Use the earlier application as the visual baseline

Inspect these actual local screenshots before editing:

- [Earlier national command](../india-portwatch-terminal/qa/shots/national-command-1366x768.png).
- [Earlier global consequence view](../india-portwatch-terminal/qa/shots/x/global-eye-1366x768.png).
- [Earlier vessel bridge](../india-portwatch-terminal/qa/shots/vessel-konkan-1366x768.png).
- [Earlier port view](../india-portwatch-terminal/qa/shots/port-chennai-1366x768.png).
- [Rejected Company release](../work/demo-A-primary-validation/company.png).
- [Rejected Admin release](../work/demo-A-primary-validation/admin.png).
- [Rejected Port release](../work/demo-A-primary-validation/port.png).

The earlier images establish layout, map prominence, typography, operational symbols, inspectors and timeline. Their simulated tracks, historic clocks, source labels and numeric values are not current-data requirements. Preserve honest data semantics while restoring the interface quality.

The direction is a spatial operations console: a large connected scene, compact chrome, purposeful overlays, distinguishable asset types and a selected-object inspector. The four roles retain their own questions and views. Global Intelligence remains a richer global scene connected to those workflows.

God's Eye's upstream includes imagery and interaction modules as well as a viewer lifecycle. Audit the installed exports and source rather than equating the current wrapper with the complete upstream experience. [Upstream reference](https://github.com/bilawalsidhu/gods-eye-view).

## 1. Restore the actual role screens

Start with `src/components/app/AppShell.tsx`, `src/components/demo/DemoShell.tsx`, `src/routes/company/overview.tsx`, `src/routes/vessel/overview.tsx`, `src/routes/port/overview.tsx`, `src/routes/admin/radar.tsx`, their child routes and shared service hooks under `india-portwatch-terminal`.

Remove the architectural dependency that discards route children in demo mode. Reuse the normal application chrome and route components where appropriate. The demo boundary belongs in the session/data/service layer; it should not require replacing the entire frontend with a second application.

Do not simply delete the `DemoShell` branch and enable the old screens. Their hooks currently query operational endpoints, and the frontend deliberately rejects such requests from demo sessions. Map the required contracts onto demo-scoped services or explicit data providers first. Preserve server enforcement. Adapt only the contracts these screens actually use, with useful typed data, rather than manufacturing an unrestricted mirror of every operational endpoint.

Reuse the backend demo world for vessel selection, comparisons, proposal, resource review, advisory, acknowledgment and outcome. Move those existing controls into their proper screens. Preserve visitor isolation, scope, reset, refresh, logout and query-cache separation. Never satisfy missing demo data by falling through to protected operational writes or real administrator authority.

Real routes must display their promised work:

| Screen | Composition and primary task |
|---|---|
| Company overview | Fleet scene and ranked interventions; select a vessel, inspect a deadline and enter a voyage comparison. |
| Company cargo/routes | Cargo readiness/connections or route alternatives with relevant geometry and selection, not a scroll to a paragraph. |
| Vessel bridge | Assigned ship, route/weather ahead, nearby relevant contacts, follow control, passage timing and advisory response. |
| Port overview | Port arrivals, queue/berth context and local geography; resources and forecasts are available through focused inspectors. |
| Port twin | A large inspectable schematic facility, berth/resource selection, timeline and actual policy comparison. |
| Forecast/weather screens | Appropriate charts/layers, horizon and variable controls, target/observation clocks and missing/stale state. |
| Admin command | Network scene, ranked ports/exposure, action queue and selected-port investigation. |
| Admin models/learning | Model/experiment status and the existing benchmark evidence, with real tables/plots and inspection rather than one disclaimer paragraph. |

Do not duplicate every screen from scratch. Use existing route components and shared primitives, extending the supported demo contracts as needed. Show meaningful empty states for genuinely unavailable features; do not invent model training, live AIS or camera coverage.

## 2. Recompose the scene and controls

Use the earlier compact top strip, navigation rail and status/timeline treatment as the starting point. Consolidate the current two-row header where possible. Keep role switching, demo state and exit obvious without making them the dominant visual elements.

The map/globe should extend across the working area behind movable or collapsible operational panels. On a 1366-pixel desktop, a roughly 48-pixel navigation rail and a roughly 300-pixel focused inspector are reasonable starting dimensions. Additional asset/signal panels should collapse and expand deliberately. Check the unobscured area when framing a route; full-width canvas alone does not guarantee useful visibility.

Provide search, layers, fit selection, follow, north-up and view mode through a small scene toolbar. Use a compact shared timeline where the data supports time inspection. Avoid placing a large scene heading over the geography. Keep attribution readable and present, but separate it from overlapping status/provenance strips.

The inspector should default to the selected asset/event and its most useful result. Open scenario parameters on demand; after comparison, prioritize options and consequences. Evidence, dates, constraints and source detail remain one action away. Do not bury the primary action below long implementation explanations.

Keep a persistent concise Demo label, source/age labels and object-specific simulation markers. Put detailed technical provenance in its drawer. Keep these meanings accurate; reducing repeated prose does not permit disguising fictional data.

Reuse the application's existing design tokens and primitives. Use legible body/control text, tabular numbers and a clear type hierarchy. Reserve amber/red for attention and risk; use a consistent selection treatment. Do not introduce decoration, marketing cards, glow or motion that competes with operations.

## 3. Upgrade the globe itself

Global Intelligence must retain an actual interactive 3D scene. Improving regional role views must not remove the broader globe or narrow the original vision to an India-only map.

Implement a considered basemap strategy: a clear dark nautical/context style for operations, and a properly attributed imagery view for geographic inspection when an authorized source is available. Investigate the installed `gods-eye-view/maps/imagery`, maps catalog/controller/defaults and existing map assets. Natural Earth II can remain a bundled fallback; it should not define the main visual presentation. Verify imagery source permissions and actual deployment behavior. Do not promise terrain, photogrammetry or port detail that is not connected.

The original `MaritimeMap` basemap uses clipped regional geometry. Reusing its style is useful; claiming that regional asset is a global coverage source is not. Use appropriate global geometry or provider coverage for the globe.

Default scene rules:

- Company: frame relevant fleet lanes and selected voyage; fit the actual route after selection/comparison.
- Vessel: frame the assigned vessel and passage ahead; a follow mode is optional and visibly active.
- Port: frame the selected port/facility; reserve global framing for a deliberate global-context action.
- Admin: frame the national/network extent, with a clear global view option.
- Global Intelligence: start with a useful world/region view, then frame the event, asset or exposed route selected by the user.

Replace fixed focus altitude with geometry-aware bounds and padding for visible panels. Preserve manual pan/zoom unless the user selects a new object or invokes fit/follow. Data refresh should not continually reset the camera. Respect reduced-motion settings.

Render vessels as clear vessel/heading glyphs with appropriate size and selected emphasis, borrowing the existing maritime symbols where feasible. Distinguish ports, events, vessels, weather and cameras by shape as well as color. Show labels for selection/hover and at suitable zoom; use decluttering and priority rules. Hide occluded far-side labels rather than allowing an all-depth symbol to appear through the Earth.

Route alternatives need restrained styling: current route, selected candidate, rejected/infeasible option and hazard geometry have distinct meanings. Use the existing decision geometry, not attractive arcs invented by the renderer. Add spatial layer legends. Weather layers should show actual spatial data when connected; a blue point is not a wave field.

Keep one active scene renderer and clean up resources when switching lenses. A 2D nautical lens can serve operational tasks alongside a 3D global lens, with shared selection/time. Show a useful map fallback when WebGL or imagery fails. A static image, prerecorded flythrough or mock screenshot cannot replace a functioning map.

## 4. Correct the port twin presentation

Retain the twin's physical/resource constraints and existing simulation. Fit the facility within the unobscured scene, improve lighting/material contrast, show berth identifiers and resource/occupancy legends, and expose selection without requiring users to guess which low-contrast block is interactive.

Separate arrival queue, berth occupancy and resource allocation into useful inspection states. Show before/after plans and their timeline when a policy is compared. Keep geometry schematic unless surveyed data exists. Do not spend this correction creating photorealistic cranes while the berth plan remains unreadable.

## 5. Review and release criteria

The first deliverable is a bounded functional preview: entry, Company overview and one improved global investigation view. It must use actual demo/API state and the real renderer. Provide side-by-side images against the earlier screenshots. This is a design checkpoint within the current implementation, not a request to generate another full product roadmap.

Once the composition is accepted, carry the shared shell and data adapters through Vessel, Port and Admin. Preserve the cross-role chain throughout.

Verify at 1920 × 1080, 1366 × 768 and 390 × 844:

1. Scene is rendered with usable geography and meaningful camera framing; primary labels do not collide with each other or panels.
2. Selection highlights the correct asset, inspector and route; changing an option updates geometry.
3. Cargo, weather, forecast and model navigation display their actual screens.
4. Role-specific compositions are visibly distinct and preserve shared demo state.
5. Demo/API scope, visitor isolation and production authorization still pass negative checks.
6. Compare → submit → review → approve → acknowledge → demo outcome still works.
7. Mobile uses one renderer and a scene with an accessible sheet/panel; controls remain reachable without overlapping attribution.
8. Slow imagery, source failure and WebGL failure retain usable navigation and comparisons.
9. Relevant backend tests, TypeScript, changed-source lint and build pass; avoid unrelated broad rewrites.

Capture screenshots after imagery/render readiness and inspect them at normal scale. Do not accept a screenshot solely because a canvas exists. Report the visual decisions and remaining gaps, then release through the existing hosting workflow when the required product review and publication authorization are satisfied.

## Copyable starting instruction

Read this brief and `PORTWATCH_IMPLEMENTATION_PROMPT.md`. Treat the UI/globe correction as the immediate priority. Preserve the Milestone A demo backend and advisory chain, restore actual role routes through demo-scoped data adapters, and build a functional preview of the original map-focused application with an improved global scene. Do not advance to Milestone B or promote another production version before addressing the rejected visual result and presenting the concrete preview for review.
