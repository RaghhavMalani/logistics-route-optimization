"""The logical port state.

This is the single object that the 3D renderer, the discrete-event simulator,
the optimisers and the RL environment all consume. That is the whole point: if
the twin the operator looks at and the twin the policy trains in were different
objects, every result from one would be unfalsifiable in the other.

Nothing here is graphics. There are no meshes, materials or cameras -- only
berths with lengths and draughts, yard blocks with slot counts, cranes with
move rates and a queue of vessels. The renderer projects this; it does not own
any of it.

**Geometry honesty.** The berth and yard positions in :func:`schematic_layout`
are a schematic derived from published berth counts and the port's coastline
orientation. They are *not* a surveyed port plan, no dimension should be read
off them, and every surface that draws them says so. What *is* real is the
count, the capacity and the operating rates -- which is what the optimiser and
the simulator actually use. The layout exists so a human can point at the thing
the numbers describe.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.utils import port_registry

#: What the geometry is. Rendered as a standing banner on every 3D surface.
GEOMETRY_SCHEMATIC = "SCHEMATIC"
GEOMETRY_SURVEYED = "SURVEYED"

SCHEMATIC_DISCLAIMER = (
    "Schematic digital twin. Berth, yard and shed positions are generated from "
    "published berth counts and coastline orientation, not from a surveyed port "
    "plan. Dimensions and positions are not navigationally or operationally "
    "authoritative. Counts, capacities and rates are modelled from the port "
    "registry and the observed panel."
)


# --------------------------------------------------------------------------
# facility elements
# --------------------------------------------------------------------------


@dataclass
class Berth:
    """One berth. Capacity attributes are real constraints, position is schematic."""

    berth_id: str
    name: str
    #: Metres. Governs which vessels can be assigned here.
    length_m: float
    #: Metres. Governs which vessels can be assigned here.
    depth_m: float
    #: Cranes physically able to serve this berth.
    crane_ids: List[str] = field(default_factory=list)
    #: Cargo types this berth can handle.
    handles: List[str] = field(default_factory=lambda: ["container"])
    #: Schematic position in the twin's local metre grid, x along the quay.
    x: float = 0.0
    y: float = 0.0
    heading_deg: float = 0.0

    #: Dynamic: the vessel currently alongside.
    occupied_by: Optional[str] = None
    #: Simulation hour the current occupancy frees up.
    free_at_hour: Optional[float] = None
    #: Cumulative occupied hours this run, for utilisation.
    occupied_hours: float = 0.0

    def can_accept(self, loa_m: float, draught_m: float, cargo: str = "container") -> bool:
        """Hard physical feasibility. Never relaxed by any optimiser or policy."""
        return (
            loa_m <= self.length_m
            and draught_m <= self.depth_m
            and (cargo in self.handles or "general" in self.handles)
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Crane:
    """A quay crane. ``moves_per_hour`` is what turns a call size into hours."""

    crane_id: str
    name: str
    moves_per_hour: float
    #: Berths this crane can reach, by rail position.
    serves: List[str] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    assigned_berth: Optional[str] = None
    #: Cumulative working hours this run, for the workload overlay.
    working_hours: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class YardBlock:
    """A container yard block. Slots are TEU ground slots, not stacked TEU."""

    block_id: str
    name: str
    slots: int
    #: Maximum stack height, so capacity is slots × tiers.
    tiers: int = 4
    #: What may be stored here.
    accepts: List[str] = field(default_factory=lambda: ["import", "export", "transshipment"])
    reefer_plugs: int = 0
    x: float = 0.0
    y: float = 0.0
    width_m: float = 120.0
    depth_m: float = 60.0

    #: Dynamic occupancy in TEU.
    occupied_teu: float = 0.0
    #: Mean dwell of what is currently in the block, hours.
    mean_dwell_hours: float = 0.0

    @property
    def capacity_teu(self) -> float:
        return float(self.slots * self.tiers)

    @property
    def utilisation(self) -> float:
        capacity = self.capacity_teu
        return float(self.occupied_teu / capacity) if capacity > 0 else 0.0

    def free_teu(self) -> float:
        return max(0.0, self.capacity_teu - self.occupied_teu)

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "capacityTeu": self.capacity_teu,
                "utilisation": round(self.utilisation, 4)}


@dataclass
class Shed:
    """Covered storage. Modelled by area rather than slots."""

    shed_id: str
    name: str
    area_m2: float
    stores: List[str] = field(default_factory=lambda: ["breakbulk"])
    x: float = 0.0
    y: float = 0.0
    width_m: float = 90.0
    depth_m: float = 40.0
    occupied_m2: float = 0.0

    @property
    def utilisation(self) -> float:
        return float(self.occupied_m2 / self.area_m2) if self.area_m2 > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "utilisation": round(self.utilisation, 4)}


@dataclass
class Gate:
    """Landside gate. The hinterland constraint the yard eventually hits."""

    gate_id: str
    name: str
    lanes: int
    trucks_per_hour: float
    x: float = 0.0
    y: float = 0.0
    queue_trucks: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class YardVehicle:
    """An internal mover. Enough of these and the quay stops waiting on them."""

    vehicle_id: str
    kind: str  # "straddle" | "terminal_tractor" | "reach_stacker"
    moves_per_hour: float
    x: float = 0.0
    y: float = 0.0
    assigned_block: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# vessels
# --------------------------------------------------------------------------

WAITING = "waiting"
APPROACHING = "approaching"
ALONGSIDE = "alongside"
DEPARTED = "departed"

VESSEL_STATES = (APPROACHING, WAITING, ALONGSIDE, DEPARTED)


@dataclass
class VesselCall:
    """One vessel's call at this port, from ETA to departure."""

    call_id: str
    vessel_id: str
    name: str
    vessel_class: str
    loa_m: float
    draught_m: float
    #: Scheduled arrival, in simulation hours from the state's epoch.
    eta_hour: float
    #: Container moves this call requires, both directions.
    moves: int
    cargo_type: str = "container"
    #: Import / export / transshipment split of the discharge, summing to 1.
    import_share: float = 0.45
    export_share: float = 0.40
    transship_share: float = 0.15
    #: Contractual or scheduled departure, if any. Missing it costs the operator.
    latest_departure_hour: Optional[float] = None
    priority: float = 0.5

    state: str = APPROACHING
    #: Hour the vessel actually arrived at the anchorage.
    arrived_hour: Optional[float] = None
    berth_id: Optional[str] = None
    berthed_hour: Optional[float] = None
    departed_hour: Optional[float] = None
    assigned_cranes: List[str] = field(default_factory=list)
    #: Hours spent at anchor. The headline number a shipping line cares about.
    wait_hours: float = 0.0
    #: Arrival delay imposed by an accepted advisory, hours.
    imposed_delay_hours: float = 0.0

    @property
    def turnaround_hours(self) -> Optional[float]:
        if self.arrived_hour is None or self.departed_hour is None:
            return None
        return self.departed_hour - self.arrived_hour

    @property
    def effective_eta(self) -> float:
        return self.eta_hour + self.imposed_delay_hours

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "turnaroundHours": self.turnaround_hours,
            "effectiveEta": self.effective_eta,
        }


