# PortWatch X product recovery brief

Prepared October 8, 2026 after reviewing the user's original brief, the published `/explore` page, and the existing workspace code. This is an implementation plan for the other chat; it does not change the deployed application.

## Product objective

Build one explorable global intelligence workspace that connects worldwide signals to shipping decisions. The public link must let an event visitor experience that workspace immediately. Research results and evidence downloads support the product and remain available under `/research`.

The original scope includes broad God's Eye spatial intelligence, news, economics, weather, vessels, infrastructure and port CCTV, coupled to forecasts, shipping optimization and learning from subsequent observations. A successful deployment and passing download tests do not by themselves satisfy this scope.

## Verified mismatch

- Anonymous users are redirected to `/explore`, whose first screen is an editorial introduction followed by collection tables and the GLAD YOUNG case. It contains no globe workspace.
- The existing `GlobalEyeScreen` and its `IntelligenceWorkspace` are reached through operator routes. Their layouts use role guards that send anonymous visitors to sign-in.
- The current integration imports God's Eye application/viewer lifecycle, earthquake modules and camera media-type helpers. This is a partial integration, not the broad layer coverage requested. The backend explicitly lists flights, satellites, transit, roads, infrastructure, fires, radio, camera projection and an Indian Ocean cyclone adapter as pending.
- Economics is cached context rather than a fitted operational impact model. The camera registry has no preconfigured feeds; a registry/player alone does not implement camera-derived berth or queue observations.
- The public forecast inspected on October 8 had an October 2 origin and October 3 target. Its stale warning is honest, but collecting new berth reports does not refresh those forecasts.
- The public diversion calculation is extra distance divided by assumed speed, then cost per day. It is not a vessel-specific constrained optimization run.

## Reuse the existing foundations

Build on the existing globe lifecycle, maritime map, world selection/time state, event cascades, decision panel, forecast and weather-feedback services, camera registry and verified identity. Preserve archived reports, frozen forecasts, release manifests and stable research links. Add an explicit public projection of these capabilities rather than granting visitors an operator role or removing private route guards.

Useful starting points:

- `india-portwatch-terminal/src/routes/index.tsx`
- `india-portwatch-terminal/src/components/globaleye/GlobalEyeScreen.tsx`
- `india-portwatch-terminal/src/components/intelligence/IntelligenceWorkspace.tsx`
- `india-portwatch-terminal/src/components/intelligence/IntelligenceGlobe.tsx`
- `india-portwatch-terminal/src/world/WorldContext.tsx`
- `india-portwatch-terminal/src/components/decision/DecisionPanel.tsx`
- `backend/app/routes/intelligence.py`
- `backend/app/routes/public_research.py`
- `src/portwatch_os/learning/weather_feedback.py`

## First milestone: the actual product on the public link

Deliver a working, globe-led public workspace using the existing data and components. Complete this milestone before making another collection report the main product release.

| Area | Required experience |
|---|---|
| Entry | `/` and `/explore` open the interactive intelligence workspace. Research and operator access remain visible secondary navigation. |
| Main scene | A viewport-filling globe/map shows ports, available vessels/tracks, events and routes. Layer controls and selection share one state. Use one active renderer. |
| Left rail | Search, source-backed alerts and layer controls for vessels, news/security, weather, economics, infrastructure and cameras. Each layer exposes actual coverage and refresh state. |
| Right inspector | Selecting an event, ship or port reveals the relevant signals, forecast, linked assets, assumptions and available shipping options in the same workspace. |
| Time | One control distinguishes current observations, historical replay and forecast projection. Source and target dates follow the selected time. |
| Public interaction | Visitors can explore public information and run isolated scenarios. Private feeds, operational writes and approvals retain verified authorization. Scenario controls cannot alter the shared collector or operator world. |
| Research | GLAD YOUNG, historical metrics, hashes and PDFs stay reachable through contextual evidence links and `/research`; they no longer dominate the homepage. |

First-milestone acceptance is a visitor journey: open the public URL without an account, inspect the globe, select an event, see affected ports/routes, select a port or available vessel, inspect its forecast, and compare a scenario with an alternative. The scene must update during those actions. Fresh data is dated; stale or unavailable data is explicit. A clearly labelled historical demonstration can exercise missing live coverage without impersonating current conditions.

