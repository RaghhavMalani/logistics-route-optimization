"""The port digital twin: state, forward simulation and cargo assignment.

Serves the same :class:`~src.portwatch_os.twin.state.PortState` the RL
environment trains in. The 3D renderer consumes ``/port-twin/{port}``; the
overlays and the ``+2h / +6h / +12h / +24h`` controls consume
``/port-twin/{port}/simulate``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.portwatch_os.cargo.model import CARGO_DISCLAIMER, demo_manifest, zones_from_state
from src.portwatch_os.cargo.optimizer import optimise
from src.portwatch_os.twin.policies import POLICY_REGISTRY, build_policy
from src.portwatch_os.twin.rl import PortEnvironment, ScenarioSpec, benchmark, default_policies
from src.portwatch_os.twin.simulation import (
    SimulationConfig,
    reward,
    reward_breakdown,
    simulate,
)
from src.portwatch_os.twin.state import PortState, state_from_snapshot
from src.utils import port_registry

router = APIRouter()

#: Horizons the 3D twin's time control offers.
SNAPSHOT_HOURS = (2, 6, 12, 24)


def _snapshot(port_code: str) -> Dict[str, Any]:
    from backend.app.services import cache_service as cache

    try:
        state = cache.get_port_state()
    except cache.CacheNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    record = port_registry.resolve(port_code)
    for key in filter(None, [port_code, port_code.upper(),
                             record.locode if record else None,
                             record.model_id if record else None]):
        if key in state:
            return state[key]
    raise HTTPException(
        status_code=404,
        detail=(
            f"No observed state for {port_code} in this run. Ports available: "
            f"{', '.join(sorted(state)[:14])}"
        ),
    )


def build_state_for(port_code: str) -> PortState:
    """The twin for a port, seeded from its observed snapshot."""
    snapshot = _snapshot(port_code)
    record = port_registry.resolve(port_code)
    from src.portwatch_os.twin.state import state_from_snapshot as build

    return build(
        record.locode if record else port_code,
        {**snapshot, "berthCount": snapshot.get("berthCount") or (
            record.berth_count if record else None
        ), "capacityIndex": snapshot.get("capacityIndex") or (
            record.capacity if record else None
        )},
        epoch=snapshot.get("observedAt"),
    )


@router.get("/port-twin/{port_code}")
def port_twin(port_code: str) -> Dict[str, Any]:
    """The twin's logical state. What the 3D renderer projects."""
    state = build_state_for(port_code)
    return state.to_dict()


@router.get("/port-twin/{port_code}/simulate")
def port_twin_simulate(
    port_code: str,
    policy: str = Query("greedy", description="Scheduling policy to run."),
    horizon_hours: float = Query(24.0, ge=1.0, le=168.0),
) -> Dict[str, Any]:
    """Run the twin forward and return the state at each overlay horizon."""
    if policy not in POLICY_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown policy '{policy}'. Known: {', '.join(sorted(POLICY_REGISTRY))}",
        )
    state = build_state_for(port_code)
    chosen = build_policy(policy)
    result = simulate(
        state, chosen,
        SimulationConfig(horizon_hours=horizon_hours, record_trace=True),
        snapshot_hours=SNAPSHOT_HOURS,
    )
    return {
        "portCode": state.port_code,
        "portName": state.port_name,
        "policy": chosen.to_dict(),
        "horizonHours": horizon_hours,
        "metrics": result.metrics,
        "snapshots": {str(k): v for k, v in sorted(result.snapshots.items())},
        "reward": round(reward(result), 3),
        "rewardBreakdown": reward_breakdown(result),
        "violations": result.violations,
        "rejectedActions": result.rejected_actions[:20],
        "trace": [event.to_dict() for event in result.trace[:120]],
        "finalState": result.final_state.to_dict(),
        "geometryBasis": state.geometry_basis,
        "note": (
            "Deterministic given the port state and the policy. The same engine "
            "generates the RL environment's episodes, so a policy result here and a "
            "benchmark result describe the same simulator."
        ),
    }


