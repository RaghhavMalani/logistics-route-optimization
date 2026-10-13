# PortWatch X — complete implementation prompt

Prepared October 9, 2026. Copy this document into the implementation chat, or ask that chat to read this entire file before working. It updates the product priorities in the earlier recovery brief. This document is a prompt for future implementation; creating it does not change the application or authorize this drafting chat to deploy anything.

**Latest October 10 implementation update:** preserve the actual `e906f6a6bd4388cd3c059b4d9a5de6759139528b` application. Isolated demo adapters now connect its original Company, Vessel, Port and Admin screens, maps, inspectors, navigation, timelines and advisory chain. Read [the current capability review](RESTORED_APP_CAPABILITY_REVIEW.md) and [Restore and extend](RESTORE_AND_EXTEND_HANDOFF.md) for implementation, actual neural/RL results and source-dependent limits. Both learned candidates were rejected. The public forecast source still lags; weather outcomes and authorized real camera footage remain unavailable. Camera scenario integration exists, but a measured real-footage demonstration remains outstanding. The earlier replacement shells/layout prescriptions are superseded. Continue within this restored application and preserve the full technical requirements below; earlier state descriptions do not override this update. Nothing has been published.

---

## 1. Your assignment

Continue improving the existing PortWatch X application in `D:\LogisticOptimization-_Capstone_168`. Implement the product described below in the existing repository. Preserve useful work already completed. This is an implementation request: inspect, build, verify and deliver working changes, rather than responding only with another roadmap.

The intended product is a global intelligence and shipping optimization platform with four usable role workspaces: **Shipping Company, Vessel Operator, Port Authority and National Admin**. It combines an explorable global scene, worldwide intelligence, local port evidence, forecasts, simulation, constrained optimization and learning from later outcomes.

The project is intended to have a public link that we can demonstrate at research-paper presentations, capstone evaluations and events. People must be able to enter the actual application, investigate a situation and use the relevant role workflow. Publishing a report, a chart gallery or a case-audit page is insufficient.

The original request included all of the following:

1. Upgrade the UI while preserving the existing application and its four roles.
2. Integrate God's Eye View deeply, including its broader spatial intelligence capabilities, alongside news, economic signals and everything that can directly or indirectly affect shipping.
3. Connect port CCTV viewpoints and eventually extract useful operational observations from them.
4. Learn from weather prediction errors, including a five-day forecast that differs from later observations.
5. Add useful neural representations and fusion between specialist inputs and forecasting, with each learned component having a defined job.
6. Extend learned decision policies and RL where the system makes sequential choices.
7. Turn those capabilities into explainable shipping alternatives and measurable improvement.

The user is dissatisfied because previous work drifted into public-report pages, berth-record collection, Windows scheduling and deployment status while important product requirements remained missing. Correct that drift. Treat infrastructure and research evidence as support for the product.

## 2. What currently works, and what still needs recovery

Re-check the current code and deployment before editing; another chat may have continued implementation after this prompt was written. The following reflects the October 9 review, not a promise that the state will remain unchanged.

Public frontend: https://india-portwatch.vercel.app

Public API: https://india-portwatch-api.up.railway.app/api

The recovered `/explore` page now has a dark globe workspace with a signal rail, a central scene and an investigation panel. Selecting a report reveals affected ports and routes. An isolated shipping scenario uses the existing constrained decision engine. Changing an assumed restriction from 72 to 120 hours was independently observed to change the baseline simulated arrival shift from 50 to 98 hours. The simulated vessel and selected route appear in the globe.

Keep that recovery. It is useful, but it does not finish the original application.

At the same review:

- `/login` still offered only production credentials. Company, Vessel, Port and Admin demo entry was absent.
- `/` still redirected anonymous users to `/explore`.
- The four original role workspaces and the old demo roster still existed in the repository.
- The displayed port forecast had an October 2 origin and an October 3 Day-1 target, even though the review occurred on October 9. It was labelled stale.
- The globe's vessel was a configurable simulation; observed public AIS was not connected.
- Cameras were unavailable. A registry/player existed, but no working port-camera observation pipeline had been demonstrated.
- Global weather fields, broader infrastructure and several God's Eye layers were incomplete.
- Neural fusion and new constrained RL work were still future work.
- Published port congestion forecasts provided context; they were not calibrated causal inputs to routing decisions.

The earlier publication preserved public research artifacts, the GLAD YOUNG case, archived PDFs, first-seen times and cohort definitions. Preserve them, but do not make them the main entry experience again.

Latest available validation reports described 58 focused Python tests, six browser regressions and 16 public journey checks. Read those reports to understand what was tested. They do not prove that the four role demos or broader product are complete.

## 3. Product priorities and entry experience

**The immediate priority is four working role demos.** Do this before expanding another report page or adding another collector monitor.

For an anonymous visitor, `/` should open or redirect to the application entry screen. That screen must immediately offer four clearly named demo entry controls:

- Open Company Demo.
- Open Vessel Demo.
- Open Port Demo.
- Open Admin Demo.