# --------------------------------------------------------------------------
# the state
# --------------------------------------------------------------------------


@dataclass
class PortState:
    """Everything the twin knows about one port at one instant.

    Deliberately plain data. :meth:`clone` gives the simulator and the RL
    environment an isolated copy so a rollout can never contaminate the state the
    operator is looking at.
    """

    port_code: str
    port_name: str
    #: Simulation hour. 0 is the state's epoch.
    hour: float = 0.0
    #: Wall-clock instant hour 0 corresponds to.
    epoch: Optional[str] = None
    geometry_basis: str = GEOMETRY_SCHEMATIC

    berths: List[Berth] = field(default_factory=list)
    cranes: List[Crane] = field(default_factory=list)
    yard_blocks: List[YardBlock] = field(default_factory=list)
    sheds: List[Shed] = field(default_factory=list)
    gates: List[Gate] = field(default_factory=list)
    vehicles: List[YardVehicle] = field(default_factory=list)
    calls: List[VesselCall] = field(default_factory=list)

    #: Weather impact index at the current hour, 0..1. Drives crane derating.
    weather_impact: float = 0.0
    #: Event-driven arrival pressure from Global Eye, 0..1.
    event_risk: float = 0.0
    #: Water area extent in local metres, for the renderer's harbour plane.
    extent_m: Tuple[float, float] = (2400.0, 1600.0)
    #: Approach bearing, degrees true, from the shipped water mask.
    seaward_bearing: float = 270.0

    notes: List[str] = field(default_factory=list)

    # -- lookups -----------------------------------------------------------
    def berth(self, berth_id: str) -> Optional[Berth]:
        return next((b for b in self.berths if b.berth_id == berth_id), None)

    def crane(self, crane_id: str) -> Optional[Crane]:
        return next((c for c in self.cranes if c.crane_id == crane_id), None)

    def block(self, block_id: str) -> Optional[YardBlock]:
        return next((b for b in self.yard_blocks if b.block_id == block_id), None)

    def call(self, call_id: str) -> Optional[VesselCall]:
        return next((c for c in self.calls if c.call_id == call_id), None)

    # -- derived metrics ---------------------------------------------------
    @property
    def berth_utilisation(self) -> float:
        if not self.berths:
            return 0.0
        return sum(1 for b in self.berths if b.occupied_by) / len(self.berths)

    @property
    def yard_utilisation(self) -> float:
        capacity = sum(b.capacity_teu for b in self.yard_blocks)
        if capacity <= 0:
            return 0.0
        return sum(b.occupied_teu for b in self.yard_blocks) / capacity

    @property
    def queue_length(self) -> int:
        return sum(1 for c in self.calls if c.state == WAITING)

    @property
    def alongside_count(self) -> int:
        return sum(1 for c in self.calls if c.state == ALONGSIDE)

    @property
    def total_crane_capacity(self) -> float:
        """Effective moves per hour across the quay, after weather derating.

        Crane work stops in high wind. The derating below is a straight-line
        reduction against the weather impact index and is labelled as modelled
        wherever it is shown; it is not a measured productivity curve for any
        specific crane.
        """
        derate = max(0.25, 1.0 - self.weather_impact * 1.4)
        return sum(c.moves_per_hour for c in self.cranes) * derate

    def waiting_calls(self) -> List[VesselCall]:
        return sorted(
            (c for c in self.calls if c.state == WAITING),
            key=lambda c: (c.arrived_hour if c.arrived_hour is not None else c.eta_hour),
        )

    def free_berths(self, *, at_hour: Optional[float] = None) -> List[Berth]:
        hour = self.hour if at_hour is None else at_hour
        return [
            b for b in self.berths
            if b.occupied_by is None or (b.free_at_hour is not None and b.free_at_hour <= hour)
        ]

    def metrics(self) -> Dict[str, Any]:
        """The operational read-out. What every overlay and reward is built on."""
        completed = [c for c in self.calls if c.state == DEPARTED]
        waits = [c.wait_hours for c in completed]
        turnarounds = [
            c.turnaround_hours for c in completed if c.turnaround_hours is not None
        ]
        missed = [
            c for c in completed
            if c.latest_departure_hour is not None
            and c.departed_hour is not None
            and c.departed_hour > c.latest_departure_hour
        ]
        return {
            "hour": round(self.hour, 3),
            "queueLength": self.queue_length,
            "alongside": self.alongside_count,
            "berthUtilisation": round(self.berth_utilisation, 4),
            "yardUtilisation": round(self.yard_utilisation, 4),
            "craneCapacityMovesPerHour": round(self.total_crane_capacity, 2),
            "completedCalls": len(completed),
            "meanWaitHours": round(sum(waits) / len(waits), 3) if waits else None,
            "maxWaitHours": round(max(waits), 3) if waits else None,
            "meanTurnaroundHours": (
                round(sum(turnarounds) / len(turnarounds), 3) if turnarounds else None
            ),
            "missedDepartures": len(missed),
            "yardOverflowBlocks": sum(1 for b in self.yard_blocks if b.utilisation > 0.95),
            "weatherImpact": round(self.weather_impact, 4),
            "eventRisk": round(self.event_risk, 4),
        }

    def clone(self) -> "PortState":
        """A deep copy. Rollouts must never mutate the live state."""
        import copy

        return copy.deepcopy(self)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portCode": self.port_code,
            "portName": self.port_name,
            "hour": round(self.hour, 3),
            "epoch": self.epoch,
            "geometryBasis": self.geometry_basis,
            "geometryDisclaimer": (
                SCHEMATIC_DISCLAIMER if self.geometry_basis == GEOMETRY_SCHEMATIC else None
            ),
            "extentM": list(self.extent_m),
            "seawardBearing": self.seaward_bearing,
            "berths": [b.to_dict() for b in self.berths],
            "cranes": [c.to_dict() for c in self.cranes],
            "yardBlocks": [b.to_dict() for b in self.yard_blocks],
            "sheds": [s.to_dict() for s in self.sheds],
            "gates": [g.to_dict() for g in self.gates],
            "vehicles": [v.to_dict() for v in self.vehicles],
            "calls": [c.to_dict() for c in self.calls],
            "weatherImpact": round(self.weather_impact, 4),
            "eventRisk": round(self.event_risk, 4),
            "metrics": self.metrics(),
            "notes": self.notes,
        }


