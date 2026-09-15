"""Transfers: the step where a consequence changes what it is.

This is the part of the world engine that carries the domain. Everything else
is structure and bookkeeping.

A transfer answers one question: *given this quantity arriving at this node, and
this relationship leaving it, what reaches the other end -- and in what unit?*
It is registered against a pair, ``(edge kind, incoming unit)``, so the engine
never has to guess which rule applies, and two rules can never quietly compete
for the same hop.

The chain the product actually needs looks like this, and each arrow is one
registered function below:

    event --threatens--> chokepoint      risk  -> risk
    chokepoint --transits--> lane        risk  -> risk
    lane --sails--> vessel               risk  -> risk + vessels
    vessel --bound_for--> port           risk  -> hours
    port (arrival shift)                 hours -> ratio     (yard pressure)
    port (pressure priced)               ratio -> inr

Two design rules earn their keep here.

**A transfer may decline.** Returning ``None`` means "this cannot be computed
from what is present", and the cascade records the reason rather than
substituting a zero. A lane with no alternative routing has no detour hours; the
honest output is a refusal that names the missing input, which is also the
finding an operator most needs -- Hormuz has no bypass.

**A transfer may emit more than one quantity.** A lane reaching a vessel yields
both the risk that vessel carries and the fact that it is one exposed hull. The
cascade aggregates each unit separately at the destination, so "14 voyages
exposed" and "risk 0.72" arrive together without either being derived from the
other by a fudge factor.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.world.graph import (
    EXPECTS,
    BOUND_FOR,
    CARGO,
    CARRIES,
    Edge,
    Node,
    PORT,
    SAILS,
    THREATENS,
    TRANSITS,
)
from src.portwatch_os.world.quantity import (
    HOURS,
    INR,
    RATIO,
    RISK,
    TEU,
    VESSELS,
    Quantity,
)

#: Below this, an exposed vessel is not counted as exposed. A vessel whose lane
#: risk is a rounding error should not appear in a count an operator reads as
#: "hulls I must look at".
EXPOSURE_COUNT_FLOOR = 0.15


@dataclass(frozen=True)
class Transferred:
    """What one hop produced, and why it produced nothing when it did not."""

    quantities: Tuple[Quantity, ...] = ()
    #: Present when the hop declined. Carried into the cascade's notes.
    declined: Optional[str] = None

    @property
    def ok(self) -> bool:
        return bool(self.quantities)


def declined(reason: str) -> Transferred:
    return Transferred(declined=reason)


def yields(*quantities: Optional[Quantity]) -> Transferred:
    kept = tuple(q for q in quantities if q is not None)
    return Transferred(quantities=kept)


#: ``(edge_kind, unit) -> fn(quantity, edge, src_node, dst_node) -> Transferred``
TransferFn = Callable[[Quantity, Edge, Node, Node], Transferred]
#: ``(node_kind, unit) -> fn(quantity, node) -> Transferred``
DeriveFn = Callable[[Quantity, Node], Transferred]

_TRANSFERS: Dict[Tuple[str, str], TransferFn] = {}
_DERIVATIONS: Dict[Tuple[str, str], DeriveFn] = {}


def transfer(edge_kind: str, unit: str) -> Callable[[TransferFn], TransferFn]:
    """Register the rule for one (relationship, incoming unit) pair."""

    def decorator(fn: TransferFn) -> TransferFn:
        pair = (edge_kind, unit)
        if pair in _TRANSFERS:
            raise ValueError(
                f"a transfer for {edge_kind} carrying {unit} is already registered "
                f"as {_TRANSFERS[pair].__name__}; two rules for one hop would make "
                "the result depend on import order"
            )
        _TRANSFERS[pair] = fn
        return fn

    return decorator


def transfer_for(edge_kind: str, unit: str) -> Optional[TransferFn]:
    return _TRANSFERS.get((edge_kind, unit))


def derive(node_kind: str, unit: str) -> Callable[[DeriveFn], DeriveFn]:
    """Register a rule that runs *at* a node rather than along a relationship.

    Some conversions are properties of the place a quantity lands, not of how it
    got there. Arrival bunching becomes yard pressure because of the port's own
    capacity; pressure becomes money because of the port's own cost basis.
    Modelling those as edges would mean inventing a self-loop and pretending the
    consequence travelled somewhere, which is exactly the sort of fiction this
    engine exists to make impossible.
    """

    def decorator(fn: DeriveFn) -> DeriveFn:
        pair = (node_kind, unit)
        if pair in _DERIVATIONS:
            raise ValueError(
                f"a derivation for {node_kind} carrying {unit} is already registered "
                f"as {_DERIVATIONS[pair].__name__}"
            )
        _DERIVATIONS[pair] = fn
        return fn

    return decorator


def derivation_for(node_kind: str, unit: str) -> Optional[DeriveFn]:
    return _DERIVATIONS.get((node_kind, unit))


def registered() -> List[Dict[str, str]]:
    """The rule catalogue, for documentation and Evidence Mode.

    Every way this engine can move between units, in one list. If a number
    appears in the product and no rule here explains how its unit was arrived
    at, that is a bug rather than a gap in the documentation.
    """
    rows = [
        {"appliesTo": "edge", "on": kind, "fromUnit": unit, "rule": fn.__name__,
         "explains": _first_line(fn)}
        for (kind, unit), fn in _TRANSFERS.items()
    ]
    rows += [
        {"appliesTo": "node", "on": kind, "fromUnit": unit, "rule": fn.__name__,
         "explains": _first_line(fn)}
        for (kind, unit), fn in _DERIVATIONS.items()
    ]
    return sorted(rows, key=lambda row: (row["appliesTo"], row["on"], row["fromUnit"]))


def _first_line(fn: Callable[..., Any]) -> str:
    doc = (fn.__doc__ or "").strip()
    return doc.splitlines()[0] if doc else ""


# --------------------------------------------------------------------------
# event -> chokepoint
# --------------------------------------------------------------------------


@transfer(THREATENS, RISK)
def threat_reaches_chokepoint(
    quantity: Quantity, edge: Edge, src: Node, dst: Node
) -> Transferred:
    """Risk at a place is risk at the chokepoint it threatens, attenuated.

    The edge weight is the classifier's confidence that this event actually
    bears on this chokepoint, which is a different thing from how severe the
    event is -- severity is already in the incoming magnitude.

    Stamps which chokepoint this risk is *about*. Everything downstream needs
    it: a lane transits several straits, and a vessel's exposure depends on its
    timing at the one that is actually threatened, not at all of them.
    """
    carried = quantity.scaled(edge.weight, confidence=edge.weight)
    if dst.kind == PORT:
        # The event acts on the port itself: a closure, not a strait. Stamped
        # as such so the hop to the inbound hulls knows what it is carrying.
        return yields(
            carried.converted(carried.value, RISK, port=dst.identifier, closure=True)
        )
    return yields(
        carried.converted(carried.value, RISK, chokepoint=dst.identifier)
    )


# --------------------------------------------------------------------------
# port -> inbound vessel
# --------------------------------------------------------------------------


@transfer(EXPECTS, RISK)
def closure_reaches_inbound_vessel(
    quantity: Quantity, edge: Edge, src: Node, dst: Node
) -> Transferred:
    """A closure at a port is exposure for every hull the port expects.

    The port's own risk is a closure; what reaches a hull bound for it is the
    chance of arriving into a port that cannot receive it. Timing decides it
    as it does at a strait: the hull's declared hours to the destination are
    read off the edge and refused when absent, and a hull already alongside
    (negative hours) is inside the closure rather than approaching it. The
    stamp names the port, so the decision engine holds clear of, or diverts
    from, the right place.
    """
    if not quantity.attrs.get("closure"):
        return declined(f"{src.label} carries no closure risk to pass to {dst.label}")
    hours = edge.attrs.get("hours_to_destination")
    if hours is None:
        return declined(
            f"{dst.label} declares no time to {src.label}, so whether it arrives into "
            "the closure cannot be decided"
        )
    port = quantity.attrs.get("port") or src.identifier
    if hours < 0:
        carried = quantity.scaled(edge.weight, confidence=0.9).converted(
            quantity.value * edge.weight, RISK, already_entered=True, vessel=dst.identifier,
            chokepoint=port, port=port, closure=True,
        )
    else:
        carried = quantity.scaled(edge.weight).converted(
            quantity.value * edge.weight, RISK, already_entered=False,
            hours_to_risk_area=round(float(hours), 1), vessel=dst.identifier,
            chokepoint=port, port=port, closure=True,
        )
    placement = dst.attrs.get("placement_confidence")
    if placement is not None:
        carried = carried.scaled(1.0, confidence=float(placement))
        carried = replace(carried, attrs={**carried.attrs, "observed": True,
                                          "placement_confidence": float(placement)})
    counted = (
        carried.converted(1.0, VESSELS, vessel=dst.identifier)
        if carried.value >= EXPOSURE_COUNT_FLOOR else None
    )
    return yields(carried, counted)


# --------------------------------------------------------------------------
# chokepoint -> lane
# --------------------------------------------------------------------------


@transfer(TRANSITS, RISK)
def chokepoint_reaches_lane(
    quantity: Quantity, edge: Edge, src: Node, dst: Node
) -> Transferred:
    """A lane that transits a threatened chokepoint carries that risk.

    Whether a routing passes a strait is a fact from the lane catalogue, so this
    hop does not attenuate. What it does add is the lane's own fragility: a lane
    with no alternative routing cannot shed the risk by diverting, so it carries
    more of it than one that can go round.
    """
    chokepoint = quantity.attrs.get("chokepoint")
    detour_nm = dst.attrs.get("detour_nm")
    if detour_nm is None:
        # No alternative routing exists. The lane is fully exposed, and that is
        # the finding, not a missing number: Hormuz has no bypass.
        return yields(
            quantity.converted(
                min(1.0, quantity.value * edge.weight * 1.25),
                RISK,
                no_alternative=True,
                lane=dst.identifier,
                chokepoint=chokepoint,
            )
        )
    carried = quantity.scaled(edge.weight, confidence=1.0)
    return yields(
        carried.converted(
            carried.value, RISK, lane=dst.identifier, chokepoint=chokepoint,
        )
    )


# --------------------------------------------------------------------------
# lane -> vessel
# --------------------------------------------------------------------------


@transfer(SAILS, RISK)
def lane_reaches_vessel(
    quantity: Quantity, edge: Edge, src: Node, dst: Node
) -> Transferred:
    """A vessel on an exposed lane is exposed -- if its timing says so.

    Timing is the whole of it. A vessel that clears the water before the event's
    window opens is not exposed, and one already inside cannot act on a
    diversion. Both are real states an operator must be able to tell apart, so
    this hop reads ``hours_to_risk_area`` off the edge and refuses rather than
    guessing when it is absent.

    Emits the vessel's risk and, above a floor, the fact that it is one exposed
    hull -- so a count and a probability arrive together without one being
    fudged out of the other.

    An observed hull carries a ``placement_confidence``: how sure the fusion
    layer is that it is on this lane, bound where it says, when it says. That
    attenuates the *confidence* of what reaches it, never the magnitude -- the
    risk on the water is what it is; what is uncertain is whether this hull is
    in it.
    """
    chokepoint = quantity.attrs.get("chokepoint")
    timings = edge.attrs.get("hours_to_chokepoint") or {}
    hours_to_risk = timings.get(chokepoint) if chokepoint else None
    if hours_to_risk is None:
        where = chokepoint or "the threatened water"
        return declined(
            f"{dst.label} declares no time to {where}, so whether it is exposed "
            "there cannot be decided"
        )

    if hours_to_risk < 0:
        # Already inside. Still exposed, but a diversion recommendation would
        # not be actionable, and the cascade must not imply one is available.
        carried = quantity.scaled(edge.weight, confidence=0.9)
        carried = carried.converted(
            carried.value, RISK, already_entered=True, vessel=dst.identifier,
            chokepoint=chokepoint,
        )
    else:
        carried = quantity.scaled(edge.weight)
        carried = carried.converted(
            carried.value,
            RISK,
            already_entered=False,
            hours_to_risk_area=round(hours_to_risk, 1),
            vessel=dst.identifier,
            chokepoint=chokepoint,
        )

    placement = dst.attrs.get("placement_confidence")
    if placement is not None:
        carried = carried.scaled(1.0, confidence=float(placement))
        carried = replace(carried, attrs={
            **carried.attrs, "observed": True, "placement_confidence": float(placement),
        })

    counted = (
        carried.converted(1.0, VESSELS, vessel=dst.identifier)
        if carried.value >= EXPOSURE_COUNT_FLOOR
        else None
    )
    return yields(carried, counted)


# --------------------------------------------------------------------------
# vessel -> port
# --------------------------------------------------------------------------


@transfer(BOUND_FOR, RISK)
def vessel_reaches_port(
    quantity: Quantity, edge: Edge, src: Node, dst: Node
) -> Transferred:
    """Exposure becomes an arrival shift at the destination, in hours.

    This is the hop where the world stops being about danger and starts being
    about operations, so it is also where the number has to be defensible. The
    delay is the lane's own detour time -- the extra passage the routing
    catalogue measures -- weighted by how likely the diversion is to be taken.
    It is never a free-floating "high impact" figure.
    """
    if quantity.attrs.get("closure"):
        # A closure at the destination produces no detour. The hold a hull
        # takes depends on its arrival against the reopening, which the
        # decision engine computes per option with the instant in hand; the
        # cascade does not guess it here.
        return declined(
            f"{src.label} faces a closure at {dst.label}, not a detour; the hold is computed "
            "per option by the decision engine, not by the cascade"
        )
    detour_hours = src.attrs.get("detour_hours")
    if detour_hours is None:
        return declined(
            f"{src.label} has no measured detour time, so its arrival shift "
            "cannot be computed"
        )
    # Read off the *incoming quantity*, not the node: whether this hull is
    # already inside the water is a property of the exposure that arrived here,
    # and the same vessel can be inside one chokepoint and approaching another.
    if quantity.attrs.get("already_entered"):
        return declined(
            f"{src.label} is already inside the risk area; it has no diversion "
            "left to take, so no arrival shift follows from one"
        )
    shift = detour_hours * quantity.value
    if shift <= 0:
        return declined(f"{src.label} has no arrival shift at this exposure")
    return yields(
        quantity.converted(
            shift,
            HOURS,
            confidence=0.85,
            detour_hours=round(detour_hours, 1),
            port=dst.identifier,
        )
    )


@transfer(BOUND_FOR, HOURS)
def delay_reaches_port(
    quantity: Quantity, edge: Edge, src: Node, dst: Node
) -> Transferred:
    """A vessel's delay is an arrival shift at the port it is bound for.

    The hop a *decision* travels along. Exposure reaching a port is an expected
    shift -- detour weighted by how likely the diversion is -- and arrives by
    the risk rule above. A chosen action produces a delay that is not expected
    but certain: the Cape adds its hours whether or not the strait closes. That
    delay reaches the port unchanged, so a scenario branch can be run back
    through the same yard-pressure and cost derivations as the observed world,
    and the two never disagree about what an hour at the quay means.
    """
    if quantity.value <= 0:
        return declined(f"{src.label} carries no delay to land at {dst.label}")
    return yields(
        quantity.converted(
            quantity.value, HOURS, port=dst.identifier, vessel=src.identifier,
            **{k: v for k, v in quantity.attrs.items() if k in ("option", "action", "certain")},
        )
    )


# --------------------------------------------------------------------------
# port: hours -> yard pressure
# --------------------------------------------------------------------------


@derive(PORT, HOURS)
def arrival_shift_becomes_pressure(quantity: Quantity, node: Node) -> Transferred:
    """Bunched arrivals become yard pressure, scaled by what the port absorbs.

    A property of the port, not of the journey here, so it is a derivation
    rather than an edge: the same bunching is absorbed by a high-capacity
    terminal and is not by one already near its limit. ``capacity`` comes from
    the port registry, so a port that declares none produces a refusal rather
    than a fabricated percentage.

    The incoming hours are the *aggregate* shift across every affected arrival,
    which is the figure that matters -- one ship four hours late is a schedule
    note, ten ships four hours late into the same window is a queue.
    """
    capacity = node.attrs.get("capacity")
    if capacity is None or capacity <= 0:
        return declined(
            f"{node.label} declares no capacity index, so arrival bunching cannot "
            "be turned into yard pressure"
        )
    berths = node.attrs.get("berth_count") or 1
    # Aggregate delay spread over the berths that can work it, against a
    # nominal day, and inversely scaled by how much slack the port has.
    pressure = (quantity.value / max(1, berths) / 24.0) * (1.0 / capacity) * 0.25
    return yields(
        quantity.converted(
            min(pressure, 3.0), RATIO, confidence=0.7,
            capacity=round(float(capacity), 3), berths=berths,
            aggregate_delay_hours=round(quantity.value, 1),
            port=node.identifier,
        )
    )


@derive(PORT, RATIO)
def pressure_becomes_cost(quantity: Quantity, node: Node) -> Transferred:
    """Yard pressure priced, so a recommendation can carry a cost of inaction.

    The first step of the financial twin, and deliberately the most conservative
    one available: pressure is charged only against the berth-hours it actually
    consumes, at a stated day rate, rather than by modelling demurrage,
    detention and SLA penalties whose contract terms this deployment does not
    hold. A port with no declared rate produces no figure at all -- an invented
    rupee number is worse than none, because it would be the one a CFO quotes.
    """
    day_rate = node.attrs.get("berth_day_rate_inr")
    if day_rate is None:
        return declined(
            f"{node.label} has no berth day rate configured, so its yard pressure "
            "cannot be priced. Supply one through the port provider to enable the "
            "financial layer."
        )
    berths = node.attrs.get("berth_count") or 1
    cost = quantity.value * float(day_rate) * berths
    return yields(
        quantity.converted(
            cost, INR, confidence=0.6,
            basis="pressure x berth day rate x berths",
            day_rate_inr=float(day_rate), port=node.identifier,
        )
    )


# --------------------------------------------------------------------------
# cargo
# --------------------------------------------------------------------------


@transfer(CARRIES, HOURS)
def delay_reaches_cargo(
    quantity: Quantity, edge: Edge, src: Node, dst: Node
) -> Transferred:
    """A delayed vessel delays what it carries, and may break a connection.

    The consignment inherits the hull's delay unchanged -- cargo does not travel
    faster than the ship it is on. What changes is whether the delay eats the
    slack before its onward cutoff, which is the thing that actually costs
    money.
    """
    teu = dst.attrs.get("teu")
    slack_hours = dst.attrs.get("slack_hours")
    carried = quantity.converted(
        quantity.value, HOURS, confidence=0.95, cargo=dst.identifier,
    )
    if slack_hours is not None and quantity.value > slack_hours and teu:
        # The connection is missed, so the whole consignment is at risk rather
        # than merely late.
        return yields(
            carried,
            quantity.converted(
                float(teu), TEU, confidence=0.8,
                connection_missed=True,
                slack_hours=round(float(slack_hours), 1),
                cargo=dst.identifier,
            ),
        )
    return yields(carried)


__all__ = [
    "EXPOSURE_COUNT_FLOOR",
    "DeriveFn",
    "TransferFn",
    "Transferred",
    "declined",
    "derivation_for",
    "derive",
    "registered",
    "transfer",
    "transfer_for",
    "yields",
]