Use `/login` as that entry screen if this fits the existing routing. Each demo control should enter its working dashboard in one deliberate action. Do not require an event visitor to obtain credentials, find a hidden email roster or submit a prefilled form as a second unexplained step.

Real operator sign-in remains available as a separate clearly labelled flow. A visitor can also open the public global workspace directly. The recovered globe may continue at `/explore` for stable links, but present it as **Global Intelligence**, not as a separate report website that replaces the application. Existing research and case URLs remain available through supporting links.

For an authenticated operator or active demo participant, `/` should take them to the appropriate workspace. Demo exit, logout and switching roles must work. Navigation must make the active role, selected port/vessel and demo or operational context understandable.

The product's primary navigation should expose the application: overview, global intelligence, fleet/vessel or port operations, forecasts, weather, scenarios, decisions and learning as appropriate to the role. Research, evidence and source inspection support those experiences.

## 4. Make demos actually work with the backend

The existing frontend demo adapter is not sufficient by itself. It manufactures browser-local identities, while the deployed backend requires verified sessions for protected routes. Simply changing `VITE_PORTWATCH_AUTH_MODE` to `demo` could restore buttons and still leave dashboards full of 401 responses. Conversely, granting a published demo administrator access to real operator state would be unacceptable.

Implement an explicit demo boundary. Choose the smallest maintainable architecture that satisfies the following contract:

1. A demo participant receives a session/context scoped to demo data and an isolated scenario state.
2. Demo role selection changes the demo workspace, not the person's production authority.
3. Demo tokens or client role headers cannot authenticate against operational API paths or expose private cameras, operator identities, private decisions or production ledgers.
4. All demo dashboard queries, simulations and workflow actions use the demo boundary consistently. A role label in the browser is not backend authorization.
5. Demo approvals, advisories, acknowledgments and outcome records write only to their demo namespace.
6. Separate visitors cannot overwrite one another's scenario or change the shared collector, production world clock, deployed model or operator configuration.
7. Refreshing a demo page restores its valid session, selected role and useful scenario state. Expired sessions return to a usable entry screen.
8. Reset affects only that visitor's demo. Logout clears its session and query caches.

An explicit `/api/demo/...` namespace with server-owned session scope is one possible implementation. If request-scoped stores and world contexts are used, verify every store, singleton, cache and background task follows the boundary. Choose one coherent approach; do not add a collection of unrelated auth modes and exceptions.

Use the existing public dataset and a coherent fictional shipping organization, fleet, port calls, cargo and scenarios for demonstration. Public-source observations may appear with their real provenance. Fictional vessel movements, berth plans and outcomes must remain labelled as demonstration or simulation. Private operational records must not be copied into the public demo.

The old published accounts can remain recognizable if useful:

| Role | Existing demo email | Default role home |
|---|---|---|
| Company | `company@portwatch.demo` | `/company/overview` |
| Vessel | `vessel@portwatch.demo` | `/vessel/overview` |
| Port | `port@portwatch.demo` | `/port/overview` |
| Admin | `admin@portwatch.demo` | `/admin/radar` |

The old client adapter uses `portwatch` as its demo password. These are public demonstration values, not accounts to provision with real production authority. Prefer direct demo buttons over making visitors type them.

## 5. Four distinct, connected role workflows

The roles must answer different questions and operate on appropriate assets. Do not give all four the same globe with a different heading.

### Company — fleet decisions

Question: **Which vessels and cargo movements need intervention, and what should the fleet desk do?**

Show the company's fleet, route and destination risks, upcoming arrivals, cargo connections and a ranked action queue. Selecting a vessel should reveal its voyage, destination forecast, relevant world signals and feasible alternatives. Let the user compare speed, departure, waiting, route or destination changes where supported. Explain the affected cost components, schedule consequences and constraints.

Connect advisories received from ports with the vessels and voyages they affect. Preserve the difference between a recommendation, an accepted advisory and an actual action. The company demo should be able to drill into one vessel and return to fleet context without losing selection.

### Vessel — bridge and voyage context

Question: **What is ahead of my vessel, what is changing, and which options remain feasible?**

Show the assigned vessel, track or simulated position, route, weather ahead, nearby relevant traffic, chokepoint timing, destination port and available advisories. A scenario should make it clear why a diversion is still possible or why the vessel is already committed. Display uncertainty and missing identity/track information.

Allow advisory inspection and acknowledgment within the demo workflow. A routing recommendation does not execute navigation or move a real ship. A demonstrator must be able to distinguish observed AIS from a simulated hull.

### Port — operational planning

Question: **What is happening at this facility, and how should its resources and arrivals be planned?**

Show arrivals, anchorage/queue evidence where available, berth occupancy, weather, forecasts, cranes/yard context, cargo connections and the existing digital twin. Integrate camera viewpoints into that port context. Compare berth scheduling, allocation, sequencing and crane/resource choices through the existing simulation and decision machinery.

Let the demo port review a proposed action, approve a demo advisory, inspect recipient response and resolve a demonstration outcome. Keep that illustrative chain in the demo namespace. Real operational approval still belongs to authorized operators.

### Admin — network and model oversight