@router.get("/port-twin/{port_code}/optimize")
def port_twin_optimize(
    port_code: str,
    horizon_hours: float = Query(24.0, ge=1.0, le=168.0),
) -> Dict[str, Any]:
    """Compare every scheduling policy on this port's actual state.

    This is the port-optimisation surface: not a benchmark on synthetic
    scenarios, but the same policies run against the port as observed right now,
    so a controller can see what each would do today.
    """
    base = build_state_for(port_code)
    rows: List[Dict[str, Any]] = []
    for policy_id in sorted(POLICY_REGISTRY):
        policy = build_policy(policy_id)
        result = simulate(
            base.clone(), policy,
            SimulationConfig(horizon_hours=horizon_hours, record_trace=False),
            snapshot_hours=(),
        )
        rows.append({
            "policy": policy.to_dict(),
            "metrics": result.metrics,
            "reward": round(reward(result), 3),
            "rewardBreakdown": reward_breakdown(result),
            "violations": len(result.violations),
            "rejectedActions": len(result.rejected_actions),
        })

    rows.sort(key=lambda r: -r["reward"])
    baseline = next((r for r in rows if r["policy"]["policyId"] == "fcfs"), None)
    for row in rows:
        if baseline and abs(baseline["reward"]) > 1e-6:
            row["improvementVsBaseline"] = round(
                (row["reward"] - baseline["reward"]) / abs(baseline["reward"]), 4
            )
        else:
            row["improvementVsBaseline"] = None

    return {
        "portCode": base.port_code,
        "horizonHours": horizon_hours,
        "policies": rows,
        "baselinePolicyId": "fcfs",
        "geometryBasis": base.geometry_basis,
        "note": (
            "Every policy ran against the same observed port state. Reward is the "
            "operational cost function in src.portwatch_os.twin.simulation; higher is "
            "better. No learned policy is used unless one has been promoted."
        ),
    }


@router.get("/port-twin/{port_code}/benchmark")
def port_twin_benchmark(
    port_code: str,
    episodes: int = Query(20, ge=5, le=120),
) -> Dict[str, Any]:
    """Policy comparison on held-out simulated scenarios."""
    record = port_registry.resolve(port_code)
    spec = ScenarioSpec(
        port_code=(record.locode if record else port_code),
        berth_count=record.berth_count if record else 8,
        capacity_index=record.capacity if record else 0.7,
    )
    result = benchmark(
        PortEnvironment(spec), default_policies(), episodes=episodes,
        ran_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return result.to_dict()


@router.get("/cargo/opportunities")
def cargo_opportunities(
    port_code: str = Query(...),
    limit: int = Query(25, ge=1, le=100),
) -> Dict[str, Any]:
    from backend.app.routes.company import resolve_company
    from src.portwatch_os.cargo.optimizer import opportunities
    from src.portwatch_os.fleet.company import capacities_for

    profile = resolve_company(None)
    state = build_state_for(port_code)
    manifest = [s for s in demo_manifest(port_code) if s.inbound_vessel_id]
    rows = opportunities(
        manifest, capacities_for(profile) if profile else [],
        zones_from_state(state), limit=limit,
    )
    return {
        "portCode": port_code,
        "opportunities": rows,
        "shipmentsConsidered": len(manifest),
        "disclaimer": CARGO_DISCLAIMER,
    }


@router.get("/cargo/optimize")
def cargo_optimize(port_code: str = Query(...)) -> Dict[str, Any]:
    """Assign transshipment cargo to onward sailings and yard zones."""
    from backend.app.routes.company import resolve_company
    from src.portwatch_os.fleet.company import capacities_for

    profile = resolve_company(None)
    state = build_state_for(port_code)
    manifest = [s for s in demo_manifest(port_code) if s.inbound_vessel_id]
    plan = optimise(
        state.port_code, manifest,
        capacities_for(profile) if profile else [],
        zones_from_state(state),
    )
    payload = plan.to_dict()
    payload["yardBlocks"] = [b.to_dict() for b in state.yard_blocks]
    payload["geometryBasis"] = state.geometry_basis
    return payload