## Complete the intelligence coverage

Create a capability matrix against the pinned God's Eye revision and the current upstream repository: https://github.com/bilawalsidhu/gods-eye-view. For each module, record its source, actual geographic coverage, credentials, update cadence, timestamp semantics, public display rights, adapter and shipping connection. Distinguish code reuse from an operating data feed.

Integrate the broad spatial layers alongside PortWatch's news and economics in the shared scene: ships, aircraft, satellites, weather fields, hazards/fires, roads/transit/infrastructure and available public cameras. An upstream implementation or screenshot is not proof that its provider covers an Indian port. Signals with no established operational relationship remain investigable context while that relationship is developed.

Cluster related news into one incident, then connect that incident to locations, exposed lanes and relevant assets. Economics should connect explicit fuel, currency and freight assumptions to scenario costs. Weather needs fields on the globe and per-port inspection, including Indian Ocean coverage. A port inspector should combine weather, arrivals, berth context, inland access and camera viewpoints.

For CCTV, connect an authorized, identified real viewpoint when available and show its coverage, health and actual frame time. Develop berth occupancy, vessel movement, queue and crane-activity observations against labelled footage. Recorded footage can support a clearly labelled development demonstration; it must retain its recording date. Measure detection and coverage limits before camera outputs enter shipping recommendations. An unavailable feed must never be replaced by invented live footage or observations.

## Connect signals to useful shipping choices

Expose a consequence path in the scene: signal -> affected route/port/vessel -> projected operational effect -> options -> observed outcome. Each computed hop identifies the input it consumed and its model or stated scenario assumption.

Run the existing constrained decision machinery for the selected vessel or an explicitly parameterized public scenario. Compare keeping the plan, adjusting speed/departure, waiting and feasible diversion under the same assumptions. Show distance, ETA, fuel/cost, berth constraints and uncertainty when the relevant models support them. Preserve timing gates and unavailable alternatives. Source-backed exposure, a modelled effect and a measured outcome need distinct labels.

The demonstration should let a visitor change a weather or closure assumption and see the compared routes and consequences change. Report simulation results as simulation results; only later operational evidence supports realized accuracy or savings.

## Deliver the requested model work

Keep development moving while public-port outcomes accumulate. Historical training and simulator experiments do not require the prospective cohort to finish; operational claims still require appropriate measured outcomes.

1. Finish the weather feedback experience: select a port, variable and five-day forecast; inspect original forecast, later observation, residual, proposed/accepted correction and its effect on the next model run. Surface input freshness and missing variables. Match with an observation rather than a newer forecast. Refresh dated forecast outputs as a separate pipeline job from public report collection.
2. Build a small learned fusion model with a defined job: combine weather, arrivals, capacity, event and economic representations using horizon, source age, missingness and previous error. Wire its output into forecasting. Compare with the existing ensemble and simple baselines on chronological partitions; expose its evaluated status and contributions. Additional networks need defined targets rather than an automatic network at every boundary.
3. Implement constrained RL experiments in the existing simulator for sequential shipping choices such as departure timing, speed or feasible diversion. Define observations, permitted actions and a reward based on delay, cost and constraint penalties. Compare with keeping the plan and strong heuristics on held-out scenarios. A second possible learning task is source/refresh selection. Weather residual estimation remains an observation-matching task, not a reward for agreeing with the latest API response.
4. Improve interval calibration using an earlier calibration partition, then report on a newly reserved chronological period. The current displayed GBM has 75.9% coverage for nominal 80% intervals; reusing the already examined reporting period does not establish a new improvement.

## Definition of completion

The release is ready for product review when the public URL demonstrates the connected intelligence-to-decision journey, rather than only showing an attractive globe or an evidence report. Review desktop and mobile interactions, source failures, shared time/selection, actual model/scenario inputs, private access boundaries and dated evidence. Visual review must assess whether the original idea is recognizable. Passing tests verifies behavior; it does not replace that assessment.

Present the first working workspace iteration for review before expanding the remaining layers. Treat background collector receipts and host maintenance as supporting operations, not the next product milestone.