Question: **Where does intervention matter across the network, and how reliable is the system?**

Show the national/network scene, ranked port risks, company and vessel exposure, global intelligence, system/source health, model status, benchmarks, calibration, learning and scenario tools. Admin demo can inspect or switch among the other demonstration roles in its own sandbox. Real admin permissions remain server-owned.

Provide a model comparison and experiment view that states which models were actually trained, evaluated and deployed. Candidate, validated and deployed states must not be interchangeable.

### One coherent demonstration

Seed one demonstration world so the roles tell a connected story: a world event affects a voyage; the company compares a change; the vessel inspects the recommendation; the port sees the revised arrival and its berth implications; the admin inspects system reliability. Role switching inside one visitor's demo can preserve that shared story, while roles retain their distinct navigation and permitted actions.

## 6. Interface and interaction requirements

Keep the product spatial and operational. Reuse the recovered globe and original role components rather than creating another disconnected frontend.

Desktop structure:

- Compact top bar: product, role/context, demo status, role switching or sign-out, source health and time mode.
- Left rail: ranked alerts, search, assets and layer controls.
- Main scene: globe or port/vessel map, selected tracks/routes, hazards and relevant operational geometry.
- Right inspector: selected asset/event, evidence, forecast, options, decision and learning details.
- Shared time control: current evidence, historical replay and forecast/scenario projection.

Selection must be shared: selecting a report highlights its exposed routes and ports; selecting a port opens its local context; selecting a vessel opens its voyage and possible actions; selecting a compared option redraws its geometry and updates the inspector. Preserve that selection when moving between the global view, role view and evidence drawer.

Use the existing dark visual language, clear typography and restrained status colors. Show risk with readable legends and accessible labels. Do not equate a glowing marker with a validated disruption probability. Keep operational controls easy to find and explanations close to their associated result.

On mobile, switch among scene, signals and inspector without creating multiple active globes or losing selection. All four demo entry buttons must remain visible and usable. A long form or table must not hide the route or prevent users from reaching the compare button.

For loading and failure, keep the rest of the application usable. Show which source is delayed, stale or unavailable and a targeted retry. Measure initial globe/chunk loading: do not leave visitors watching an unexplained preparation message. A lightweight map fallback is appropriate when WebGL fails, with an honest explanation.

A visible demo control must perform the stated action. Avoid inert buttons, decorative layer switches, unexplained empty dashboards and prominent features that only link to a future-work page.

## 7. Deep God's Eye integration and broad intelligence coverage

Upstream repository: https://github.com/bilawalsidhu/gods-eye-view

The installed package is currently pinned to `9542a5e58b19277d1f9b6698a46f69fdaa5fc5c1`. Audit the installed revision and current upstream before selecting modules. Preserve attribution and imported license notices. Check data/asset terms separately from the code license.

The upstream project describes a broad globe experience with aircraft, ships, satellites, hazards, weather and cameras. Reusing its viewer lifecycle alone does not deliver that experience. PortWatch's own news, economics, models and decision logic must be integrated with it rather than assuming the upstream supplies all of them. [Upstream reference](https://github.com/bilawalsidhu/gods-eye-view).

Create a concise capability matrix for every relevant layer: existing implementation, upstream module, active source, actual geographic coverage, required credentials, cadence, timestamps, rights, operational relationship, and remaining dependency. Then implement the adapters and interactions. The matrix is a work tracker, not a substitute for integration.

| Intelligence family | Required connection to shipping |
|---|---|
| News, conflict and policy | Strikes, closures, sanctions, restrictions and unrest linked to affected locations, lanes, cargo or facilities. |
| Economics and markets | Fuel, exchange rates, freight and trade context connected to explicit cost and demand assumptions. |
| Weather and ocean | Wind, gusts, waves, rain, visibility, cyclones and relevant marine conditions across routes and ports. |
| Hazards | Earthquakes, floods, fires and other disruptions connected to exposed infrastructure and operations. |
| Ships and AIS | Identities, positions, tracks, arrivals, destinations and freshness connected to voyages and ports. |
| Aircraft and satellites | Spatial movement or observation context with a stated shipping/infrastructure use; retain context-only layers where appropriate. |
| Roads, rail and transit | Inland cargo readiness, access bottlenecks and connection risk. |
| Infrastructure | Ports, berths, terminals, chokepoints, power and other relevant facilities/networks with geometry and known limits. |
| Cameras | Identified port/terminal/berth/gate viewpoints and bounded operational observations. |

Do not narrow the system back to a maritime-only news list. Users should investigate broad global signals and see which have established shipping connections. A contextual layer can be useful without being a trained forecasting input; label that distinction.

Use one active rendering lifecycle per scene. Lazy-load heavy modules, destroy unused renderers and avoid parallel Cesium/MapLibre scenes consuming memory. Keep layer adapters separate from the inference and decision engines, so a visualization cannot silently introduce new delay formulas.

## 8. News, incidents and economic connections

Broaden the existing connectors/classification beyond a few chokepoints. Normalize location, category, event time, publication time, first-seen time, source and reliability. Link incidents to the graph of places, ports, lanes, facilities and assets.

