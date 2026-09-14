"""Cargo decisions through the cargo model, on the same decision model as a
vessel's routing and a port's berth plan.

Shipment X misses its booked connection. The options are to keep the booking
and see whether it makes it, to move the consignment to another vessel that
serves its destination, to stage it in a yard zone nearer the quay so the
transfer is faster, or to wait for the next sailing. Each option is checked
by the cargo model's feasibility rules -- capacity, reefer plugs, dangerous
goods, deadweight, the connection window -- and a failed rule is a hard
constraint: the option is REJECTED with the rule, not scored lower.

Objectives are the ones a cargo planner reads: when it sails, how much slack
it has, how long it dwells, how many handling hours it costs, what it costs
where a storage or missed-connection basis exists. Arrival at the far port is
*not* measured -- no onward transit schedule is held -- and the problem says
so rather than inventing one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.cargo.model import (
    Connection,
    Shipment,
    StorageZone,
    VesselCapacity,
    evaluate_connection,
)
from src.portwatch_os.decision.actions import (
    CHANGE_CONNECTION,
    CHANGE_YARD,
    DEFER_SHIPMENT,
    KEEP_CONNECTION,
    TRANSFER_TO_VESSEL,
    availability_of,
    for_domain,
)
from src.portwatch_os.decision.model import (
    AVAILABLE,
    Availability,
    CARGO_CONNECTION,
    ConstraintResult,
    DecisionActor,
    DecisionEvaluation,
    DecisionOption,
    DecisionProblem,
    FEASIBLE,
    Measure,
    OBJECTIVES,
    REJECTED,
    UNAVAILABLE,
    known,
    unknown,
)
from src.portwatch_os.finance.basis import CostBasis
from src.portwatch_os.finance.evaluate import Pricer
from src.portwatch_os.finance.money import DAY, FxTable, Quantity as MoneyQuantity, TEU, TEU_DAY
from src.portwatch_os.world.quantity import utc

#: The cargo model's handling and window arithmetic is a model of the terminal.
CARGO_CONFIDENCE = 0.6
CARGO_OBJECTIVES: Tuple[str, ...] = (
    "sailing", "slack", "dwell", "handling", "missed_connection", "cost", "uncertainty",
)
FRONTIER_OBJECTIVES: Tuple[str, ...] = ("sailing", "slack", "dwell")
MAX_TRANSFER_CANDIDATES = 3


class CargoDecisionError(ValueError):
    """The manifest does not hold what a connection decision needs."""


@dataclass
class CargoPlan:
    action: str
    label: str
    params: Dict[str, Any]
    vessel: VesselCapacity
    zone: Optional[StorageZone]
    is_baseline: bool = False


def _serving(vessels: Sequence[VesselCapacity], shipment: Shipment) -> List[VesselCapacity]:
    return sorted(
        (v for v in vessels if v.serves(shipment.destination_port)),
        key=lambda v: (v.departure_hour if v.departure_hour is not None else float("inf")),
    )


def _usable_zones(shipment: Shipment, zones: Sequence[StorageZone]) -> List[StorageZone]:
    out = [
        z for z in zones
        if z.free_teu >= shipment.teu
        and (not shipment.spec.needs_power or z.reefer_plugs_free >= int(shipment.teu))
        and (shipment.cargo_class != "hazardous" or z.accepts_hazardous)
        and (shipment.cargo_class != "oog" or z.accepts_oog)
    ]
    return sorted(out, key=lambda z: z.quay_transfer_minutes_per_teu)


def _plans(
    shipment: Shipment,
    vessels: Sequence[VesselCapacity],
    zones: Sequence[StorageZone],
    actor: str,
) -> Tuple[List[CargoPlan], List[Dict[str, Any]]]:
    booked = next((v for v in vessels if v.vessel_id == shipment.booked_vessel_id), None)
    serving = _serving(vessels, shipment)
    current_zone = next((z for z in zones if z.zone_id == shipment.yard_block_id), None)
    usable = _usable_zones(shipment, zones)
    alternatives = [v for v in serving if booked is None or v.vessel_id != booked.vessel_id]
    # "Wait for the next sailing" is distinct from a transfer only when the next
    # sailing is not already offered as one; otherwise the two would be the same
    # option under two names.
    offered = {v.vessel_id for v in alternatives[:MAX_TRANSFER_CANDIDATES]}
    later = [v for v in alternatives
             if booked is not None and booked.departure_hour is not None and v.departure_hour is not None
             and v.departure_hour > booked.departure_hour and v.vessel_id not in offered]
    subject = {
        "booked_vessel": None if booked is None else booked.vessel_id,
        "candidate_vessels": [v.vessel_id for v in alternatives] or None,
        "next_sailing": later[0].vessel_id if later else None,
        "zones": [z.zone_id for z in usable] or None,
        "hub_schedules": None,
    }
    checks = {
        DEFER_SHIPMENT: lambda s: Availability(AVAILABLE) if later else Availability(
            UNAVAILABLE, "every later sailing to the destination is already offered as a transfer"),
        CHANGE_YARD: lambda s: Availability(AVAILABLE) if any(
            current_zone is None or z.quay_transfer_minutes_per_teu < current_zone.quay_transfer_minutes_per_teu
            for z in usable
        ) else Availability(UNAVAILABLE, "no usable zone is nearer the quay than the current one"),
    }
    plans: List[CargoPlan] = []
    rows: List[Dict[str, Any]] = []
    for spec in for_domain(CARGO_CONNECTION):
        availability = availability_of(spec, subject, actor=actor, checks=checks)
        rows.append({**spec.to_dict(), "availability": availability.to_dict()})
        if not availability.available:
            continue
        if spec.kind == KEEP_CONNECTION and booked is not None:
            plans.append(CargoPlan(KEEP_CONNECTION, f"Keep the booking on {booked.name}",
                                   {"vesselId": booked.vessel_id, "zoneId": shipment.yard_block_id},
                                   booked, current_zone, is_baseline=True))
        elif spec.kind == TRANSFER_TO_VESSEL:
            for vessel in alternatives[:MAX_TRANSFER_CANDIDATES]:
                plans.append(CargoPlan(TRANSFER_TO_VESSEL, f"Transfer to {vessel.name}",
                                       {"vesselId": vessel.vessel_id, "zoneId": shipment.yard_block_id},
                                       vessel, current_zone))
        elif spec.kind == CHANGE_YARD and booked is not None:
            nearer = [z for z in usable if current_zone is None
                      or z.quay_transfer_minutes_per_teu < current_zone.quay_transfer_minutes_per_teu]
            if nearer:
                zone = nearer[0]
                plans.append(CargoPlan(CHANGE_YARD, f"Stage in {zone.name} and keep {booked.name}",
                                       {"vesselId": booked.vessel_id, "zoneId": zone.zone_id}, booked, zone))
        elif spec.kind == DEFER_SHIPMENT and later:
            vessel = later[0]
            plans.append(CargoPlan(DEFER_SHIPMENT, f"Wait for {vessel.name}",
                                   {"vesselId": vessel.vessel_id, "zoneId": shipment.yard_block_id},
                                   vessel, current_zone))
    return plans, rows


def evaluate_plan(
    plan: CargoPlan,
    shipment: Shipment,
    *,
    now_hour: float,
    basis: CostBasis,
    fx: FxTable,
    currency: str,
    at: datetime,
    port_code: str,
) -> DecisionOption:
    connection: Connection = evaluate_connection(shipment, plan.vessel, zone=plan.zone, now_hour=now_hour)
    window = connection.window
    measures: Dict[str, Measure] = {}
    basis_note = f"cargo.model.evaluate_connection on {plan.vessel.vessel_id}"
    departure = plan.vessel.departure_hour
    measures["sailing"] = (known(departure, "hours", basis=basis_note + " (vessel departure hour)", confidence=CARGO_CONFIDENCE)
                           if departure is not None else unknown("hours", f"{plan.vessel.name} declares no sailing time"))
    measures["slack"] = (known(window.slack_hours, "hours", basis=basis_note + " (cutoff minus ready)", confidence=CARGO_CONFIDENCE)
                         if window.slack_hours is not None else unknown("hours", f"{plan.vessel.name} declares no loading cut-off"))
    available = shipment.available_hour if shipment.available_hour is not None else now_hour
    measures["dwell"] = (known(max(0.0, departure - available), "hours", basis=basis_note + " (departure minus available)", confidence=CARGO_CONFIDENCE)
                         if departure is not None else unknown("hours", f"{plan.vessel.name} declares no sailing time"))
    measures["handling"] = known(window.handling_hours, "hours", basis=basis_note + " (total_handling_hours)", confidence=CARGO_CONFIDENCE,
                                 directTransfer=connection.direct_transfer)
    measures["missed_connection"] = known(0.0 if connection.feasible else shipment.teu, "teu",
                                          basis=basis_note + " (feasible -> 0, else the whole consignment)",
                                          confidence=CARGO_CONFIDENCE)

    pricer = Pricer(basis, at=at, currency=currency, fx=fx, scope=port_code)
    dwell = measures["dwell"]
    components = [
        pricer.priced("storage", "Yard storage", "yard_storage_teu_day",
                      None if not dwell.available else MoneyQuantity(shipment.teu * dwell.value / 24.0, TEU_DAY),
                      driver="dwell", zero_because="the consignment does not dwell"),
        pricer.priced("missed", "Missed connection", "missed_connection_teu",
                      MoneyQuantity(measures["missed_connection"].value, TEU), driver="missed_connection",
                      zero_because="the connection is made"),
        pricer.unknown("handling", "Terminal handling", "no terminal handling rate per move is configured"),
    ]
    financial = pricer.evaluation(components).to_dict()
    measures["cost"] = (known(financial["total"]["amount"], "money", basis="finance.evaluate.Pricer",
                              confidence=0.5 if financial.get("assumption") else 0.8, currency=currency)
                        if financial.get("total") is not None
                        else unknown("money", "; ".join(u["reason"] for u in financial["unknown"])))
    measures["uncertainty"] = known(1.0 - CARGO_CONFIDENCE, "ratio", basis="the cargo model is schematic; see CARGO_DISCLAIMER",
                                    confidence=1.0)

    constraints = [
        ConstraintResult(f"cargo_rule_{index}", "Cargo feasibility rule", False, True, reason,
                         basis="cargo.model.check_compatibility / check_zone / TransferWindow")
        for index, reason in enumerate(connection.reasons)
    ] or [ConstraintResult("cargo_rules", "Cargo feasibility rules", True, True,
                           "capacity, plugs, dangerous goods, deadweight and window all hold",
                           basis="cargo.model.evaluate_connection")]
    constraints.append(ConstraintResult(
        "onward_arrival", "Arrival at destination", True, False,
        "not measured: no onward transit schedule is held", basis="cargo model",
    ))
    rejected = [c for c in constraints if c.hard and not c.passed]
    evaluation = DecisionEvaluation(
        objectives=measures,
        consequences=[{"node": f"vessel:{plan.vessel.vessel_id}", "kind": "vessel", "label": plan.vessel.name,
                       "connection": connection.to_dict()}],
        derived={"vesselId": plan.vessel.vessel_id, "vesselName": plan.vessel.name,
                 "zoneId": None if plan.zone is None else plan.zone.zone_id,
                 "readyHour": round(window.ready_hour, 2), "cutoffHour": window.cutoff_hour,
                 "departureHour": departure, "directTransfer": connection.direct_transfer},
        financial=financial, computed_at=utc().isoformat(timespec="seconds"),
    )
    suffix = "" if plan.action in (KEEP_CONNECTION, CHANGE_YARD) else f"-{plan.vessel.vessel_id}"
    provenance = {"model": "src.portwatch_os.cargo.model.evaluate_connection",
                  "closesInHours": None if window.cutoff_hour is None else max(0.0, window.cutoff_hour - now_hour)}
    if rejected:
        provenance["rejectedEvaluation"] = evaluation.to_dict()
    return DecisionOption(
        option_id=plan.action.lower() + suffix, action=plan.action, label=plan.label, actor="",
        params=plan.params, constraints=constraints, status=REJECTED if rejected else FEASIBLE,
        evaluation=None if rejected else evaluation, is_baseline=plan.is_baseline,
        assumptions=[{"kind": "connection", "vesselId": plan.vessel.vessel_id,
                      "zoneId": None if plan.zone is None else plan.zone.zone_id, "source": "ASSUMPTION"}],
        provenance=provenance,
        timeline=[m for m in (
            {"kind": "ready", "subject": shipment.shipment_id, "hours": round(window.ready_hour - now_hour, 1)},
            None if window.cutoff_hour is None else {"kind": "deadline", "subject": plan.vessel.vessel_id,
                                                      "hours": round(window.cutoff_hour - now_hour, 1)},
            None if departure is None else {"kind": "sailing", "subject": plan.vessel.vessel_id,
                                            "hours": round(departure - now_hour, 1)},
        ) if m is not None],
    )


def build_cargo_problem(
    shipment: Shipment,
    vessels: Sequence[VesselCapacity],
    zones: Sequence[StorageZone],
    *,
    decision_id: str,
    actor: DecisionActor,
    at: datetime,
    port_code: str,
    world_state_id: str,
    world_revision: Dict[str, Any],
    basis: CostBasis,
    fx: Optional[FxTable] = None,
    currency: str = "USD",
    now_hour: float = 0.0,
    attention_item_id: Optional[str] = None,
) -> DecisionProblem:
    if shipment.booked_vessel_id is None:
        raise CargoDecisionError(f"{shipment.shipment_id} is booked on no vessel; there is no connection to decide about")
    plans, rows = _plans(shipment, vessels, zones, actor.role)
    if not any(p.is_baseline for p in plans):
        raise CargoDecisionError(f"{shipment.shipment_id}'s booked vessel {shipment.booked_vessel_id} is not in the capacity list")
    table = fx if fx is not None else FxTable()
    options = [evaluate_plan(p, shipment, now_hour=now_hour, basis=basis, fx=table, currency=currency, at=at,
                             port_code=port_code) for p in plans]
    for option in options:
        option.actor = actor.role
    baseline = next(o for o in options if o.is_baseline)
    windows = [o.provenance.get("closesInHours") for o in options
               if o.feasible and o.provenance.get("closesInHours") is not None]
    window = min(windows) if windows else None
    problem = DecisionProblem(
        decision_id=decision_id, created_at=utc().isoformat(timespec="seconds"), domain=CARGO_CONNECTION,
        world_revision=world_revision, world_state_id=world_state_id,
        subject_type="cargo", subject_id=shipment.shipment_id,
        subject_label=f"{shipment.shipment_id} ({shipment.teu:.0f} TEU {shipment.spec.label.lower()} to {shipment.destination_port})",
        actor=actor, attention_item_id=attention_item_id, decision_window_hours=window, at=at.isoformat(),
        objectives=[OBJECTIVES[k] for k in CARGO_OBJECTIVES],
        hard_constraints=["cargo_rules"], soft_constraints=["onward_arrival"],
        available_actions=rows, baseline_option_id=baseline.option_id, options=options,
        evidence={
            "shipment": shipment.to_dict(),
            "vessels": [v.to_dict() for v in vessels if v.serves(shipment.destination_port)],
            "zones": [z.to_dict() for z in zones][:12],
            "nowHour": now_hour,
            "costBasis": basis.coverage(at=at, scope=port_code),
            "frontierObjectives": list(FRONTIER_OBJECTIVES),
            "disclaimer": "demo manifest; see CARGO_DISCLAIMER",
        },
        headline=f"{shipment.shipment_id} · connection to {shipment.destination_port}",
        do_nothing_statement=_do_nothing(baseline, shipment),
    )
    problems = problem.validate()
    if problems:
        raise CargoDecisionError("; ".join(problems))
    return problem


def _do_nothing(baseline: DecisionOption, shipment: Shipment) -> str:
    if baseline.status == REJECTED:
        return "If unchanged: the booked connection is missed -- " + "; ".join(c.detail for c in baseline.rejected_by)
    slack = baseline.measure("slack")
    sailing = baseline.measure("sailing")
    parts = []
    if sailing is not None and sailing.available:
        parts.append(f"sails at hour {sailing.value:.0f}")
    if slack is not None and slack.available:
        parts.append(f"{slack.value:.1f} h of slack")
    return "If unchanged: " + ", ".join(parts) if parts else "If unchanged: the booked connection cannot be checked"


__all__ = [
    "CARGO_CONFIDENCE",
    "CARGO_OBJECTIVES",
    "CargoDecisionError",
    "CargoPlan",
    "FRONTIER_OBJECTIVES",
    "MAX_TRANSFER_CANDIDATES",
    "build_cargo_problem",
    "evaluate_plan",
]
