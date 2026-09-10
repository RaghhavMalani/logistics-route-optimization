"""The PortWatch tool catalogue.

Every tool here is a thin adapter over a deterministic module. The adapter's
whole job is to shape arguments and results; the arithmetic belongs to the model
it wraps, and each tool declares which one in ``computed_by`` so a trace shows
where every number came from.

Tools that need an artefact the pipeline has not exported raise
:class:`ToolUnavailable` naming the command that produces it, rather than
returning a plausible empty result. An agent can then say "the weather artefact
is not available" instead of "there is no weather".
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.portwatch_os.advisories.model import (
    DRAFT,
    ISSUED,
    ISSUER,
    RECIPIENT,
    UNDER_REVIEW,
    Advisory,
    AdvisoryError,
)
from src.portwatch_os.advisories.store import (
    AdvisoryStore,
    AuthorisationError,
    Principal,
    get_advisory_store,
    principal_for_role,
)
from src.portwatch_os.agents.tools import (
    EXECUTE,
    PROPOSE,
    READ,
    SIMULATE,
    ApprovalContext,
    ToolError,
    ToolRegistry,
    ToolScope,
    ToolUnavailable,
)
from src.portwatch_os.cargo.model import demo_manifest, zones_from_state
from src.portwatch_os.cargo.optimizer import opportunities, optimise
from src.portwatch_os.fleet.company import (
    CompanyProfile,
    attach_etas,
    capacities_for,
    demo_company,
)
from src.portwatch_os.global_eye.calibration import apply_calibration, fit_calibrator
from src.portwatch_os.global_eye.exposure import (
    TRADE_LANES,
    aggregate_port_risk,
    build_impact,
)
from src.portwatch_os.global_eye.ingest import from_news_bundle
from src.portwatch_os.ledger.store import LedgerStore, get_ledger
from src.portwatch_os.learning.attribution import attribute, rank_misses
from src.portwatch_os.learning.outcome_agent import OutcomeAgent
from src.portwatch_os.twin.policies import GreedyPolicy, build_policy
from src.portwatch_os.twin.promotion import active_policy
from src.portwatch_os.twin.rl import PortEnvironment, ScenarioSpec, benchmark, default_policies
from src.portwatch_os.twin.simulation import SimulationConfig, reward, reward_breakdown, simulate
from src.portwatch_os.twin.state import state_from_snapshot
from src.utils import port_registry

CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "cache"

REBUILD_HINT = "Run `python run_award_demo.py --source portwatch` to build it."


def _read_cache(name: str) -> Any:
    path = CACHE_DIR / name
    if not path.exists():
        raise ToolUnavailable(
            f"{name} has not been exported by the pipeline. {REBUILD_HINT}"
        )
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ToolUnavailable(f"{name} is corrupt: {exc}. {REBUILD_HINT}") from exc


def _port_snapshot(port_code: str) -> Dict[str, Any]:
    state = _read_cache("port_state.json")
    record = port_registry.resolve(port_code)
    for key in filter(None, [port_code, record.locode if record else None,
                             record.model_id if record else None]):
        if key in state:
            return state[key]
    known = ", ".join(sorted(state)[:12])
    raise ToolUnavailable(
        f"no observed state for {port_code}. Ports in this run: {known}"
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------


def _principal_for_scope(scope: ToolScope) -> Principal:
    """The advisory principal for an authenticated tool scope.

    Thin on purpose: the mapping itself lives in the advisory store beside the
    authorisation rules it feeds, so the tool layer and the HTTP layer cannot
    drift into disagreeing about what a role may see.
    """
    return principal_for_role(
        actor=scope.actor,
        role=scope.role,
        port_code=scope.port_code,
        organisation=scope.organisation,
        vessel_ids=list(scope.vessel_ids),
    )


def build_registry(
    *,
    ledger: Optional[LedgerStore] = None,
    advisory_store: Optional[AdvisoryStore] = None,
    company: Optional[CompanyProfile] = None,
) -> ToolRegistry:
    """Assemble the tool catalogue.

    Dependencies are injected so tests can supply in-memory stores and a fixed
    company, and so the API can supply the process-wide ones. Nothing here
    reaches for a global.
    """
    registry = ToolRegistry()
    ledger = ledger if ledger is not None else get_ledger()
    advisories = advisory_store if advisory_store is not None else get_advisory_store()
    fleet = company if company is not None else demo_company()

    # ------------------------------------------------------------ READ --
    @registry.register(
        "portwatch.ports.list", READ,
        "Every port in the registry with its observed state.",
        returns="Array of port snapshots: congestion, delay, risk, queue pressure.",
        computed_by="backend pipeline export (port_state.json) + src.utils.port_registry",
        failure_modes=("The pipeline has not exported port_state.json.",),
    )
    def ports_list() -> List[Dict[str, Any]]:
        state = _read_cache("port_state.json")
        return [
            {"code": code, **{k: v for k, v in row.items() if k != "forecast"}}
            for code, row in sorted(state.items())
        ]

    @registry.register(
        "portwatch.ports.get", READ,
        "One port's observed and forecast state.",
        arguments={"port_code": "UN/LOCODE or model id, e.g. INMAA."},
        required=("port_code",),
        returns="One port snapshot including its forecast series.",
        computed_by="backend pipeline export (port_state.json, forecast_by_port.json)",
        failure_modes=("The port is not in this run.",),
    )
    def ports_get(port_code: str) -> Dict[str, Any]:
        snapshot = dict(_port_snapshot(port_code))
        try:
            forecasts = _read_cache("forecast_by_port.json")
            record = port_registry.resolve(port_code)
            for key in filter(None, [port_code, record.locode if record else None,
                                     record.model_id if record else None]):
                if key in forecasts:
                    snapshot["forecast"] = forecasts[key]
                    break
        except ToolUnavailable:
            snapshot["forecast"] = None
            snapshot["forecastNote"] = "No forecast artefact in this run."
        return snapshot

    @registry.register(
        "portwatch.forecast.get", READ,
        "The calibrated congestion forecast for one port.",
        arguments={"port_code": "UN/LOCODE or model id."},
        required=("port_code",),
        returns="Daily forecast points with q10/q50/q90 bands and a confidence.",
        computed_by="src.forecasting (adaptive ensemble + conformal calibration)",
        failure_modes=("No forecast artefact was exported for this port.",),
    )
    def forecast_get(port_code: str) -> Dict[str, Any]:
        forecasts = _read_cache("forecast_by_port.json")
        record = port_registry.resolve(port_code)
        for key in filter(None, [port_code, record.locode if record else None,
                                 record.model_id if record else None]):
            if key in forecasts:
                return {"portCode": key, "points": forecasts[key]}
        raise ToolUnavailable(f"no forecast series for {port_code} in this run")

    @registry.register(
        "portwatch.weather.get", READ,
        "Marine weather observations and the daily impact forecast per port.",
        arguments={"port_code": "Optional. Omit for every port."},
        returns="Weather signals: wind, gust, rain, visibility, storm risk, impact.",
        computed_by="src.ingestion.connectors.weather_live (Open-Meteo) via the pipeline",
        failure_modes=("The weather artefact has not been exported.",),
    )
    def weather_get(port_code: Optional[str] = None) -> Any:
        rows = _read_cache("weather_by_port.json")
        series = rows if isinstance(rows, list) else list(rows.values())
        if port_code is None:
            return series
        record = port_registry.resolve(port_code)
        wanted = {port_code.upper()}
        if record:
            wanted |= {record.locode, record.model_id}
        match = [r for r in series if str(r.get("portCode", "")).upper() in wanted]
        if not match:
            raise ToolUnavailable(f"no weather signal for {port_code} in this run")
        return match[0]

    @registry.register(
        "portwatch.global_eye.events", READ,
        "Deduplicated, corroborated maritime disruption events.",
        arguments={"category": "Optional category filter.",
                   "limit": "Optional maximum number of events."},
        returns="Events with sources, confidence, severity and calibrated probability.",
        computed_by="src.portwatch_os.global_eye (ingest + calibration)",
        failure_modes=("The news bundle has not been exported.",),
    )
    def global_eye_events(category: Optional[str] = None, limit: int = 40) -> Dict[str, Any]:
        bundle = _read_cache("news_bundle.json")
        events, report = from_news_bundle(bundle)
        calibrator = fit_calibrator(ledger.event_outcomes(), fitted_at=_now())
        stamped = apply_calibration(events, calibrator)
        if category:
            events = [e for e in events if e.category == category]
        return {
            "events": [e.to_dict() for e in events[: int(limit)]],
            "ingest": report.to_dict(),
            "calibration": {
                "available": calibrator.available,
                "stamped": stamped,
                "globalCount": calibrator.global_count,
            },
        }

    @registry.register(
        "portwatch.global_eye.exposure", READ,
        "The impact chain for one event: chokepoint, lanes, vessels, ports, actions.",
        arguments={"event_id": "Event id from portwatch.global_eye.events.",
                   "company_id": "Optional. Scope vessel exposure to this fleet."},
        required=("event_id",),
        returns="Lane, vessel and port exposure plus the actions the chain supports.",
        computed_by="src.portwatch_os.global_eye.exposure",
        failure_modes=("The event id is not in the current feed.",),
    )
    def global_eye_exposure(event_id: str, company_id: Optional[str] = None) -> Dict[str, Any]:
        bundle = _read_cache("news_bundle.json")
        events, _ = from_news_bundle(bundle)
        calibrator = fit_calibrator(ledger.event_outcomes(), fitted_at=_now())
        apply_calibration(events, calibrator)
        event = next((e for e in events if e.event_id == event_id), None)
        if event is None:
            raise ToolUnavailable(
                f"event {event_id} is not in the current feed; it may have aged out"
            )
        voyages = fleet.voyages() if (company_id is None or company_id == fleet.company_id) else []
        return build_impact(event, voyages).to_dict()

    @registry.register(
        "portwatch.company.fleet", READ,
        "The signed-in company's fleet and each vessel's current voyage.",
        arguments={"company_id": "Optional company id; defaults to the demo carrier."},
        returns="Fleet profile with vessels, lanes, ETAs and free capacity.",
        computed_by="src.portwatch_os.fleet.company",
        failure_modes=("The requested company is not configured.",),
    )
    def company_fleet(company_id: Optional[str] = None) -> Dict[str, Any]:
        if company_id and company_id != fleet.company_id:
            raise ToolUnavailable(
                f"no company account {company_id} is configured in this deployment"
            )
        return fleet.to_dict()

    @registry.register(
        "portwatch.company.risk", READ,
        "Which vessels in the fleet need intervention, and why.",
        arguments={"horizon_hours": "Look-ahead window. Defaults to 72."},
        returns="Ranked vessel exposures with deadlines and recommended actions.",
        computed_by="src.portwatch_os.global_eye.exposure over the company fleet",
        failure_modes=("The news bundle has not been exported.",),
    )
    def company_risk(horizon_hours: float = 72.0) -> Dict[str, Any]:
        bundle = _read_cache("news_bundle.json")
        events, _ = from_news_bundle(bundle)
        calibrator = fit_calibrator(ledger.event_outcomes(), fitted_at=_now())
        apply_calibration(events, calibrator)
        voyages = fleet.voyages()

        rows: List[Dict[str, Any]] = []
        impacts = []
        for event in events:
            impact = build_impact(event, voyages)
            if not impact.vessels:
                continue
            impacts.append(impact)
            for vessel in impact.vessels:
                if (
                    vessel.hours_to_risk_area is not None
                    and vessel.hours_to_risk_area > horizon_hours
                ):
                    continue
                rows.append({
                    **vessel.to_dict(),
                    "eventId": event.event_id,
                    "eventTitle": event.title,
                    "eventCategory": event.category,
                    "eventProbability": event.probability,
                    "eventConfidence": round(event.confidence, 3),
                })
        rows.sort(key=lambda r: (-r["exposure"], r.get("hoursToRiskArea") or 1e9))
        return {
            "companyId": fleet.company_id,
            "companyName": fleet.name,
            "horizonHours": horizon_hours,
            "vesselsExposed": len({r["vesselId"] for r in rows}),
            "fleetSize": len(fleet.vessels),
            "rows": rows,
            "portRisk": aggregate_port_risk(impacts),
            "disclaimer": fleet.disclaimer,
        }

    @registry.register(
        "portwatch.port_twin.state", READ,
        "The digital twin's logical state for one port.",
        arguments={"port_code": "UN/LOCODE.", "horizon_hours": "Optional look-ahead."},
        required=("port_code",),
        returns="Berths, cranes, yard blocks, sheds, calls and operational metrics.",
        computed_by="src.portwatch_os.twin.state",
        failure_modes=("No observed snapshot exists for the port.",),
    )
    def port_twin_state(port_code: str, horizon_hours: float = 24.0) -> Dict[str, Any]:
        snapshot = _port_snapshot(port_code)
        state = state_from_snapshot(port_code, snapshot)
        return state.to_dict()

    @registry.register(
        "portwatch.advisories.list", READ,
        "Advisories visible to the authenticated identity asking.",
        arguments={"port_code": "Optional port filter.",
                   "vessel_id": "Optional recipient vessel filter.",
                   "state": "Optional advisory state filter."},
        returns="Advisories with their state, evidence and audit trail.",
        computed_by="src.portwatch_os.advisories.store",
        failure_modes=(
            "No authenticated scope was supplied, and an agent does not hold one "
            "by default.",
            "Otherwise none: an empty register is a valid answer.",
        ),
        scoped=True,
    )
    def advisories_list(
        scope: ToolScope,
        port_code: Optional[str] = None,
        vessel_id: Optional[str] = None,
        state: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # The agent reads as the identity that asked, not as national command.
        # It used to read with a hardcoded admin principal on the reasoning that
        # it was assembling evidence for a controller who already held that
        # scope -- which stops being true the moment there is a second port or a
        # second carrier on the deployment.
        principal = _principal_for_scope(scope)
        return [
            a.to_dict(for_recipient=principal.role == RECIPIENT)
            for a in advisories.visible_to(
                principal, state=state, port_code=port_code, vessel_id=vessel_id
            )
        ]

    @registry.register(
        "portwatch.learning.reliability", READ,
        "Learned reliability weights per contributor and context.",
        arguments={"contributor": "Optional contributor filter."},
        returns="Weights with sample counts, error and the context each was fitted on.",
        computed_by="src.portwatch_os.learning.reliability",
        failure_modes=("No claims have resolved yet, so the table is empty.",),
    )
    def learning_reliability(contributor: Optional[str] = None) -> List[Dict[str, Any]]:
        return [
            {
                "contributor": r.contributor, "context": r.context_key,
                "weight": r.weight, "previousWeight": r.previous_weight,
                "samples": r.sample_count, "meanAbsoluteError": r.mean_absolute_error,
                "bias": r.bias, "updatedAt": r.updated_at, "notes": r.notes,
            }
            for r in ledger.reliability(contributor=contributor)
        ]

    @registry.register(
        "portwatch.learning.outcomes", READ,
        "Scored history: calibration, error and the largest misses.",
        arguments={"limit": "How many misses to return. Defaults to 10."},
        returns="Calibration and error reports sliced by domain, model and horizon.",
        computed_by="src.portwatch_os.learning.outcome_agent",
        failure_modes=("No resolved claims yet, in which case the report says so.",),
    )
    def learning_outcomes(limit: int = 10) -> Dict[str, Any]:
        agent = OutcomeAgent(ledger)
        scored = agent.score_history()
        resolved = ledger.predictions(status="resolved")
        return {
            "counts": ledger.counts(),
            "overall": scored["overall"].to_dict(),
            "byDomain": [s.to_dict() for s in scored["byDomain"]],
            "byModel": [s.to_dict() for s in scored["byModel"]],
            "byHorizon": [s.to_dict() for s in scored["byHorizon"]],
            "events": agent.score_events(),
            "decisions": agent.score_decisions(),
            "misses": [m.to_dict() for m in rank_misses(resolved, limit=int(limit))],
        }

    @registry.register(
        "portwatch.learning.policies", READ,
        "Learned policies and their promotion state.",
        returns="Policies with evaluation evidence, safety checks and approver.",
        computed_by="src.portwatch_os.twin.promotion",
        failure_modes=("No policy has been trained yet.",),
    )
    def learning_policies() -> Dict[str, Any]:
        active = active_policy(ledger)
        return {
            "policies": [
                {
                    "policyId": p.policy_id, "name": p.name, "family": p.family,
                    "version": p.version, "state": p.state,
                    "environment": p.environment, "evaluation": p.evaluation,
                    "safetyChecks": p.safety_checks, "approvedBy": p.approved_by,
                    "approvedAt": p.approved_at, "rejectionReason": p.rejection_reason,
                    "createdAt": p.created_at,
                }
                for p in ledger.policies()
            ],
            "activePolicyId": active.policy_id if active else None,
            "note": (
                "No learned policy is approved, so operational recommendations use the "
                "hand-written optimiser."
                if active is None else
                f"{active.name} is approved and may be used for recommendations."
            ),
        }

    @registry.register(
        "portwatch.provenance.get", READ,
        "The provenance state of every data source in this run.",
        returns="Sources with LIVE / CACHED_LIVE / STALE / SYNTHETIC / UNAVAILABLE.",
        computed_by="src.utils.provenance",
        failure_modes=("The provenance artefact has not been exported.",),
    )
    def provenance_get() -> Any:
        return _read_cache("provenance.json")

    @registry.register(
        "portwatch.audit.advisory", READ,
        "The full audit trail for one advisory.",
        arguments={"advisory_id": "Advisory id."},
        required=("advisory_id",),
        returns="Every transition with actor, role, timestamp and reason.",
        computed_by="src.portwatch_os.advisories.store",
        failure_modes=(
            "The advisory id does not exist.",
            "The asking identity is not entitled to that advisory.",
            "No authenticated scope was supplied.",
        ),
        scoped=True,
    )
    def audit_advisory(advisory_id: str, scope: ToolScope) -> List[Dict[str, Any]]:
        # The trail carries the issuing port's internal review, so it is gated by
        # the asking identity's visibility rather than by knowledge of the id.
        principal = _principal_for_scope(scope)
        try:
            return advisories.audit_trail(advisory_id, principal)
        except AuthorisationError as exc:
            raise ToolUnavailable(str(exc)) from exc
        except AdvisoryError as exc:
            raise ToolUnavailable(str(exc)) from exc

    # -------------------------------------------------------- SIMULATE --
    @registry.register(
        "portwatch.port_twin.simulate", SIMULATE,
        "Run the port twin forward under a scheduling policy.",
        arguments={"port_code": "UN/LOCODE.",
                   "policy": "fcfs | greedy | lookahead | random.",
                   "horizon_hours": "Simulation horizon. Defaults to 24."},
        required=("port_code",),
        returns="Metrics, snapshots at +2/+6/+12/+24h, reward breakdown, violations.",
        computed_by="src.portwatch_os.twin.simulation (deterministic, seeded)",
        failure_modes=("No observed snapshot for the port; unknown policy id.",),
    )
    def port_twin_simulate(
        port_code: str,
        policy: str = "greedy",
        horizon_hours: float = 24.0,
    ) -> Dict[str, Any]:
        snapshot = _port_snapshot(port_code)
        state = state_from_snapshot(port_code, snapshot)
        try:
            chosen = build_policy(policy)
        except KeyError as exc:
            raise ToolUnavailable(str(exc)) from exc
        result = simulate(
            state, chosen,
            SimulationConfig(horizon_hours=float(horizon_hours), record_trace=True),
        )
        return {
            "portCode": port_code,
            "policy": chosen.to_dict(),
            "metrics": result.metrics,
            "snapshots": {str(k): v for k, v in sorted(result.snapshots.items())},
            "reward": reward(result),
            "rewardBreakdown": reward_breakdown(result),
            "violations": result.violations,
            "rejectedActions": result.rejected_actions[:10],
            "geometryBasis": state.geometry_basis,
        }

    @registry.register(
        "portwatch.port_twin.benchmark", SIMULATE,
        "Compare scheduling policies on held-out simulated scenarios.",
        arguments={"port_code": "UN/LOCODE.", "episodes": "Held-out episodes. Defaults to 20."},
        returns="Every policy's mean reward, wait, turnaround and violations, ranked.",
        computed_by="src.portwatch_os.twin.rl",
        failure_modes=("None: the benchmark generates its own scenarios.",),
    )
    def port_twin_benchmark(port_code: str = "INMAA", episodes: int = 20) -> Dict[str, Any]:
        record = port_registry.resolve(port_code)
        spec = ScenarioSpec(
            port_code=port_code,
            berth_count=record.berth_count if record else 8,
            capacity_index=record.capacity if record else 0.7,
        )
        result = benchmark(
            PortEnvironment(spec), default_policies(), episodes=int(episodes), ran_at=_now()
        )
        return result.to_dict()

    @registry.register(
        "portwatch.routing.optimize", SIMULATE,
        "Score a passage against weather, port and chokepoint exposure.",
        arguments={"vessel_id": "Fleet vessel id.",
                   "destination": "Destination UN/LOCODE.",
                   "risk_tolerance": "low | medium | high."},
        required=("vessel_id",),
        returns="Route exposure, ETA effect, chokepoint risk, confidence, provenance.",
        computed_by="src.portwatch_os.global_eye.exposure + the port forecast artefacts",
        failure_modes=("The vessel is not in the fleet; the lane has no catalogue entry.",),
    )
    def routing_optimize(
        vessel_id: str,
        destination: Optional[str] = None,
        risk_tolerance: str = "medium",
    ) -> Dict[str, Any]:
        vessel = fleet.vessel(vessel_id)
        if vessel is None:
            raise ToolUnavailable(
                f"{vessel_id} is not in the {fleet.name} fleet"
            )
        destination = destination or vessel.destination_port
        lane = TRADE_LANES.get(vessel.lane_code or "")

        bundle = _read_cache("news_bundle.json")
        events, _ = from_news_bundle(bundle)
        calibrator = fit_calibrator(ledger.event_outcomes(), fitted_at=_now())
        apply_calibration(events, calibrator)

        exposures: List[Dict[str, Any]] = []
        for event in events:
            impact = build_impact(event, [vessel.to_voyage()])
            for row in impact.vessels:
                if row.vessel_id != vessel_id:
                    continue
                exposures.append({
                    **row.to_dict(),
                    "eventId": event.event_id,
                    "eventTitle": event.title,
                    "eventProbability": event.probability,
                })
        exposures.sort(key=lambda r: -r["exposure"])

        # Risk tolerance sets the threshold at which a diversion is recommended.
        # It changes the *decision*, never the measurement.
        thresholds = {"low": 0.25, "medium": 0.40, "high": 0.60}
        threshold = thresholds.get(risk_tolerance, 0.40)
        worst = exposures[0]["exposure"] if exposures else 0.0

        port_risk = None
        if destination:
            try:
                port_risk = _port_snapshot(destination).get("risk")
            except ToolUnavailable:
                port_risk = None

        return {
            "vesselId": vessel_id,
            "vesselName": vessel.name,
            "destination": destination,
            "lane": lane.name if lane else None,
            "primaryRoutingNm": lane.primary_nm if lane else None,
            "alternativeRouting": lane.alternative if lane else None,
            "detourNm": lane.detour_nm if lane else None,
            "detourHours": (
                round(lane.detour_nm / vessel.service_speed_kn, 1)
                if lane and lane.detour_nm else None
            ),
            "chokepointExposure": exposures[:6],
            "worstExposure": round(worst, 3),
            "riskTolerance": risk_tolerance,
            "threshold": threshold,
            "recommendation": (
                "evaluate_diversion" if worst >= threshold else "maintain_routing"
            ),
            "destinationPortRisk": port_risk,
            "currentEta": vessel.eta,
            "provenance": {
                "routing": "Water-only routing graph; non-navigational.",
                "positions": vessel.position_source,
                "events": "GDELT/GDACS via the pipeline; see portwatch.provenance.get.",
            },
            "note": (
                "This is decision support, not a passage plan. Routing geometry is "
                "non-navigational and must not be used for navigation."
            ),
        }

    @registry.register(
        "portwatch.cargo.opportunities", SIMULATE,
        "Feasible transshipment connections at a port, ranked by value.",
        arguments={"port_code": "UN/LOCODE.", "limit": "Maximum rows. Defaults to 20."},
        required=("port_code",),
        returns="Connections with capacity, window, handling time and value.",
        computed_by="src.portwatch_os.cargo.optimizer",
        failure_modes=("No observed snapshot for the port.",),
    )
    def cargo_opportunities(port_code: str, limit: int = 20) -> Dict[str, Any]:
        snapshot = _port_snapshot(port_code)
        state = state_from_snapshot(port_code, snapshot)
        manifest = [s for s in demo_manifest(port_code) if s.inbound_vessel_id]
        rows = opportunities(
            manifest, capacities_for(fleet), zones_from_state(state), limit=int(limit)
        )
        from src.portwatch_os.cargo.model import CARGO_DISCLAIMER
        return {
            "portCode": port_code,
            "opportunities": rows,
            "shipmentsConsidered": len(manifest),
            "disclaimer": CARGO_DISCLAIMER,
        }

    @registry.register(
        "portwatch.cargo.optimize", SIMULATE,
        "Assign transshipment cargo to onward sailings and yard zones.",
        arguments={"port_code": "UN/LOCODE."},
        required=("port_code",),
        returns="Assignments, unplaced shipments with reasons, and the value gap.",
        computed_by="src.portwatch_os.cargo.optimizer",
        failure_modes=("No observed snapshot for the port.",),
    )
    def cargo_optimize(port_code: str) -> Dict[str, Any]:
        snapshot = _port_snapshot(port_code)
        state = state_from_snapshot(port_code, snapshot)
        manifest = [s for s in demo_manifest(port_code) if s.inbound_vessel_id]
        plan = optimise(
            port_code, manifest, capacities_for(fleet), zones_from_state(state)
        )
        return plan.to_dict()

    @registry.register(
        "portwatch.scenarios.simulate", SIMULATE,
        "Propagate a shock through the port network.",
        arguments={"shock_type": "chokepoint_closure | strike | weather_extreme | conflict.",
                   "severity": "0..1.", "chokepoint": "Optional chokepoint code."},
        required=("shock_type",),
        returns="Per-port congestion and delay deltas under the shock.",
        computed_by="src.decision.scenario_engine",
        failure_modes=("The forecast artefact has not been exported.",),
    )
    def scenarios_simulate(
        shock_type: str,
        severity: float = 0.7,
        chokepoint: Optional[str] = None,
    ) -> Dict[str, Any]:
        forecasts = _read_cache("forecast_by_port.json")
        from src.portwatch_os.global_eye.exposure import TRADE_LANES as LANES

        affected = [
            lane for lane in LANES.values()
            if chokepoint is None or chokepoint in lane.chokepoints
        ]
        ports = sorted({p for lane in affected for p in lane.india_ports})
        rows = []
        for code in ports:
            series = forecasts.get(code) or []
            base = float(series[0].get("q50", 0.0)) if series else 0.0
            # Delta is severity-scaled against the lane's own detour cost, so a
            # chokepoint with no alternative bites harder than one with a bypass.
            lanes_here = [l for l in affected if code in l.india_ports]
            worst = max(
                (1.4 if l.alternative is None else min(1.0, (l.detour_nm or 0) / 4000.0)
                 for l in lanes_here),
                default=0.0,
            )
            delta = base * float(severity) * worst * 0.35
            rows.append({
                "portCode": code,
                "baselineCongestion": round(base, 2),
                "shockedCongestion": round(base + delta, 2),
                "deltaCongestion": round(delta, 2),
                "lanes": [l.code for l in lanes_here],
            })
        rows.sort(key=lambda r: -r["deltaCongestion"])
        return {
            "shockType": shock_type,
            "severity": severity,
            "chokepoint": chokepoint,
            "affectedLanes": [l.code for l in affected],
            "ports": rows,
            "method": (
                "Baseline forecast scaled by shock severity and the lane's diversion "
                "cost. Lanes with no alternative routing take a larger multiplier."
            ),
        }

    # --------------------------------------------------------- PROPOSE --
    @registry.register(
        "portwatch.advisories.draft", PROPOSE,
        "Draft a port-to-vessel advisory for a controller to review.",
        arguments={
            "port_code": "Issuing port.", "vessel_id": "Recipient vessel id.",
            "kind": "arrival_window | speed | berth | holding | approach | cargo_transfer.",
            "recommendation": "The recommendation payload for this kind.",
            "reason": "Plain-language justification a master can evaluate.",
            "issuer": "Name of the controller the draft is raised for.",
        },
        required=("port_code", "vessel_id", "kind", "recommendation", "reason"),
        returns="The draft advisory. Not visible to the recipient until issued.",
        computed_by="src.portwatch_os.advisories (the numbers must come from a model)",
        failure_modes=("The advisory is not well formed; the vessel is unknown.",),
    )
    def advisories_draft(
        port_code: str,
        vessel_id: str,
        kind: str,
        recommendation: Dict[str, Any],
        reason: str,
        issuer: str = "PortWatch decision engine",
        model_confidence: Optional[float] = None,
        evidence: Optional[Dict[str, Any]] = None,
        prediction_ids: Optional[Sequence[str]] = None,
        valid_until: Optional[str] = None,
    ) -> Dict[str, Any]:
        vessel = fleet.vessel(vessel_id)
        record = port_registry.resolve(port_code)
        created = _now()
        advisory = Advisory(
            advisory_id=Advisory.make_id(port_code, vessel_id, kind, created),
            kind=kind,
            port_code=(record.locode if record else port_code),
            issuer=issuer,
            issuer_organisation=(record.authority if record else port_code),
            recipient_vessel_id=vessel_id,
            recipient_vessel_name=(vessel.name if vessel else vessel_id),
            recipient_organisation=(fleet.name if vessel else "Unknown operator"),
            created_at=created,
            recommendation=dict(recommendation),
            reason=reason,
            model_confidence=model_confidence,
            evidence=dict(evidence or {}),
            prediction_ids=list(prediction_ids or []),
            valid_until=valid_until,
        )
        try:
            advisories.create(advisory)
        except AdvisoryError as exc:
            raise ToolUnavailable(str(exc)) from exc
        return {
            **advisory.to_dict(),
            "note": (
                "Draft only. It is not visible to the recipient and will not be until "
                "a named port controller reviews and issues it."
            ),
        }

    # --------------------------------------------------------- EXECUTE --
    @registry.register(
        "portwatch.advisories.issue", EXECUTE,
        "Issue a reviewed advisory to its recipient. Requires human approval.",
        arguments={"advisory_id": "Advisory to issue."},
        required=("advisory_id",),
        returns="The issued advisory, now visible to the recipient.",
        computed_by="src.portwatch_os.advisories.store (state machine + authorisation)",
        failure_modes=("Not in a reviewable state; the approver does not hold the port.",),
    )
    def advisories_issue(advisory_id: str, approval: ApprovalContext) -> Dict[str, Any]:
        advisory = advisories.require(advisory_id)
        if not approval.authorises(advisory_id):
            raise ToolError(
                f"this approval names {approval.subject or 'no subject'} and cannot "
                f"issue {advisory_id}. An EXECUTE mandate is bound to the artefact "
                "the human actually looked at.",
                recoverable=False,
            )
        if advisory.state != UNDER_REVIEW:
            raise ToolError(
                f"{advisory_id} is {advisory.state}. A draft becomes visible to its "
                "recipient only after a named controller reviews it; issuing "
                "straight from a draft would skip that review.",
                recoverable=False,
            )
        # The issuer's scope is the one the session authenticated, not the one
        # written on the record -- reading it off the target would make the
        # store's port check compare a value against itself.
        principal = Principal(
            actor=approval.actor, role=ISSUER, port_code=approval.port_code,
            is_admin=approval.is_admin,
        )
        issued = advisories.act(
            advisory_id, ISSUED, principal=principal,
            reason=approval.reason or "approved by the duty controller",
        )
        return issued.to_dict()

    @registry.register(
        "portwatch.advisories.respond", EXECUTE,
        "Record a recipient's response to an issued advisory.",
        arguments={"advisory_id": "Advisory id.",
                   "response": "accepted | queried | declined | acknowledged.",
                   "reason": "Required for queried and declined."},
        required=("advisory_id", "response"),
        returns="The advisory in its new state.",
        computed_by="src.portwatch_os.advisories.store",
        failure_modes=("Illegal transition; the responder is not the recipient.",),
    )
    def advisories_respond(
        advisory_id: str,
        response: str,
        approval: ApprovalContext,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        advisories.require(advisory_id)
        if not approval.authorises(advisory_id):
            raise ToolError(
                f"this approval names {approval.subject or 'no subject'} and cannot "
                f"respond to {advisory_id}.",
                recoverable=False,
            )
        principal = Principal(
            actor=approval.actor, role=RECIPIENT,
            organisation=approval.organisation,
            vessel_ids=list(approval.vessel_ids),
            is_admin=approval.is_admin,
        )
        updated = advisories.act(
            advisory_id, response, principal=principal, reason=reason,
        )
        return updated.to_dict()

    return registry


__all__ = ["build_registry"]