Cluster multiple reports of one incident without merging unrelated incidents at the same location. Syndicated copies from several domains should not automatically count as independent corroboration. Retain sources, conflicting reports and the basis of each location. Historical storms belong in historical investigation; they should not dominate the default current alert queue merely because their dataset rows exist.

Event severity, corroboration, exposure and modelled operational impact have different meanings. Display and store them separately. If a relationship is only a catalogue exposure or a scenario assumption, preserve that meaning rather than claiming measured causality.

Economic series need units, currency, observation date, release/availability information where available and stale state. Connect fuel and exchange-rate assumptions to costs transparently. Let a visitor choose a provider value or an entered assumption and retain which was used in a comparison. A CPI series appearing beside a ship does not establish a congestion model connection.

Add freight, trade or infrastructure signals when a source and a meaningful target are available. Maintain usable current features while an optional paid or unavailable provider remains pending.

## 9. AIS, vessel identity and routes

Reuse the existing AIS fabric and entity fusion. `src/portwatch_os/fusion` is about canonical vessel identity; do not confuse it with the requested neural expert-fusion model.

Preserve IMO/MMSI identity, timestamps, track history, provider/source, observed versus inferred attributes and conflicts. Names alone should not silently merge two hulls. A plotted position should state how old it is. Dead reckoning or interpolation must be labelled and bounded.

Connect observed tracks to the correct vessel/voyage, route and destination when supported. Do not use a public berth report as proof of a continuous live track or confirmed MMSI. Keep fictional demo fleets explicitly separate from observed ships.

Review available authorized sources and existing adapters before proposing a new paid integration. If a feed requires credentials or coverage verification, report that specific layer dependency and continue other work. Do not make an optional provider a prerequisite for the four role demos, model experiments or the whole interface.

Route geometry must use the same topology and constraints as the decision engine. Alternatives cannot pass through land, bypass timing gates or imply a usable commercial sailing when no service evidence exists. If geometry is schematic, say so. This application supports investigation and planning; it is not a bridge navigation system.

## 10. Port CCTV and computer vision

Reuse the scoped camera registry and existing media support. Associate each viewpoint with the relevant port, terminal, berth or gate. Record source, public/private access, rights basis, coverage, pose/location quality, frame timestamp, retrieval time and stream health.

Use identified public or supplied authorized feeds. Do not invent live camera coverage. If an actual feed cannot be connected, a clearly dated, authorized recording can support development and a labelled demonstration. Its outputs must remain recorded observations rather than current port state.

Implement a bounded computer-vision path for useful targets such as:

- Berth occupancy within the viewpoint.
- Visible vessel arrival/departure or movement.
- Gate/truck queue extent or trend.
- Crane activity when the viewpoint and sampling can support it.
- Possible smoke/interruption requiring review, with explicit confidence and false-positive handling.

Every generated observation should identify its camera/frame interval, region of interest, model version, confidence and coverage. Require sufficient frame quality and temporal evidence. A single quay camera cannot establish the entire port's occupancy or productivity. Do not identify a vessel from appearance alone when identity evidence is absent.

Build a labelled evaluation set and report detection/occupancy/queue performance appropriate to the target. Use held-out viewpoints or time periods where possible. Demonstrate how a reviewed camera observation enters port state and an affected planning scenario. Do not stop at drawing bounding boxes or adding a camera tab.

Historical replay uses recorded frames available at the replay time; it must not display current media as historical evidence. Keep private feeds and derived private evidence inside their existing membership boundary.

## 11. Shared evidence, time and consequence contract

Use consistent records across adapters, models, the scene and decisions. The following concepts are required even if the repository uses different field names:

| Record | Essential information |
|---|---|
| Signal/observation | Stable ID, source, source version, asset/location, observed/valid time, publication/available time, retrieval/recorded time, units, quality, coverage and access scope. |
| Forecast | Port/asset, target variable, provider/model, model version, original values, origin/issue or retrieval time with its meaning, target time, horizon, input IDs, uncertainty and availability. |
| Consequence | Affected operation, baseline, projected delay/cost/capacity effect, interval if supported, horizon, input IDs, model/version, assumptions and missing-input reasons. |
| Scenario | Submitted assumptions, selected world revision, initial state, visitor namespace, seed, feasible actions and immutable comparison results. |
| Decision/advisory | Compared options, recommendation, constraints, approval/delivery/acknowledgment states and the evidence actually consumed. |
| Outcome | Actual event/action/result, source, timestamp meaning, availability, match quality and whether measured, recorded-demo or simulated. |
| Model experiment | Dataset/feature snapshot, partition dates, code/dependencies, seed, targets, metrics, candidate artifact and promotion status. |

One time control should govern the view. Separate the actual present from scenario time. Historical mode must withhold information unavailable at that historical instant. A later retrieval or current cache export cannot be backdated to create a historical forecast. Missing observation, unknown value and measured zero are separate states.

The explainable chain is:

```text
World signal
  -> exposed route / facility / port / vessel / cargo
  -> forecast or scenario consequence
  -> constrained alternatives
  -> reviewed decision and advisory
  -> actual or simulated action
  -> later outcome
  -> error scoring and learning
```

