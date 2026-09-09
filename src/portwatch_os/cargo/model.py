"""Cargo, capacity and the transshipment connection.

The question this exists to answer, from either side of the quay:

    Shipping company: "can the boxes arriving on Vessel A make Vessel B, which
                       is already alongside and sails for Singapore tonight?"
    Port authority:   "where do I put transshipment cargo so those connections
                       are actually makeable?"

**The data is schematic and labelled.** No commercial cargo feed exists for this
deployment, so :func:`demo_manifest` generates a manifest from the port's own
observed throughput. Every surface that shows it carries
:data:`CARGO_DISCLAIMER`. What is *not* invented is the feasibility logic: the
capacity arithmetic, the handling times and the connection window are real
constraints, and a transfer that fails one of them is rejected with the reason.
That is the part a real feed would plug straight into.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

CARGO_DISCLAIMER = (
    "Demo cargo flow. No commercial manifest feed is connected to this "
    "deployment, so shipments are generated from the port's observed container "
    "throughput and its published transshipment share. Volumes, destinations and "
    "customers are illustrative and do not represent any real consignment. The "
    "feasibility rules -- capacity, handling time, connection window and "
    "destination compatibility -- are real and are what a live manifest feed "
    "would drive."
)

#: Cargo classes, and what each needs from the terminal.
@dataclass(frozen=True)
class CargoClass:
    key: str
    label: str
    #: Handling moves per TEU. Reefers and hazardous need extra handling.
    handling_factor: float
    #: Whether the class needs a powered slot.
    needs_power: bool
    #: Whether the class has segregation rules that limit where it can sit.
    segregated: bool
    description: str


CARGO_CLASSES: Dict[str, CargoClass] = {
    c.key: c
    for c in [
        CargoClass("dry", "Dry container", 1.0, False, False,
                   "Standard dry box. No special handling."),
        CargoClass("reefer", "Reefer", 1.25, True, False,
                   "Temperature-controlled. Needs a plug and a monitored slot."),
        CargoClass("hazardous", "Hazardous (IMDG)", 1.6, False, True,
                   "Dangerous goods. Segregation rules restrict placement."),
        CargoClass("oog", "Out of gauge", 1.8, False, True,
                   "Over-height or over-width. Cannot be stacked normally."),
        CargoClass("empty", "Empty", 0.7, False, False,
                   "Repositioning empties. Cheap to handle, still takes a slot."),
    ]
}


@dataclass
class Shipment:
    """One consignment moving through the port as a unit."""

    shipment_id: str
    #: TEU. The unit everything downstream counts in.
    teu: float
    cargo_class: str
    #: Where it is ultimately going. Drives connection compatibility.
    destination_port: str
    #: The vessel it arrived on, where it arrived by sea.
    inbound_vessel_id: Optional[str] = None
    #: The vessel it is currently booked onto, if any.
    booked_vessel_id: Optional[str] = None
    #: Simulation hour it became available in the yard.
    available_hour: Optional[float] = None
    #: Latest hour it must leave to meet its onward commitment.
    latest_departure_hour: Optional[float] = None
    #: Where it is now.
    yard_block_id: Optional[str] = None
    weight_t: float = 0.0
    #: Customer reference. Illustrative; see CARGO_DISCLAIMER.
    consignee: str = "Demo consignee"
    #: How long it has been in the yard, hours.
    dwell_hours: float = 0.0

    @property
    def spec(self) -> CargoClass:
        return CARGO_CLASSES.get(self.cargo_class, CARGO_CLASSES["dry"])

    @property
    def handling_moves(self) -> float:
        """Crane moves this shipment costs, both ends of a transfer."""
        return self.teu * self.spec.handling_factor

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "cargoLabel": self.spec.label,
            "handlingMoves": round(self.handling_moves, 2),
        }


@dataclass
class VesselCapacity:
    """What a vessel can still take, and where it is going.

    Capacity is not one number. A ship with 400 TEU of slots and no reefer plugs
    cannot take a reefer consignment, and a transfer proposal that ignores that
    is a proposal no terminal would execute.
    """

    vessel_id: str
    name: str
    #: Free slots, TEU.
    available_teu: float
    #: Free reefer plugs.
    available_reefer_plugs: int = 0
    #: Whether the vessel is certified for dangerous goods.
    accepts_hazardous: bool = False
    accepts_oog: bool = False
    #: Remaining deadweight, tonnes.
    available_deadweight_t: Optional[float] = None
    #: Ports on this vessel's onward rotation, in order.
    onward_ports: List[str] = field(default_factory=list)
    #: Hour it sails. The hard end of every connection window.
    departure_hour: Optional[float] = None
    #: Hour loading must be complete: cut-off, not sailing.
    load_cutoff_hour: Optional[float] = None
    berth_id: Optional[str] = None
    operator: Optional[str] = None

    def serves(self, destination: str) -> bool:
        """Whether this vessel reaches a destination directly on this rotation."""
        return destination.upper() in {p.upper() for p in self.onward_ports}

    def cutoff(self) -> Optional[float]:
        """Effective loading cut-off. Two hours before sailing where unstated."""
        if self.load_cutoff_hour is not None:
            return self.load_cutoff_hour
        if self.departure_hour is not None:
            return self.departure_hour - 2.0
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "loadCutoff": self.cutoff()}


@dataclass
class StorageZone:
    """A yard area a shipment can sit in between vessels."""

    zone_id: str
    name: str
    #: Free TEU right now.
    free_teu: float
    capacity_teu: float
    reefer_plugs_free: int = 0
    accepts_hazardous: bool = False
    accepts_oog: bool = True
    #: Minutes to move one TEU between this zone and the quay. Distance made
    #: operational: a far zone is not merely inconvenient, it costs connection
    #: window.
    quay_transfer_minutes_per_teu: float = 1.2
    block_id: Optional[str] = None

    @property
    def utilisation(self) -> float:
        return (
            1.0 - (self.free_teu / self.capacity_teu) if self.capacity_teu > 0 else 1.0
        )

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "utilisation": round(self.utilisation, 4)}


# --------------------------------------------------------------------------
# handling times
# --------------------------------------------------------------------------

#: Discharge rate from a vessel into the yard, TEU per hour, one gang.
DISCHARGE_TEU_PER_HOUR = 24.0

#: Load rate from the yard onto a vessel, TEU per hour, one gang.
LOAD_TEU_PER_HOUR = 22.0

#: Fixed administrative time on a transfer: documentation, customs hold check,
#: stowage plan amendment. A transshipment is not a crane operation alone.
TRANSFER_OVERHEAD_HOURS = 1.5


def discharge_hours(shipment: Shipment, gangs: int = 1) -> float:
    return float(shipment.handling_moves / max(1, gangs) / DISCHARGE_TEU_PER_HOUR)


def load_hours(shipment: Shipment, gangs: int = 1) -> float:
    return float(shipment.handling_moves / max(1, gangs) / LOAD_TEU_PER_HOUR)


def yard_move_hours(shipment: Shipment, zone: StorageZone) -> float:
    return float(shipment.teu * zone.quay_transfer_minutes_per_teu / 60.0)


def total_handling_hours(
    shipment: Shipment,
    zone: Optional[StorageZone],
    *,
    gangs: int = 1,
) -> float:
    """Total time from touching the inbound hull to being loadable onto the next.

    Discharge, two yard moves (in and out), and the fixed overhead. A direct
    ship-to-ship transfer skips the yard moves, which is why the zone is
    optional and why a direct transfer is materially faster when both hulls are
    alongside at once.
    """
    hours = discharge_hours(shipment, gangs) + TRANSFER_OVERHEAD_HOURS
    if zone is not None:
        hours += 2 * yard_move_hours(shipment, zone)
    return hours + load_hours(shipment, gangs)


# --------------------------------------------------------------------------
# feasibility
# --------------------------------------------------------------------------


@dataclass
class TransferWindow:
    """When a transfer could physically happen, and whether it fits."""

    #: Earliest the shipment can be ready to load.
    ready_hour: float
    #: Latest the outbound vessel will take it.
    cutoff_hour: Optional[float]
    handling_hours: float

    @property
    def slack_hours(self) -> Optional[float]:
        if self.cutoff_hour is None:
            return None
        return self.cutoff_hour - self.ready_hour

    @property
    def feasible(self) -> bool:
        slack = self.slack_hours
        return slack is not None and slack >= 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "readyHour": round(self.ready_hour, 2),
            "cutoffHour": None if self.cutoff_hour is None else round(self.cutoff_hour, 2),
            "handlingHours": round(self.handling_hours, 2),
            "slackHours": None if self.slack_hours is None else round(self.slack_hours, 2),
            "feasible": self.feasible,
        }


@dataclass
class Connection:
    """A proposed shipment-to-vessel transfer, with every check recorded.

    A rejected connection carries its reasons. That is the whole value of the
    object: a planner needs to know that the box missed the ship by forty minutes
    of yard move, not merely that the answer was no.
    """

    shipment_id: str
    outbound_vessel_id: str
    destination_port: str
    zone_id: Optional[str]
    window: TransferWindow
    feasible: bool
    reasons: List[str] = field(default_factory=list)
    #: Hours saved against the shipment's next alternative sailing, where one
    #: exists. ``None`` when there is no alternative to compare against.
    hours_saved: Optional[float] = None
    #: Whether both hulls are alongside simultaneously, allowing a direct move.
    direct_transfer: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shipmentId": self.shipment_id,
            "outboundVesselId": self.outbound_vessel_id,
            "destinationPort": self.destination_port,
            "zoneId": self.zone_id,
            "window": self.window.to_dict(),
            "feasible": self.feasible,
            "reasons": self.reasons,
            "hoursSaved": None if self.hours_saved is None else round(self.hours_saved, 2),
            "directTransfer": self.direct_transfer,
        }


def check_compatibility(
    shipment: Shipment,
    vessel: VesselCapacity,
) -> List[str]:
    """Every reason this shipment cannot go on this vessel. Empty means it can."""
    problems: List[str] = []
    spec = shipment.spec

    if not vessel.serves(shipment.destination_port):
        problems.append(
            f"{vessel.name} does not call at {shipment.destination_port} on this rotation "
            f"(rotation: {', '.join(vessel.onward_ports) or 'none declared'})"
        )
    if vessel.available_teu < shipment.teu:
        problems.append(
            f"{vessel.name} has {vessel.available_teu:.0f} TEU free; the shipment is "
            f"{shipment.teu:.0f} TEU"
        )
    if spec.needs_power and vessel.available_reefer_plugs < int(shipment.teu):
        problems.append(
            f"{vessel.name} has {vessel.available_reefer_plugs} reefer plugs free; "
            f"{int(shipment.teu)} are needed"
        )
    if shipment.cargo_class == "hazardous" and not vessel.accepts_hazardous:
        problems.append(f"{vessel.name} is not certified for IMDG cargo")
    if shipment.cargo_class == "oog" and not vessel.accepts_oog:
        problems.append(f"{vessel.name} cannot carry out-of-gauge cargo")
    if (
        vessel.available_deadweight_t is not None
        and shipment.weight_t > vessel.available_deadweight_t
    ):
        problems.append(
            f"{vessel.name} has {vessel.available_deadweight_t:.0f} t deadweight free; "
            f"the shipment is {shipment.weight_t:.0f} t"
        )
    return problems


def check_zone(shipment: Shipment, zone: StorageZone) -> List[str]:
    problems: List[str] = []
    if zone.free_teu < shipment.teu:
        problems.append(
            f"{zone.name} has {zone.free_teu:.0f} TEU free; the shipment is "
            f"{shipment.teu:.0f} TEU"
        )
    if shipment.spec.needs_power and zone.reefer_plugs_free < int(shipment.teu):
        problems.append(
            f"{zone.name} has {zone.reefer_plugs_free} reefer plugs free"
        )
    if shipment.cargo_class == "hazardous" and not zone.accepts_hazardous:
        problems.append(f"{zone.name} does not accept IMDG cargo")
    if shipment.cargo_class == "oog" and not zone.accepts_oog:
        problems.append(f"{zone.name} cannot hold out-of-gauge units")
    return problems


def evaluate_connection(
    shipment: Shipment,
    vessel: VesselCapacity,
    *,
    zone: Optional[StorageZone] = None,
    now_hour: float = 0.0,
    inbound_discharge_hour: Optional[float] = None,
    gangs: int = 1,
    alternative_departure_hour: Optional[float] = None,
) -> Connection:
    """Is this transfer possible, and what does it buy?

    Every check runs even after the first failure, because a planner asking
    "why not?" needs all the reasons at once rather than one per attempt.
    """
    reasons = check_compatibility(shipment, vessel)
    if zone is not None:
        reasons.extend(check_zone(shipment, zone))

    available = (
        inbound_discharge_hour
        if inbound_discharge_hour is not None
        else (shipment.available_hour if shipment.available_hour is not None else now_hour)
    )
    direct = (
        zone is None
        and vessel.berth_id is not None
        and shipment.inbound_vessel_id is not None
    )
    handling = total_handling_hours(shipment, zone, gangs=gangs)
    ready = available + handling
    cutoff = vessel.cutoff()

    window = TransferWindow(ready_hour=ready, cutoff_hour=cutoff, handling_hours=handling)
    if cutoff is None:
        reasons.append(
            f"{vessel.name} has declared no sailing time, so the connection window "
            "cannot be checked"
        )
    elif not window.feasible:
        reasons.append(
            f"the shipment is ready at hour {ready:.1f} but {vessel.name} closes "
            f"loading at hour {cutoff:.1f}: short by {ready - cutoff:.1f} h"
        )

    if (
        shipment.latest_departure_hour is not None
        and vessel.departure_hour is not None
        and vessel.departure_hour > shipment.latest_departure_hour
    ):
        reasons.append(
            f"{vessel.name} sails at hour {vessel.departure_hour:.1f}, after the "
            f"shipment's commitment at hour {shipment.latest_departure_hour:.1f}"
        )

    hours_saved = None
    if alternative_departure_hour is not None and vessel.departure_hour is not None:
        hours_saved = alternative_departure_hour - vessel.departure_hour

    return Connection(
        shipment_id=shipment.shipment_id,
        outbound_vessel_id=vessel.vessel_id,
        destination_port=shipment.destination_port,
        zone_id=zone.zone_id if zone else None,
        window=window,
        feasible=not reasons,
        reasons=reasons,
        hours_saved=hours_saved,
        direct_transfer=direct,
    )


# --------------------------------------------------------------------------
# the demo manifest
# --------------------------------------------------------------------------

#: Onward destinations used by the demo manifest. Real ports, illustrative flows.
DEMO_DESTINATIONS: Tuple[Tuple[str, str, float], ...] = (
    ("SGSIN", "Singapore", 0.24),
    ("AEJEA", "Jebel Ali", 0.18),
    ("LKCMB", "Colombo", 0.16),
    ("MYPKG", "Port Klang", 0.10),
    ("NLRTM", "Rotterdam", 0.10),
    ("CNSHA", "Shanghai", 0.09),
    ("BDCGP", "Chittagong", 0.07),
    ("OMSLL", "Salalah", 0.06),
)

_CLASS_MIX: Tuple[Tuple[str, float], ...] = (
    ("dry", 0.68), ("empty", 0.14), ("reefer", 0.12),
    ("hazardous", 0.04), ("oog", 0.02),
)


def _pick(rng: random.Random, options: Sequence[Tuple[Any, ...]], weight_index: int) -> Any:
    total = sum(option[weight_index] for option in options)
    draw = rng.random() * total
    running = 0.0
    for option in options:
        running += option[weight_index]
        if draw <= running:
            return option
    return options[-1]


def demo_manifest(
    port_code: str,
    *,
    seed: int = 20260909,
    shipments: int = 60,
    transshipment_share: float = 0.35,
    horizon_hours: float = 72.0,
) -> List[Shipment]:
    """Generate a schematic manifest for a port. See :data:`CARGO_DISCLAIMER`.

    Deterministic given the seed, so the cargo screen shows the same thing on
    every run and a screenshot is reviewable.
    """
    rng = random.Random(
        seed ^ int(hashlib.sha1(port_code.encode()).hexdigest()[:8], 16)
    )
    out: List[Shipment] = []
    for index in range(shipments):
        destination = _pick(rng, DEMO_DESTINATIONS, 2)
        cargo_class = _pick(rng, _CLASS_MIX, 1)[0]
        teu = float(rng.choice([20, 40, 60, 80, 120, 160, 240]))
        available = rng.uniform(0.0, horizon_hours * 0.6)
        out.append(
            Shipment(
                shipment_id=f"{port_code}-SHP-{index + 1:03d}",
                teu=teu,
                cargo_class=cargo_class,
                destination_port=destination[0],
                available_hour=available,
                latest_departure_hour=(
                    available + rng.uniform(24.0, 120.0)
                    if rng.random() < 0.7 else None
                ),
                weight_t=teu * rng.uniform(8.0, 14.0),
                dwell_hours=rng.uniform(2.0, 96.0),
                consignee=f"Demo consignee {rng.randint(1, 24):02d}",
                inbound_vessel_id=(
                    f"{port_code}-INB-{rng.randint(1, 8)}"
                    if rng.random() < transshipment_share else None
                ),
            )
        )
    return out


def zones_from_state(state: Any) -> List[StorageZone]:
    """Storage zones derived from a :class:`PortState`'s yard blocks.

    Reads the twin rather than keeping a second yard model, so the cargo plan and
    the 3D overlay cannot disagree about how full a block is.
    """
    zones: List[StorageZone] = []
    for index, block in enumerate(getattr(state, "yard_blocks", [])):
        zones.append(
            StorageZone(
                zone_id=block.block_id,
                name=block.name,
                free_teu=block.free_teu(),
                capacity_teu=block.capacity_teu,
                reefer_plugs_free=block.reefer_plugs,
                accepts_hazardous=(index % 4 == 0),
                accepts_oog=True,
                # Blocks further from the quay cost more to move to and from.
                quay_transfer_minutes_per_teu=0.9 + (block.y / 1000.0),
                block_id=block.block_id,
            )
        )
    return zones


__all__ = [
    "CARGO_CLASSES",
    "CARGO_DISCLAIMER",
    "DEMO_DESTINATIONS",
    "DISCHARGE_TEU_PER_HOUR",
    "LOAD_TEU_PER_HOUR",
    "TRANSFER_OVERHEAD_HOURS",
    "CargoClass",
    "Connection",
    "Shipment",
    "StorageZone",
    "TransferWindow",
    "VesselCapacity",
    "check_compatibility",
    "check_zone",
    "demo_manifest",
    "discharge_hours",
    "evaluate_connection",
    "load_hours",
    "total_handling_hours",
    "yard_move_hours",
    "zones_from_state",
]
