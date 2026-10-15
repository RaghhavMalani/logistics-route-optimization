# Additive intelligence contracts

October 14, 2026. Integration track changes for teammates branching from `feat/portwatch-restored-intelligence`. The Company, Vessel, Port and Admin role sources and `PortTwinScene` retain the restored interface. This adds data and shared components; Ananya's geometry/GEE work and Preksha's UI/data-quality work remain their assignments.

`NavigationRestrictionPanel` takes the existing optional `onDecision(DecisionProblem)` callback. It mounts within `ShippingIntelligencePanel`; no new role shell is introduced. `FrozenIntelligenceBasis` accepts `restriction.sourceFamily = NAVCEN_MSI` alongside existing Eastham evidence. The original inspector carries this frozen basis through Company, Port and Vessel.

`DecisionEvidence.restrictionAsset` contains `{id, name, lat, lon, basis}`. `decisionLayers` emits its point through the existing `cascade` source. The internal `portwatch:focus-constraint` event carries this asset and its `period`; `useWorkspaceMap` adds a labelled point and focuses the existing chart, while the Global Intelligence dialog closes. The point comes from official MSI, not a generated shipping route, closure polygon or surveyed twin. Teammates can later replace this small event bridge with a shared typed selection contract.

Timeline marks add `restriction_start`, `restriction_end` and `passage_request`, each with explicit `subject`, `hours` from comparison origin and retained `at`. These are scheduled constraints, not observed movements, claim expiry or confirmed access. Preserve their distinctions in subsequent presentation work.

`operationalEpisode` is server-owned `{id, voyageLegId, namespace, vesselId, portCode, createdAt}`. ETA edits, refreshes and role copies preserve it. A distinct next call requires a confirmed Company request and stable `requestId`; repeated identical requests recover the same call, while conflicting reuse is rejected. Earlier comparisons and advisories remain inspectable.

The advisory's `approvedActionContract` and outcome's `simulatedAction` carry canonical action and metric basis hashes. A simulation identifies its call and selected action but has `actualExecutionAt: null` and `eligibleForRealTarget: false`. Do not use approval, acceptance or simulation as proof of real execution.

Operational inspection preserves all forecast vintages. Real scoring requires episode, executed action, action/metric basis hashes, explicit approved forecast cutoff, observation/availability times and suitable original records. One independent episode/metric counts once under the documented cutoff policy; conflicting records remain excluded. Old records without this identity remain unscored and inspectable.

Frozen feedback retains a global snapshot for audit, but continuation checks consumed assessment/applicability, originals, relevant active consumer-bound policies, expiry and voyage declarations. Global pending counts are not continuation dependencies. Current calculators bind no learned policy: weight 1, no correction, COLLECTING. Future calculators must explicitly bind actual consumed policy parameters; discovering a matching version in the ledger does not apply it.

Economic quotes and persistence forecasts remain inspectable. They cannot create vessel holds. No currency exposure amounts or settlement dates are invented; a future valuation contract must supply those inputs separately from reference rates and realized savings.