Each hop needs its evidence, method and uncertainty. Every signal displayed beside a recommendation is not automatically an input to that recommendation. Record which inputs the model actually consumed.

## 12. Fresh forecasts and useful shipping decisions

Fix the forecast delivery path alongside role restoration. Public report collection is a separate job from weather collection, feature generation, forecast inference and artifact export. A new receipt does not make an October 2 forecast current.

Trace the source of stale outputs through fetch, feature build, model availability, inference, export, backend cache and frontend query. Refresh current supported predictions without retraining on the reporting holdout or changing timestamps to hide stale data. If the source itself has reporting lag, distinguish source lag from a failed pipeline and state the latest valid target/horizon.

The shipping comparison must consume the selected vessel/scenario, route, timing, closure and weather constraints through the existing engine. Extend meaningful supported objectives: arrival and waiting, departure deadlines, fuel, cost components, berth/resource feasibility and cargo connection risk.

Compare keeping the plan, slowing/speeding within limits, waiting, adjusting departure, feasible diversion and supported destination/berth alternatives. Missing cargo, dimensions or charges should produce specific limits, not a fictional total cost. Add editable scenario inputs when a demonstrator can reasonably supply a missing value.

Show why an option was rejected, what changes if it is selected, and which uncertainty can alter its ranking. Allow scenarios in which action is clearly useful and scenarios in which retaining the plan is correct. Do not hard-code a reroute so the demonstration looks impressive, or make 'keep plan' win every case by construction.

The existing decision benchmark reports that the robust vessel policy matched keeping the plan at 1.05 hours mean regret and captured none of ten cases where intervention was best. Treat that as a concrete improvement target. Expand adverse-condition and missed-intervention cases, compare strong baselines and address the observed failures before claiming optimizer value. The old benchmark is a recorded result, not necessarily the newest implementation; verify it before changing policy.

## 13. Weather feedback: the original five-day example

The user asked for the system to learn when a five-day weather prediction was wrong. Implement and expose that learning loop, while using the correct learning method for each task.

Distinguish two errors:

1. The weather forecast differed from a later observation. The forecast correction/provider-reliability layer should learn from this.
2. The weather was forecast correctly, but its effect on operations was predicted incorrectly. The weather-to-capacity/delay/consequence model should learn from that outcome.

For each forecast retain an immutable original: port/location, variable, units, daily/hourly statistic, provider and provider model, issue time when actually supplied, retrieval time, target time, exact horizon, values, quantiles and input/version information. Do not call retrieval time a verified provider issue time.

When a target passes, match a later observation of the same location, variable, units and aggregation. A daily maximum wind forecast cannot be scored against daily mean wind. Preserve the observation's measurement and availability time. Distinguish station/operator measurements from reanalysis.

A newer forecast from an API is not the realized outcome. Previous-run archives can support lead-time comparisons, while historical weather products may include reanalysis; check the provider's actual semantics and coverage. [Open-Meteo Previous Runs](https://open-meteo.com/en/docs/previous-runs-api), [Historical Weather](https://open-meteo.com/en/docs/historical-weather-api).

Score error by port, variable, provider, season and horizon, including Day 5. Keep MAE, signed bias, relevant extremes and interval coverage. Several refreshes of one target must not inflate the independent outcome count. Missing observations remain pending.

Reuse the current residual-correction implementation as a baseline. Separate fitting, selection/validation and calibration chronologically, with availability purging. Preserve the original forecasts and store corrections separately. A correction must identify its version and learned context. Apply validated corrections to subsequent features/inference and show their downstream effect; do not merely display a corrected number beside a decision that still consumed the old input.

The UI needs an inspectable sequence: **original forecast -> corrected forecast -> observed outcome -> residual -> effect on recommendation**. It must also show collecting, insufficient data, rejected and validated states clearly.

One miss does not prove a missing feature. Investigate repeated errors, input gaps, provider age and aggregation mistakes. Learn systematic corrections from evidence.

## 14. Neural architecture with defined jobs

The user's 'layer by layer' idea should become meaningful learned components connected through clear interfaces. Do not add a neural network at every boundary merely to make the diagram look deep.

Target architecture:

```text
Weather / events / economics / AIS / port operations / cameras
                    |
         Quality, identity and time alignment
                    |
      Specialist representations and missingness masks
                    |
       Learned context-dependent expert fusion
                    |
      Temporal forecasts and operational consequence models
                    |
        Uncertainty and network exposure/propagation
                    |
        Simulation and constrained decision engine
                    |
       Learned policy candidate plus safety constraints
                    |
             Role-specific review workflow
                    |
          Outcomes, residuals and policy evaluation
```

Implement the next useful neural candidate in the existing forecasting stack. A small gating/fusion network is a sensible first target: use specialist forecasts/representations, port, horizon, regime where legitimately available, source ages, quality, masks and past resolved error to produce context-dependent contributions. Ensure it connects to an explicit forecast/consequence target and enters actual inference.