# --------------------------------------------------------------------------
# building a state
# --------------------------------------------------------------------------

#: Berth length classes, metres. A real port has a mix; assuming every berth
#: takes a 400 m vessel would let the optimiser make assignments no port could.
_BERTH_LENGTHS = (180.0, 230.0, 280.0, 330.0, 400.0)
_BERTH_DEPTHS = (9.5, 11.0, 12.5, 14.0, 16.5)

#: Container yard ground slots per berth. Mid-range for an Indian container
#: terminal; scaled by the registry's capacity index.
_SLOTS_PER_BERTH = 900

#: Quay cranes per berth. Between two and three is the working assumption for a
#: container berth; the gang actually assigned to a call is a decision, not a
#: constant, which is the whole point of the allocation problem.
_CRANES_PER_BERTH = 2.4

#: Nominal crane productivity, moves per hour. Deliberately conservative.
_CRANE_MOVES_PER_HOUR = 26.0


def schematic_layout(
    port_code: str,
    *,
    berth_count: Optional[int] = None,
    capacity_index: Optional[float] = None,
    seaward_bearing: float = 270.0,
) -> PortState:
    """Build a schematic but internally consistent port state.

    Everything structural scales off two real numbers from the port registry --
    the berth count and the capacity index -- so a large port gets a large twin
    and a feeder port does not. The *arrangement* is a schematic: berths along a
    straight quay, yard blocks ranked behind them, sheds behind those.
    """
    record = port_registry.resolve(port_code)
    name = record.name if record else port_code
    berths_n = int(berth_count or (record.berth_count if record else 6))
    berths_n = max(2, min(28, berths_n))
    capacity = float(capacity_index if capacity_index is not None
                     else (record.capacity if record else 0.6))

    state = PortState(
        port_code=(record.locode if record else port_code),
        port_name=name,
        geometry_basis=GEOMETRY_SCHEMATIC,
        seaward_bearing=seaward_bearing,
    )

    quay_length = berths_n * 340.0
    state.extent_m = (quay_length + 900.0, 1500.0)

    # -- berths, along a straight quay at y = 0 ---------------------------
    for index in range(berths_n):
        # Longer berths cluster at one end, as they do where a terminal was
        # extended seaward over time.
        tier = min(len(_BERTH_LENGTHS) - 1, int((index / max(1, berths_n - 1)) * len(_BERTH_LENGTHS)))
        handles = ["container"] if tier >= 2 else ["container", "general", "breakbulk"]
        if index == berths_n - 1:
            handles = ["liquid", "general"]
        state.berths.append(
            Berth(
                berth_id=f"B{index + 1}",
                name=f"Berth {index + 1}",
                length_m=_BERTH_LENGTHS[tier],
                depth_m=_BERTH_DEPTHS[tier],
                handles=handles,
                x=180.0 + index * 340.0,
                y=0.0,
                heading_deg=90.0,
            )
        )

    # -- cranes, railed along the quay ------------------------------------
    #
    # Cranes share a rail, so a crane can be walked to the berth next door. That
    # is what makes crane allocation a decision at all: with a fixed gang per
    # berth there would be nothing to optimise. Each crane therefore serves its
    # home berth and its immediate neighbours, which is how a linear quay works.
    crane_total = max(3, int(round(berths_n * _CRANES_PER_BERTH * (0.8 + 0.5 * capacity))))
    per_berth = crane_total / max(1, berths_n)
    for index in range(crane_total):
        home = min(berths_n - 1, int(index / max(1e-9, per_berth)))
        berth = state.berths[home]
        reachable = [
            state.berths[j].berth_id
            for j in range(max(0, home - 1), min(berths_n, home + 2))
        ]
        crane = Crane(
            crane_id=f"QC{index + 1}",
            name=f"QC{index + 1}",
            moves_per_hour=_CRANE_MOVES_PER_HOUR * (0.85 + 0.3 * capacity),
            serves=reachable,
            x=berth.x + (index % 2) * 90.0 - 45.0,
            y=-30.0,
        )
        state.cranes.append(crane)
        for berth_id in reachable:
            target = state.berth(berth_id)
            if target is not None:
                target.crane_ids.append(crane.crane_id)

    # -- yard blocks, ranked behind the quay ------------------------------
    block_count = max(3, int(round(berths_n * 1.5)))
    slots_each = int(_SLOTS_PER_BERTH * (0.6 + 0.8 * capacity) * berths_n / block_count)
    per_row = max(3, int(math.ceil(block_count / 3)))
    for index in range(block_count):
        row, column = divmod(index, per_row)
        accepts = ["import", "export", "transshipment"]
        if index == block_count - 1:
            accepts = ["transshipment"]
        state.yard_blocks.append(
            YardBlock(
                block_id=f"Y{index + 1}",
                name=f"Yard {chr(65 + row)}{column + 1}",
                slots=max(120, slots_each),
                tiers=4 if capacity > 0.5 else 3,
                accepts=accepts,
                reefer_plugs=int(80 * capacity) if index % 3 == 0 else 0,
                x=240.0 + column * 300.0,
                y=260.0 + row * 190.0,
                width_m=240.0,
                depth_m=140.0,
            )
        )

    # -- sheds behind the yard --------------------------------------------
    for index in range(max(2, berths_n // 3)):
        state.sheds.append(
            Shed(
                shed_id=f"S{index + 1}",
                name=f"Shed {index + 1}",
                area_m2=9000.0 * (0.6 + capacity),
                stores=["breakbulk", "project"] if index % 2 == 0 else ["bagged"],
                x=300.0 + index * 340.0,
                y=880.0,
                width_m=260.0,
                depth_m=110.0,
            )
        )

    # -- gates and internal movers ----------------------------------------
    state.gates.append(
        Gate(
            gate_id="G1",
            name="Main gate",
            lanes=max(4, int(berths_n * 1.2)),
            trucks_per_hour=40.0 * (0.7 + capacity),
            x=state.extent_m[0] * 0.5,
            y=1180.0,
        )
    )
    vehicle_count = max(6, int(crane_total * 2.5))
    for index in range(vehicle_count):
        block = state.yard_blocks[index % len(state.yard_blocks)]
        state.vehicles.append(
            YardVehicle(
                vehicle_id=f"V{index + 1}",
                kind="terminal_tractor" if index % 3 else "straddle",
                moves_per_hour=9.0,
                x=block.x + (index % 4) * 40.0,
                y=block.y - 90.0,
                assigned_block=block.block_id,
            )
        )

    state.notes.append(SCHEMATIC_DISCLAIMER)
    return state


def seed_yard(state: PortState, utilisation: float, *, mean_dwell_hours: float = 62.0) -> None:
    """Fill the yard to a target utilisation, weighted toward the quay.

    Real terminals fill the blocks nearest the quay first, so the pressure a
    controller feels is not evenly spread. The optimiser needs that asymmetry to
    have anything to optimise.
    """
    if not state.yard_blocks:
        return
    target = max(0.0, min(1.0, utilisation))
    blocks = sorted(state.yard_blocks, key=lambda b: b.y)
    n = len(blocks)
    for index, block in enumerate(blocks):
        # Linear ramp from 1.3x the target at the quay to 0.7x at the back.
        gradient = 1.3 - 0.6 * (index / max(1, n - 1))
        block.occupied_teu = min(block.capacity_teu, block.capacity_teu * target * gradient)
        block.mean_dwell_hours = mean_dwell_hours * (0.8 + 0.4 * (index / max(1, n - 1)))


def state_from_snapshot(
    port_code: str,
    snapshot: Dict[str, Any],
    *,
    epoch: Optional[str] = None,
    seaward_bearing: float = 270.0,
) -> PortState:
    """Build a twin seeded from the observed port snapshot.

    The snapshot is the pipeline's measured state for the port: queue pressure,
    anchorage count, capacity pressure, weather impact. Those become the twin's
    starting occupancy, so the simulation begins from the port as observed rather
    than from an empty terminal.
    """
    state = schematic_layout(
        port_code,
        berth_count=snapshot.get("berthCount"),
        capacity_index=snapshot.get("capacityIndex"),
        seaward_bearing=seaward_bearing,
    )
    state.epoch = epoch
    state.weather_impact = float(snapshot.get("weatherImpact") or 0.0)

    capacity_pressure = float(snapshot.get("capacityPressure") or 0.55)
    seed_yard(state, min(0.94, 0.42 + capacity_pressure * 0.5))

    # Occupy berths in proportion to the observed queue pressure. This is the
    # one place the twin is seeded from measurement rather than assumption, and
    # the note records it.
    queue_pressure = float(snapshot.get("queuePressure") or 0.0)
    occupied = int(round(len(state.berths) * min(0.92, 0.35 + queue_pressure * 0.6)))
    for berth in state.berths[:occupied]:
        berth.occupied_by = f"seed-{berth.berth_id}"
        berth.free_at_hour = 2.0 + (hash(berth.berth_id) % 14)

    state.notes.append(
        f"Initial berth and yard occupancy seeded from the observed snapshot: "
        f"queue pressure {queue_pressure:.2f}, capacity pressure {capacity_pressure:.2f}."
    )
    return state


__all__ = [
    "ALONGSIDE",
    "APPROACHING",
    "DEPARTED",
    "GEOMETRY_SCHEMATIC",
    "GEOMETRY_SURVEYED",
    "SCHEMATIC_DISCLAIMER",
    "VESSEL_STATES",
    "WAITING",
    "Berth",
    "Crane",
    "Gate",
    "PortState",
    "Shed",
    "VesselCall",
    "YardBlock",
    "YardVehicle",
    "schematic_layout",
    "seed_yard",
    "state_from_snapshot",
]
