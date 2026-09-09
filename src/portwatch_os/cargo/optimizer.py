"""Assigning transshipment cargo to onward vessels and yard zones.

The problem is a constrained assignment: shipments on one side, outbound vessel
slots on the other, with capacity, timing, destination and cargo-class rules
between them. It is solved here by a greedy pass over a value-ranked list, and
the choice of greedy over an exact solver is deliberate rather than lazy:

*   The binding constraints are integral and hard (a plug is a plug), so the
    LP relaxation an exact solver would lean on is not a useful guide.
*   The instance a port controller actually faces is small -- a few dozen
    shipments against a handful of sailings in the next 48 hours -- and greedy
    on a good ranking is within a few percent of optimal on assignment problems
    of that shape.
*   A planner has to be able to see *why* a box went where it did. "Highest
    value per TEU of scarce capacity, subject to these checks" is auditable.

:func:`optimise` reports the gap it knows about: the value it left on the table
because capacity ran out, and every shipment it could not place with the reason.
No result is presented as optimal, because it is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.portwatch_os.cargo.model import (
    CARGO_DISCLAIMER,
    Connection,
    Shipment,
    StorageZone,
    TransferWindow,
    VesselCapacity,
    evaluate_connection,
    total_handling_hours,
)

#: Value weights. What the assignment is actually trying to buy, in comparable
#: units so the ranking means something.
VALUE_WEIGHTS: Dict[str, float] = {
    #: Per TEU actually moved onward. Moving the box is the business, and
    #: without this term the arithmetic says the cheapest plan is to move
    #: nothing -- which is true only if handling is free and storage is
    #: infinite.
    "teu_moved": 0.18,
    #: Per hour of onward transit time saved against the next alternative.
    "hours_saved": 1.0,
    #: Per hour of yard dwell avoided. Dwell is a real cost: it occupies a slot
    #: another box needs, which is why an overfull yard is a scheduling problem
    #: and not just a storage one.
    "dwell_avoided": 0.35,
    #: Flat bonus for meeting a committed departure. Missing a commitment costs
    #: far more than the transit time involved.
    "commitment_met": 30.0,
    #: Penalty per hour of handling. A transfer that needs six hours of crane
    #: time competes with vessel work for the same gangs, so it is charged --
    #: but at a rate that lets a worthwhile transfer survive it.
    "handling_hours": -1.2,
    #: Bonus for a direct ship-to-ship move, which skips the yard entirely.
    "direct_transfer": 12.0,
}


@dataclass
class Assignment:
    """One shipment placed on one vessel, with the value it earned."""

    shipment_id: str
    vessel_id: str
    vessel_name: str
    destination_port: str
    zone_id: Optional[str]
    teu: float
    value: float
    hours_saved: Optional[float]
    handling_hours: float
    ready_hour: float
    cutoff_hour: Optional[float]
    slack_hours: Optional[float]
    direct_transfer: bool
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shipmentId": self.shipment_id,
            "vesselId": self.vessel_id,
            "vesselName": self.vessel_name,
            "destinationPort": self.destination_port,
            "zoneId": self.zone_id,
            "teu": self.teu,
            "value": round(self.value, 2),
            "hoursSaved": None if self.hours_saved is None else round(self.hours_saved, 2),
            "handlingHours": round(self.handling_hours, 2),
            "readyHour": round(self.ready_hour, 2),
            "cutoffHour": None if self.cutoff_hour is None else round(self.cutoff_hour, 2),
            "slackHours": None if self.slack_hours is None else round(self.slack_hours, 2),
            "directTransfer": self.direct_transfer,
            "rationale": self.rationale,
        }


@dataclass
class Unplaced:
    """A shipment that could not be assigned, and every reason why."""

    shipment_id: str
    teu: float
    destination_port: str
    cargo_class: str
    reasons: List[str]
    #: The best candidate considered, so a planner can see how close it was.
    nearest_vessel: Optional[str] = None
    shortfall_hours: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shipmentId": self.shipment_id,
            "teu": self.teu,
            "destinationPort": self.destination_port,
            "cargoClass": self.cargo_class,
            "reasons": self.reasons,
            "nearestVessel": self.nearest_vessel,
            "shortfallHours": (
                None if self.shortfall_hours is None else round(self.shortfall_hours, 2)
            ),
        }


@dataclass
class CargoPlan:
    """The result of one optimisation pass."""

    port_code: str
    assignments: List[Assignment] = field(default_factory=list)
    unplaced: List[Unplaced] = field(default_factory=list)
    #: Remaining capacity per vessel after the plan.
    residual_capacity: Dict[str, float] = field(default_factory=dict)
    total_value: float = 0.0
    total_teu: float = 0.0
    #: Value that could not be captured because capacity ran out. The optimality
    #: gap this method can actually measure.
    foregone_value: float = 0.0
    notes: List[str] = field(default_factory=list)
    disclaimer: str = CARGO_DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portCode": self.port_code,
            "assignments": [a.to_dict() for a in self.assignments],
            "unplaced": [u.to_dict() for u in self.unplaced],
            "residualCapacity": {k: round(v, 1) for k, v in self.residual_capacity.items()},
            "totalValue": round(self.total_value, 2),
            "totalTeu": round(self.total_teu, 1),
            "foregoneValue": round(self.foregone_value, 2),
            "placedCount": len(self.assignments),
            "unplacedCount": len(self.unplaced),
            "notes": self.notes,
            "disclaimer": self.disclaimer,
            "method": (
                "Greedy assignment over value per TEU of scarce vessel capacity, with "
                "capacity, connection-window, destination and cargo-class feasibility "
                "checked on every candidate. Not proven optimal; the value left "
                "unplaced is reported as the measurable gap."
            ),
        }


def connection_value(
    shipment: Shipment,
    vessel: VesselCapacity,
    connection: Connection,
    *,
    alternative_departure_hour: Optional[float],
) -> Tuple[float, str]:
    """What this transfer is worth, and the sentence explaining it."""
    parts: List[str] = []
    value = VALUE_WEIGHTS["teu_moved"] * shipment.teu
    parts = [f"{shipment.teu:.0f} TEU moved onward (+{value:.1f})"]

    if connection.hours_saved is not None and connection.hours_saved > 0:
        contribution = VALUE_WEIGHTS["hours_saved"] * connection.hours_saved
        value += contribution
        parts.append(
            f"{connection.hours_saved:.1f} h earlier than the next sailing "
            f"(+{contribution:.1f})"
        )

    if vessel.departure_hour is not None and shipment.available_hour is not None:
        dwell = max(0.0, vessel.departure_hour - shipment.available_hour)
        # Dwell avoided is measured against the alternative, not against zero:
        # every box waits for its ship, and only the difference is a saving.
        if alternative_departure_hour is not None:
            avoided = max(0.0, (alternative_departure_hour - shipment.available_hour) - dwell)
            if avoided > 0:
                contribution = VALUE_WEIGHTS["dwell_avoided"] * avoided
                value += contribution
                parts.append(f"{avoided:.1f} h less yard dwell (+{contribution:.1f})")

    if (
        shipment.latest_departure_hour is not None
        and vessel.departure_hour is not None
        and vessel.departure_hour <= shipment.latest_departure_hour
    ):
        value += VALUE_WEIGHTS["commitment_met"]
        parts.append(
            f"meets the committed departure at hour "
            f"{shipment.latest_departure_hour:.0f} (+{VALUE_WEIGHTS['commitment_met']:.0f})"
        )

    handling_cost = VALUE_WEIGHTS["handling_hours"] * connection.window.handling_hours
    value += handling_cost
    parts.append(
        f"{connection.window.handling_hours:.1f} h of handling ({handling_cost:.1f})"
    )

    if connection.direct_transfer:
        value += VALUE_WEIGHTS["direct_transfer"]
        parts.append(
            f"direct ship-to-ship, no yard move (+{VALUE_WEIGHTS['direct_transfer']:.0f})"
        )

    return value, "; ".join(parts)


def _best_zone(
    shipment: Shipment,
    zones: Sequence[StorageZone],
) -> Optional[StorageZone]:
    """The nearest zone that can actually take this shipment."""
    usable = [
        zone for zone in zones
        if zone.free_teu >= shipment.teu
        and (not shipment.spec.needs_power or zone.reefer_plugs_free >= int(shipment.teu))
        and (shipment.cargo_class != "hazardous" or zone.accepts_hazardous)
        and (shipment.cargo_class != "oog" or zone.accepts_oog)
    ]
    if not usable:
        return None
    # Nearest to the quay wins: transfer time is connection window, and window is
    # the constraint that actually breaks these plans.
    return min(usable, key=lambda z: z.quay_transfer_minutes_per_teu)


def optimise(
    port_code: str,
    shipments: Sequence[Shipment],
    vessels: Sequence[VesselCapacity],
    zones: Sequence[StorageZone],
    *,
    now_hour: float = 0.0,
    gangs: int = 1,
) -> CargoPlan:
    """Assign transshipment cargo to onward sailings.

    Greedy over value per TEU: a shipment that buys a lot per unit of scarce
    vessel slot is placed first, which is the standard ranking for a knapsack of
    this shape. Capacity is decremented as the plan is built, so later shipments
    see the world the earlier ones left behind.
    """
    plan = CargoPlan(port_code=port_code)
    # Work on copies of the capacity: the plan must not mutate the live state
    # its inputs came from.
    remaining = {
        v.vessel_id: {
            "teu": v.available_teu,
            "plugs": v.available_reefer_plugs,
            "deadweight": v.available_deadweight_t,
        }
        for v in vessels
    }
    zone_free = {z.zone_id: z.free_teu for z in zones}
    by_id = {v.vessel_id: v for v in vessels}

    #: Candidate list: every (shipment, vessel) pair that passes every check.
    candidates: List[Tuple[float, float, Shipment, VesselCapacity, Connection, Optional[StorageZone], str]] = []
    failures: Dict[str, List[str]] = {}
    nearest: Dict[str, Tuple[str, Optional[float]]] = {}

    for shipment in shipments:
        # The alternative is the next sailing to the same destination after the
        # best one. Without it "hours saved" has no meaning.
        serving = sorted(
            (v for v in vessels if v.serves(shipment.destination_port)),
            key=lambda v: v.departure_hour if v.departure_hour is not None else 1e9,
        )
        alternative = (
            serving[1].departure_hour if len(serving) > 1 else None
        )

        placed_any = False
        for vessel in serving or vessels:
            zone = _best_zone(shipment, zones)
            connection = evaluate_connection(
                shipment, vessel, zone=zone, now_hour=now_hour, gangs=gangs,
                alternative_departure_hour=alternative,
            )
            if not connection.feasible:
                failures.setdefault(shipment.shipment_id, []).extend(connection.reasons)
                slack = connection.window.slack_hours
                if slack is not None:
                    current = nearest.get(shipment.shipment_id)
                    if current is None or (current[1] is not None and slack > current[1]):
                        nearest[shipment.shipment_id] = (vessel.name, slack)
                continue
            value, rationale = connection_value(
                shipment, vessel, connection, alternative_departure_hour=alternative
            )
            density = value / max(1.0, shipment.teu)
            candidates.append(
                (density, value, shipment, vessel, connection, zone, rationale)
            )
            placed_any = True

        if not placed_any and shipment.shipment_id not in failures:
            failures[shipment.shipment_id] = [
                f"no vessel in scope calls at {shipment.destination_port}"
            ]

    candidates.sort(key=lambda c: (-c[0], -c[1], c[2].shipment_id))

    assigned: set[str] = set()
    for density, value, shipment, vessel, connection, zone, rationale in candidates:
        if shipment.shipment_id in assigned:
            continue
        budget = remaining[vessel.vessel_id]
        if budget["teu"] < shipment.teu:
            plan.foregone_value += max(0.0, value)
            failures.setdefault(shipment.shipment_id, []).append(
                f"{vessel.name} filled up before this shipment was reached"
            )
            continue
        if shipment.spec.needs_power and budget["plugs"] < int(shipment.teu):
            plan.foregone_value += max(0.0, value)
            failures.setdefault(shipment.shipment_id, []).append(
                f"{vessel.name} ran out of reefer plugs"
            )
            continue
        if zone is not None and zone_free.get(zone.zone_id, 0.0) < shipment.teu:
            plan.foregone_value += max(0.0, value)
            failures.setdefault(shipment.shipment_id, []).append(
                f"yard block {zone.name} filled up before this shipment was reached"
            )
            continue

        budget["teu"] -= shipment.teu
        if shipment.spec.needs_power:
            budget["plugs"] -= int(shipment.teu)
        if budget["deadweight"] is not None:
            budget["deadweight"] -= shipment.weight_t
        if zone is not None:
            zone_free[zone.zone_id] = zone_free.get(zone.zone_id, 0.0) - shipment.teu

        assigned.add(shipment.shipment_id)
        plan.assignments.append(
            Assignment(
                shipment_id=shipment.shipment_id,
                vessel_id=vessel.vessel_id,
                vessel_name=vessel.name,
                destination_port=shipment.destination_port,
                zone_id=zone.zone_id if zone else None,
                teu=shipment.teu,
                value=value,
                hours_saved=connection.hours_saved,
                handling_hours=connection.window.handling_hours,
                ready_hour=connection.window.ready_hour,
                cutoff_hour=connection.window.cutoff_hour,
                slack_hours=connection.window.slack_hours,
                direct_transfer=connection.direct_transfer,
                rationale=rationale,
            )
        )
        plan.total_value += value
        plan.total_teu += shipment.teu

    for shipment in shipments:
        if shipment.shipment_id in assigned:
            continue
        reasons = _dedupe(failures.get(shipment.shipment_id, ["no feasible connection found"]))
        near = nearest.get(shipment.shipment_id)
        plan.unplaced.append(
            Unplaced(
                shipment_id=shipment.shipment_id,
                teu=shipment.teu,
                destination_port=shipment.destination_port,
                cargo_class=shipment.cargo_class,
                reasons=reasons[:5],
                nearest_vessel=near[0] if near else None,
                shortfall_hours=(-near[1] if near and near[1] is not None and near[1] < 0 else None),
            )
        )

    plan.residual_capacity = {
        by_id[vid].name: budget["teu"] for vid, budget in remaining.items()
    }
    plan.assignments.sort(key=lambda a: -a.value)
    plan.unplaced.sort(key=lambda u: -u.teu)

    if not vessels:
        plan.notes.append("No outbound vessel capacity was in scope, so nothing could be placed.")
    if plan.foregone_value > 0:
        plan.notes.append(
            f"{plan.foregone_value:.0f} points of value were foregone because capacity "
            "ran out before those shipments were reached. That is the measurable gap "
            "between this greedy plan and a better one."
        )
    return plan


def _dedupe(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def opportunities(
    shipments: Sequence[Shipment],
    vessels: Sequence[VesselCapacity],
    zones: Sequence[StorageZone],
    *,
    now_hour: float = 0.0,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Feasible transfers ranked by value, without committing capacity.

    This is what the company screen shows: "these connections exist right now",
    before anyone decides which to take. The plan in :func:`optimise` is what a
    port controller commits to.
    """
    rows: List[Dict[str, Any]] = []
    for shipment in shipments:
        serving = sorted(
            (v for v in vessels if v.serves(shipment.destination_port)),
            key=lambda v: v.departure_hour if v.departure_hour is not None else 1e9,
        )
        alternative = serving[1].departure_hour if len(serving) > 1 else None
        for vessel in serving:
            zone = _best_zone(shipment, zones)
            connection = evaluate_connection(
                shipment, vessel, zone=zone, now_hour=now_hour,
                alternative_departure_hour=alternative,
            )
            if not connection.feasible:
                continue
            value, rationale = connection_value(
                shipment, vessel, connection, alternative_departure_hour=alternative
            )
            rows.append(
                {
                    **connection.to_dict(),
                    "value": round(value, 2),
                    "rationale": rationale,
                    "teu": shipment.teu,
                    "cargoClass": shipment.cargo_class,
                    "vesselName": vessel.name,
                }
            )
    rows.sort(key=lambda r: -r["value"])
    return rows[:limit]


__all__ = [
    "VALUE_WEIGHTS",
    "Assignment",
    "CargoPlan",
    "Unplaced",
    "connection_value",
    "opportunities",
    "optimise",
]