Compare it with the current ensemble, equal weighting, persistence and an appropriate non-neural alternative. Include source-dropout and missing-input tests. A simple model that wins remains the incumbent; an implemented neural candidate can still be a valid experiment without being promoted.

Possible subsequent components include neural weather residual correction, the existing TFT for temporal prediction, and graph propagation over connected ports/routes/facilities. Audit the existing TFT and training/dependency path before duplicating it. A graph model needs a defined target and suitable observations; do not turn exposure edges into invented causal delay labels.

Record feature versions, weights, training configuration, dataset and artifact hashes, seed, metrics and active inference version. Contributions or gating weights explain model use, not causal importance. Do not label an untrained architecture as active intelligence.

If independent data is inadequate for a particular model, implement its interfaces and evaluation path, state the exact training dependency and continue supported models/experiments. Historical experiments can proceed where their features and labels have valid time semantics. Do not wait for the prospective public-port cohort to finish before doing all neural development.

## 15. RL and learned decision policies

Audit existing RL/policy work first. In particular, inspect `src/portwatch_os/twin/rl.py`, `policies.py`, `promotion.py` and the decision-learning modules. The repository already contains a seeded port environment, contextual-bandit policy interfaces, baseline policies and promotion concepts. State what is implemented, trained, evaluated and used in inference; these are different claims.

RL is appropriate where the system chooses actions and their consequences evolve. Weather residual fitting alone is supervised prediction. If all providers can be compared with the same observation, supervised reliability weighting can use that information; a contextual bandit is useful when only the chosen source/action receives relevant feedback.

Implement and evaluate a scoped sequential policy experiment in the validated simulator. Pick one initial operational problem with a clear target, such as port sequencing/resource allocation or voyage departure/speed/wait/diversion decisions. Reuse current state and constraints rather than building a disconnected toy environment.

Specify before training:

- Observation: available vessel/port state, forecast summaries and uncertainty, queues/capacity, remaining route/timing, source freshness and missingness.
- Actions: a bounded set of feasible operational changes and retaining the current plan; all actions pass the existing physical/topological constraints.
- Transition: simulator progression, arrivals, changing weather/disruption information, service and resource effects.
- Reward: explicitly normalized delay, cost/fuel and missed-connection consequences, with hard safety constraints outside a tradeable reward.
- Episode termination: completion, horizon, failure or rejected transition, stated consistently.
- Training and evaluation: separate seeds plus held-out scenario families/conditions, not just different random draws from one easy case.

Compare with keeping the plan, first-come/first-served, greedy, existing heuristics/lookahead and the current robust engine as applicable. Report delay, fuel/cost components, violations, regret, missed useful interventions, unnecessary interventions, runtime and variance. Check that a policy does not exploit reset semantics, unavailable future information or unrealistic simulator loopholes.

Publish the policy as an experimental candidate until promotion criteria are satisfied. Show evaluation and candidate status in Admin/Learning. Keep operational actions behind their existing human workflow; demo actions execute only in the sandbox.

Do not endlessly postpone RL as a sentence in the roadmap. Deliver an implemented, reproducible simulator experiment with results, while keeping the strength and scope of those results honest.

## 16. Evaluation and research requirements

Keep research supporting the product, but make the learning work reproducible.

For forecasting, divide fit, tuning/selection, calibration and final reporting by time. Purge labels or observations that cross availability boundaries. Feature scaling, regimes, embeddings, ensemble weights and calibration must be fitted using their permitted partitions. Do not fit a full-history regime and then reuse it as though it had been known at each past origin.

The existing displayed historical congestion benchmark uses an already examined reporting period. A new experiment on it is not a new untouched test. Reserve a later period or use an explicit rolling-origin protocol with model choices frozen before each evaluation. If new untouched outcomes are unavailable, identify the limits instead of manufacturing a promotion claim.

The displayed October 8 GBM MAE was about 5.918 congestion-index points versus 6.674 for persistence, with about 75.9% coverage for nominal 80% intervals. These are historical proxy-target scores. Use the current manifest for exact figures. Improve calibration on an earlier calibration block and report performance on a newly reserved period.

Congestion from IMF call pressure is a proxy. Public reported arrival-to-berth waiting, confirmed anchorage/all-fast measurements, cost and realized savings are separate targets. Define the target before choosing a model or metric. Ablations establish predictive comparisons, not automatic causal value of weather or news.

Preserve the Paradip/Chennai collector and optional JNPA workflow in the background. Real operators can strengthen operational validation, but an operator response is not a prerequisite for product development or supported historical/simulator experiments. A historical public record cannot be retroactively converted into a prospectively frozen prediction.

GLAD YOUNG remains a published-ETA baseline case: -24 minutes arrival error and 2.4 hours reported arrival-to-berth waiting. It is not a new ML accuracy result, confirmed all-fast interval or realized shipping saving.

## 17. Repository implementation map

Inspect these existing locations before introducing replacement systems:

