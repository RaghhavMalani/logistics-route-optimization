"""The action catalogue: what could be done, by whom, and whether it can be
evaluated here.

An action is a typed thing with a name, a domain, the actors entitled to
execute it, the data it needs and the simulator that evaluates it. The catalogue
exists so that "the options" are never an ad-hoc list an engine happened to
produce: every problem enumerates the whole catalogue for its domain and marks
each entry available or not, with the reason, so the operator sees what was
*not* offered as clearly as what was.

An action is ``AVAILABLE`` only when three things hold: the required data
exists on the subject, its constraints can be evaluated, and a simulator here
supports it. Otherwise it is marked ``UNAVAILABLE`` (the world does not permit
it -- no alternative routing exists), ``INSUFFICIENT_DATA`` (the subject does
not declare what the evaluation needs) or ``UNSUPPORTED`` (nothing in this
deployment can compute its consequence). None of those is a scored option. A
name that sounds right is not a reason to offer it.

Actor entitlement is part of the type. A port authority does not reroute a
vessel and a shipping company does not reassign a berth; where an actor wants
an effect it cannot execute, the catalogue holds ``ISSUE_ADVISORY`` -- the
recommendation becomes a proposal to whoever can.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.decision.model import (
    AVAILABLE,
    CARGO_CONNECTION,
    INSUFFICIENT_DATA,
    NATIONAL_ADMIN,
    PORT_AUTHORITY,
    PORT_BERTHING,
    SHIPPING_COMPANY,
    TERMINAL_OPERATOR,
    UNAVAILABLE,
    UNSUPPORTED,
    VESSEL_OPERATOR,
    VESSEL_ROUTING,
    Availability,
)

# -- vessel / shipping company -------------------------------------------
KEEP_PLAN = "KEEP_PLAN"
REROUTE = "REROUTE"
SLOW_STEAM = "SLOW_STEAM"
SPEED_UP = "SPEED_UP"
DELAY_DEPARTURE = "DELAY_DEPARTURE"
DELAY_ARRIVAL = "DELAY_ARRIVAL"
CHANGE_DESTINATION_PORT = "CHANGE_DESTINATION_PORT"
CHANGE_TRANSSHIPMENT = "CHANGE_TRANSSHIPMENT"
REBUNKER = "REBUNKER"

# -- port authority / terminal -------------------------------------------
KEEP_SCHEDULE = "KEEP_SCHEDULE"
SHIFT_ARRIVAL_SLOT = "SHIFT_ARRIVAL_SLOT"
REASSIGN_BERTH = "REASSIGN_BERTH"
ALTER_HOLDING_WINDOW = "ALTER_HOLDING_WINDOW"
CHANGE_CRANE_ALLOCATION = "CHANGE_CRANE_ALLOCATION"
CHANGE_YARD_ALLOCATION = "CHANGE_YARD_ALLOCATION"
PRIORITISE_VESSEL = "PRIORITISE_VESSEL"
ISSUE_ADVISORY = "ISSUE_ADVISORY"

# -- cargo -----------------------------------------------------------------
KEEP_CONNECTION = "KEEP_CONNECTION"
CHANGE_CONNECTION = "CHANGE_CONNECTION"
CHANGE_YARD = "CHANGE_YARD"
TRANSFER_TO_VESSEL = "TRANSFER_TO_VESSEL"
DEFER_SHIPMENT = "DEFER_SHIPMENT"

#: Simulators this deployment holds. An action naming none is UNSUPPORTED
#: everywhere, by construction.
WORLD_ENGINE = "world_engine"
PORT_TWIN = "port_twin"
CARGO_MODEL = "cargo_model"
SIMULATORS: Tuple[str, ...] = (WORLD_ENGINE, PORT_TWIN, CARGO_MODEL)


@dataclass(frozen=True)
class ActionSpec:
    kind: str
    label: str
    domain: str
    #: Actors entitled to execute the action themselves.
    actors: Tuple[str, ...]
    #: Subject data the evaluation needs, by attribute name.
    requires: Tuple[str, ...]
    #: Which simulator evaluates it; ``None`` means nothing here can.
    simulator: Optional[str]
    description: str
    #: Whether this action is the domain's "change nothing".
    baseline: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind, "label": self.label, "domain": self.domain,
            "actors": list(self.actors), "requires": list(self.requires),
            "simulator": self.simulator, "description": self.description,
            "baseline": self.baseline,
        }


CATALOGUE: Dict[str, ActionSpec] = {
    spec.kind: spec for spec in [
        # ---------------------------------------------------------- vessel --
        ActionSpec(KEEP_PLAN, "Continue current plan", VESSEL_ROUTING,
                   (SHIPPING_COMPANY, VESSEL_OPERATOR), ("lane_code",), WORLD_ENGINE,
                   "Hold the planned routing and speed. The baseline every other option "
                   "is measured against.", baseline=True),
        ActionSpec(REROUTE, "Reroute on the alternative routing", VESSEL_ROUTING,
                   (SHIPPING_COMPANY, VESSEL_OPERATOR),
                   ("lane_code", "alternative", "hours_to_chokepoint", "service_speed_kn"),
                   WORLD_ENGINE,
                   "Leave the lane's primary routing for its catalogued alternative, "
                   "clear of the threatened chokepoint."),
        ActionSpec(SLOW_STEAM, "Slow steam and hold clear", VESSEL_ROUTING,
                   (SHIPPING_COMPANY, VESSEL_OPERATOR),
                   ("hours_to_chokepoint", "service_speed_kn", "event_end"), WORLD_ENGINE,
                   "Reduce speed so the vessel reaches the threatened water only once "
                   "the event's claim has lapsed."),
        ActionSpec(SPEED_UP, "Reroute at increased speed", VESSEL_ROUTING,
                   (SHIPPING_COMPANY, VESSEL_OPERATOR),
                   ("lane_code", "alternative", "hours_to_chokepoint", "service_speed_kn"),
                   WORLD_ENGINE,
                   "Take the alternative routing and recover part of the detour by "
                   "running above service speed, within the speed envelope."),
        ActionSpec(DELAY_DEPARTURE, "Delay departure", VESSEL_ROUTING,
                   (SHIPPING_COMPANY,), ("departure_port", "departure_at"), WORLD_ENGINE,
                   "Hold the vessel at its origin until the event clears."),
        ActionSpec(DELAY_ARRIVAL, "Delay arrival", VESSEL_ROUTING,
                   (SHIPPING_COMPANY, VESSEL_OPERATOR),
                   ("destination_port", "eta", "service_speed_kn"), WORLD_ENGINE,
                   "Slow the final approach to arrive into a later berth window."),
        ActionSpec(CHANGE_DESTINATION_PORT, "Change destination port", VESSEL_ROUTING,
                   (SHIPPING_COMPANY,), ("lane_code", "destination_port"), WORLD_ENGINE,
                   "Land at another port the lane serves."),
        ActionSpec(CHANGE_TRANSSHIPMENT, "Change transshipment hub", VESSEL_ROUTING,
                   (SHIPPING_COMPANY,), ("onward_ports", "cargo_manifest"), None,
                   "Route the consignments over a different hub."),
        ActionSpec(REBUNKER, "Rebunker en route", VESSEL_ROUTING,
                   (SHIPPING_COMPANY, VESSEL_OPERATOR),
                   ("bunker_state", "bunker_ports"), None,
                   "Call for fuel on the alternative routing."),
        # ------------------------------------------------------------ port --
        ActionSpec(KEEP_SCHEDULE, "Continue current plan", PORT_BERTHING,
                   (PORT_AUTHORITY, TERMINAL_OPERATOR), ("berths", "calls"), PORT_TWIN,
                   "Run the incumbent rule: first come, first served. The baseline every other "
                   "port option is measured against.", baseline=True),
        ActionSpec(SHIFT_ARRIVAL_SLOT, "Stagger arrivals", PORT_BERTHING,
                   (PORT_AUTHORITY,), ("calls",), PORT_TWIN,
                   "Restagger the bunched arrivals into later slots through advisories."),
        ActionSpec(REASSIGN_BERTH, "Reassign berths", PORT_BERTHING,
                   (PORT_AUTHORITY, TERMINAL_OPERATOR), ("berths", "calls"), PORT_TWIN,
                   "Allocate berths by expected work rather than order of arrival."),
        ActionSpec(ALTER_HOLDING_WINDOW, "Alter holding window", PORT_BERTHING,
                   (PORT_AUTHORITY,), ("anchorage",), None,
                   "Change the anchorage holding sector or window."),
        ActionSpec(CHANGE_CRANE_ALLOCATION, "Reallocate cranes", PORT_BERTHING,
                   (TERMINAL_OPERATOR, PORT_AUTHORITY), ("cranes", "calls"), PORT_TWIN,
                   "Size the crane gang to the call rather than the berth's default."),
        ActionSpec(CHANGE_YARD_ALLOCATION, "Reallocate yard", PORT_BERTHING,
                   (TERMINAL_OPERATOR,), ("yard_blocks",), PORT_TWIN,
                   "Open overflow tiers on the yard blocks under pressure."),
        ActionSpec(PRIORITISE_VESSEL, "Prioritise a vessel", PORT_BERTHING,
                   (PORT_AUTHORITY,), ("calls",), PORT_TWIN,
                   "Move one call up the queue."),
        ActionSpec(ISSUE_ADVISORY, "Issue an advisory", PORT_BERTHING,
                   (PORT_AUTHORITY, NATIONAL_ADMIN), (), PORT_TWIN,
                   "Recommend an action to an actor who can execute it. Never a command."),
        # ----------------------------------------------------------- cargo --
        ActionSpec(KEEP_CONNECTION, "Keep the booked connection", CARGO_CONNECTION,
                   (SHIPPING_COMPANY, TERMINAL_OPERATOR), ("booked_vessel",), CARGO_MODEL,
                   "Leave the consignment booked as it is.", baseline=True),
        ActionSpec(CHANGE_CONNECTION, "Connect via another hub", CARGO_CONNECTION,
                   (SHIPPING_COMPANY,), ("hub_schedules",), None,
                   "Route the consignment through a different hub."),
        ActionSpec(CHANGE_YARD, "Change yard sequence", CARGO_CONNECTION,
                   (TERMINAL_OPERATOR,), ("zones",), CARGO_MODEL,
                   "Stage the consignment in a zone nearer the quay."),
        ActionSpec(TRANSFER_TO_VESSEL, "Transfer to another vessel", CARGO_CONNECTION,
                   (SHIPPING_COMPANY,), ("candidate_vessels",), CARGO_MODEL,
                   "Load the consignment onto a different vessel serving its destination."),
        ActionSpec(DEFER_SHIPMENT, "Wait for the next sailing", CARGO_CONNECTION,
                   (SHIPPING_COMPANY,), ("next_sailing",), CARGO_MODEL,
                   "Hold the consignment for the next sailing to its destination."),
    ]
}


#: Actors who cannot execute a routing or cargo action themselves but may
#: advise the one who can. Their problem is evaluated for the executing actor
#: and the recommendation is framed as an advisory.
ADVISING_ACTORS: Tuple[str, ...] = (PORT_AUTHORITY, NATIONAL_ADMIN)
EXECUTING_ACTOR = SHIPPING_COMPANY


def executing_actor_for(actor: str) -> str:
    return EXECUTING_ACTOR if actor in ADVISING_ACTORS else actor


def for_domain(domain: str) -> List[ActionSpec]:
    return [spec for spec in CATALOGUE.values() if spec.domain == domain]


def entitled(spec: ActionSpec, actor: str) -> bool:
    return actor in spec.actors


def baseline_for(domain: str) -> ActionSpec:
    found = [s for s in CATALOGUE.values() if s.domain == domain and s.baseline]
    if len(found) != 1:
        raise ValueError(f"{domain} must have exactly one baseline action")
    return found[0]


#: A predicate that decides availability from what the subject carries.
#: Domain modules register one per action kind they can evaluate.
AvailabilityFn = Callable[[Dict[str, Any]], Availability]


def availability_of(
    spec: ActionSpec,
    subject: Dict[str, Any],
    *,
    actor: str,
    checks: Optional[Dict[str, AvailabilityFn]] = None,
) -> Availability:
    """Whether this action can be considered for this subject by this actor.

    The order is deliberate: entitlement first (an action the actor cannot
    execute is not made available and then rejected -- it is simply not
    theirs), then simulator support, then the data requirement, then the
    domain's own check. Each step names its reason.
    """
    if not entitled(spec, actor):
        return Availability(
            UNAVAILABLE,
            f"{spec.label} is executed by {', '.join(spec.actors)}, not by {actor}; "
            f"the most this actor can do is propose it through an advisory.",
        )
    if spec.simulator is None:
        return Availability(
            UNSUPPORTED,
            f"no simulator in this deployment evaluates {spec.label.lower()}; the "
            "consequence cannot be computed, so it is not offered.",
        )
    missing = [k for k in spec.requires if subject.get(k) in (None, "", [], {})]
    if missing:
        return Availability(
            INSUFFICIENT_DATA,
            f"{spec.label.lower()} needs {', '.join(missing)}, which the subject "
            "does not declare.",
        )
    check = (checks or {}).get(spec.kind)
    if check is not None:
        return check(subject)
    return Availability(AVAILABLE)


__all__ = [
    "ALTER_HOLDING_WINDOW",
    "ActionSpec",
    "AvailabilityFn",
    "CARGO_MODEL",
    "CATALOGUE",
    "CHANGE_CONNECTION",
    "CHANGE_CRANE_ALLOCATION",
    "CHANGE_DESTINATION_PORT",
    "CHANGE_TRANSSHIPMENT",
    "CHANGE_YARD",
    "CHANGE_YARD_ALLOCATION",
    "DEFER_SHIPMENT",
    "DELAY_ARRIVAL",
    "DELAY_DEPARTURE",
    "ISSUE_ADVISORY",
    "KEEP_CONNECTION",
    "KEEP_PLAN",
    "KEEP_SCHEDULE",
    "PORT_TWIN",
    "PRIORITISE_VESSEL",
    "REASSIGN_BERTH",
    "REBUNKER",
    "REROUTE",
    "SHIFT_ARRIVAL_SLOT",
    "SIMULATORS",
    "SLOW_STEAM",
    "SPEED_UP",
    "TRANSFER_TO_VESSEL",
    "WORLD_ENGINE",
    "availability_of",
    "baseline_for",
    "entitled",
    "for_domain",
]