| Responsibility | Existing starting points |
|---|---|
| Entry, login and identity | `india-portwatch-terminal/src/routes/index.tsx`, `src/routes/login.tsx`, `src/auth/AuthProvider.tsx`, `src/auth/adapters.ts`, `src/auth/guards.tsx`, `src/auth/types.ts` under the frontend root; `backend/app/identity.py`, `auth_store.py`, `routes/auth.py`, `main.py`. |
| Original role application | `india-portwatch-terminal/src/routes/admin`, `company`, `port`, `vessel`; `src/components/app/AppShell.tsx` and navigation. |
| Recovered globe | `india-portwatch-terminal/src/components/public/PublicWorkspace.tsx`, `src/services/public-workspace.ts`, `backend/app/services/public_workspace.py`, `src/components/intelligence/IntelligenceGlobe.tsx`. |
| Existing operational intelligence | `india-portwatch-terminal/src/components/globaleye`, `src/components/intelligence/IntelligenceWorkspace.tsx`, `src/world/WorldContext.tsx`; `backend/app/routes/intelligence.py`; `src/portwatch_os/global_eye` and `world`. |
| AIS and canonical identities | `src/portwatch_os/fabric/ais`, `src/portwatch_os/fusion`. |
| Forecasts and expert inputs | `src/experts`, `src/forecasting/ensemble.py`, `forecast_runner.py`, `calibration.py`, `tft_model.py`, `src/evaluation/model_benchmark.py`, `run_award_demo.py`, `backend/pipeline`. |
| Weather learning | `src/ingestion/connectors/weather_live.py`, `src/portwatch_os/learning/weather_feedback.py`, `outcome_agent.py`, `reliability.py`, `scoring.py`. |
| Decisions and digital twin | `src/portwatch_os/decision`, `src/portwatch_os/twin`, `india-portwatch-terminal/src/components/decision`, `src/services/decisions.ts`. |
| RL and promotion | `src/portwatch_os/twin/rl.py`, `policies.py`, `promotion.py`; `src/portwatch_os/decision/learning.py`, `promotion.py`, `benchmark.py`. |
| Public evidence | `backend/app/routes/public_research.py`, `data/research_release`, `data/public_port_cases`, existing public-port evidence and cohort stores. |

Read `AGENTS.md` instructions applicable to each edited location. The frontend is connected to Lovable; preserve published Git history. The working tree contains extensive existing changes. Inspect and preserve them rather than resetting, reverting, overwriting or reformatting unrelated work.

Useful documents are `docs/PRODUCT_INTERNALS.md`, `INTELLIGENCE_WORKSPACE.md`, `PUBLIC_WORKSPACE_ITERATION.md`, `PUBLIC_WORKSPACE_RELEASE.md`, `PUBLIC_PORT_PILOT.md`, `API_CONTRACT.md`, `DEPLOYMENT.md` and `SECURITY.md`. Older statements can be stale. This prompt supersedes the earlier recovery brief's priority of a globe-only public entry; four-role demo restoration is now the immediate requirement.

## 18. Execution order and deliverables

Work in bounded milestones while preserving the full objective. Do not try to implement every upstream module in one unreviewable rewrite.

### Milestone A — restore the application

Implement entry routing, four direct demo buttons, the consistent demo API/session boundary, role-specific dashboards, role switching, refresh/logout/reset and one coherent cross-role demo. Preserve the recovered globe and evidence links.

Deliverable: a demonstrator can use all four roles, inspect their existing maps/forecasts, compare a scenario and exercise the demo advisory chain without protected-route errors or production mutations. Present the working result for product review before spending most of the effort on further layer expansion.

### Milestone B — freshness and connected decisions

Repair the separate forecast pipeline/output path. Make current supported data usable, date lagged data honestly, connect selected inputs to the decision engine and show limitations. Improve missed-intervention/constraint cases and scenario explanations. Preserve source and model versions.

Deliverable: a demonstrator can identify the age and target of a forecast, change a consumed input, recompute a comparison and explain why an option changed or was rejected.

### Milestone C — broader intelligence and cameras

Expand relevant God's Eye layers with news/economic/infrastructure adapters and actual available coverage. Integrate authorized AIS and camera sources where possible. Implement a bounded CV observation demonstration with appropriate footage and evaluation.

Deliverable: a port/vessel selection gathers its relevant global and local signals, with working spatial interactions and precise coverage. Missing optional credentials block their source only.

### Milestone D — learning implementations

Deliver the original/corrected/observed weather inspection, a trained/evaluated neural candidate where appropriate data supports it, a reproducible constrained policy/RL experiment, calibration work and model-status UI. Fit on valid data, evaluate with appropriate partitions and publish candidate artifacts/results.

Deliverable: the model work exists in code and reproducible experiments, enters its intended inference or experimental path, and states what was measured. Do not call an untrained network or a documentation paragraph an implemented model upgrade.

Milestones B-D can share adapters and run independently where dependencies allow. The prospective operational cohort should continue collecting without freezing all other development.

## 19. Acceptance checklist

### Entry and all four roles

- Anonymous `/` immediately exposes Company, Vessel, Port and Admin demo entry.
- Each control reaches its correct working dashboard in one deliberate action.
- Each dashboard has useful populated context, appropriate navigation and successful backend queries.
- Deep links, refresh, role switching, logout, expiration and demo reset work.
- Demo state, tokens and actions cannot read or write operational/private state.
- Company, vessel, port and admin demonstrate different responsibilities in one coherent scenario.

### Globe and intelligence

- Report, port, vessel and route selection update scene and inspector together.
- Selecting a compared option updates its visible route.
- Layer controls affect actual rendered data; their source and coverage can be inspected.
- Current, historical and projected views retain correct time semantics.
- Old incident archives do not masquerade as current high-priority alerts.
- Mobile interaction preserves one scene and reachable controls.
- Globe failure does not make the entire application unusable.

### Data and decision use

- Current forecast targets, origins, model/input versions and source ages are available.
- Stale timestamps cannot be overwritten by a new export or cache receipt.
- Original forecasts remain immutable.
- Changed weather/closure/timing assumptions demonstrably affect the consumed scenario.
- Infeasible routes, unsafe seas, committed-vessel diversion and incompatible input combinations are rejected clearly.
- Cost/fuel units and baseline comparisons are consistent; missing total-cost components remain explicit.
- There are valid cases where changing the plan helps and where retaining it is correct.

### Learning and research

- Forecast observations match variable, units, aggregation, target and availability.
- Neural experiments compare appropriate baselines and handle missing inputs.
- RL/policy experiments use separate training/evaluation and meaningful constraints.
- Candidate versus deployed status is visible and versioned.
- No historical proxy score or simulator result is presented as measured operational savings.
- Existing archived PDFs, release hashes, case URLs and public evidence remain accessible.

### Verification and release

- TypeScript and lint for changed source pass; relevant backend tests and production build pass.
- Browser QA exercises all four demo roles against their real demo backend, not only mocked responses.
- API tests verify demo isolation and preserved production authorization, including negative cases.
- Desktop and mobile are visually reviewed after the scene has actually rendered.
- A staged deployment verifies the application entry, four roles, simulations, evidence links and source failures on public HTTPS URLs.
- The final production alias runs the intended frontend/API versions, with CORS and persistent public state intact.

Scale tests to the changes. Add meaningful behavior tests, not tests that merely restate implementation. Do not repeatedly rerun every inherited suite or perform unrelated repository-wide formatting to inflate validation numbers.

## 20. Five demonstration stories the application must support

1. **Company:** a lane restriction threatens a voyage; identify affected fleet assets, compare a feasible change, see schedule/fuel/cost implications and inspect the advisory.
2. **Vessel:** inspect weather and chokepoint timing; compare available actions; see why a late diversion is rejected; acknowledge a demo advisory.
3. **Port:** an arrival surge or weather constraint affects berth planning; inspect arrivals/twin/camera evidence, compare a resource or schedule choice and issue a demo advisory.
4. **Admin:** identify where risks concentrate, inspect a port/company/vessel, then inspect model reliability and candidate-versus-deployed learning status.
5. **Learning:** inspect a five-day forecast miss against a valid later observation; see correction and uncertainty evidence, and trace its effect into a subsequent forecast or explicitly labelled demonstration model run.

If a story requires fictional or recorded data, label it and make that data coherent. A polished simulated demonstration can establish that the workflow works; its source label must prevent viewers from confusing it with a real operational outcome.

## 21. Deployment and scope boundaries

The target remains the existing Vercel frontend and Railway backend. Use the current linked projects, architecture and public domains. Prepare and verify a staged release before production publication, within the authorization available in the implementation chat. Do not invent a requirement to change hosting providers or return to Windows Task Scheduler maintenance as the main feature work.

The implementation chat should complete its authorized work before requesting any genuinely necessary final approval. If an action needs additional authorization, present the exact prepared change and explain the actual reason. Do not ask for confirmation after every routine edit, test or reversible decision.

Do not purchase providers, enable new billing, change account ownership, publish private data, remove production authentication, rewrite published Git history or delete existing evidence as part of this task. Ask only when such a consequential action is genuinely needed. A missing credential should be recorded for that provider while unaffected product work continues.

Keep public-port collection running in its existing backend path. Preserve first-seen timestamps, hashes, immutable originals, cohort cutoffs and identity stores. Do not replace genuine state with QA fixtures. Stop QA processes started for verification and keep them separate from the real backend.

## 22. How to communicate progress and completion

Lead progress with user-visible changes: which role works, which investigation is possible, what input changes the decision, what source is connected, and which model was actually evaluated. Routine collector counts, host PIDs and test totals belong in supporting evidence.

For each milestone, provide the usable URL or preview, a concise demonstration sequence, relevant screenshots, what changed, verification, and specific remaining gaps. Name source coverage dependencies precisely. Do not claim the whole product is complete after one milestone.

Final delivery should include a short matrix of **implemented and usable**, **implemented but awaiting data/credentials**, **experimental and evaluated**, and **remaining work**, with links to evidence. Preserve the original product goal across all milestones.

Start now by re-checking the current tree, then implement Milestone A. Keep the recovered globe. Restore the four role experiences. Continue toward the broader intelligence and learning platform without substituting another report website for the application.
