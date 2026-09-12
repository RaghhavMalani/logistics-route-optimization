"""Turn a computed cascade into the handful of things a person should act on.

The engine reads a :class:`~src.portwatch_os.world.cascade.Cascade` and frames
what it already contains. It performs no arithmetic of its own: every magnitude
is lifted from a quantity the World State Engine produced, with unit, confidence
and the rule that made it carried through.

That constraint is the point of the module. Four roles look at one Red Sea
event and see four different queues, but they are four *views of one
computation*. If the port authority's arrival bunching and the carrier's ETA
slip were derived separately, they would eventually disagree, and the first
person to notice would be a customer with both accounts open.

What differs by role is which subjects are worth surfacing:

    NATIONAL_ADMIN     systemic exposure -- chokepoints, lanes, multiple ports
    PORT_AUTHORITY     what lands at their quay -- bunching, pressure, advisories
    SHIPPING_COMPANY   their hulls -- exposure, reroute and slow-steam options
    VESSEL_OPERATOR    the water ahead of one ship, and its destination

and what each may see is enforced by the same scope the tool layer uses, so an
attention queue cannot become a way around advisory visibility.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.portwatch_os.attention.model import (
    ACT_NOW,
    ACT_SOON,
    AttentionItem,
    Effect,
    MONITOR_ONLY,
    NATIONAL,
    NO_ACTION_AVAILABLE,
    Option,
    PORT_AUTHORITY,
    SHIPPING_COMPANY,
    UNAVAILABLE,
    VESSEL_OPERATOR,
    WATCH,
    order,
    urgency_score,
)
from src.portwatch_os.world.cascade import Cascade, Reached
from src.portwatch_os.world.graph import CHOKEPOINT, LANE, PORT, VESSEL
from src.portwatch_os.world.quantity import HOURS, INR, RATIO, RISK, TEU, VESSELS

#: A window shorter than this is treated as already shut. Ordering a diversion
#: is not instantaneous: it needs a master, a bridge team and often an owner, so
#: an option with twenty minutes left is not an option a queue should offer.
MINIMUM_ACTIONABLE_WINDOW_HOURS = 0.5

#: Above this window, the decision can wait for the next shift handover.
WATCH_WINDOW_HOURS = 24.0
#: Below this, it is the thing to do next.
ACT_NOW_WINDOW_HOURS = 3.0


def attention_for(
    cascade: Cascade,
    *,
    scope: str,
    now: Optional[datetime] = None,
    port_code: Optional[str] = None,
    organisation: Optional[str] = None,
    vessel_ids: Optional[Sequence[str]] = None,
    limit: int = 5,
) -> List[AttentionItem]:
    """The ranked queue one identity should see from one cascade."""
    moment = now or cascade.at
    items: List[AttentionItem] = []

    if scope in (SHIPPING_COMPANY, VESSEL_OPERATOR, NATIONAL):
        held = set(vessel_ids or ())
        for reached in cascade.by_kind(VESSEL):
            if scope == VESSEL_OPERATOR and held and reached.node.identifier not in held:
                continue
            if scope == SHIPPING_COMPANY and held and reached.node.identifier not in held:
                continue
            item = _vessel_item(cascade, reached, scope, moment)
            if item is not None:
                items.append(item)

    if scope in (PORT_AUTHORITY, NATIONAL, VESSEL_OPERATOR):
        for reached in cascade.by_kind(PORT):
            if scope == PORT_AUTHORITY and port_code:
                if reached.node.identifier != port_code:
                    continue
            item = _port_item(cascade, reached, scope, moment)
            if item is not None:
                items.append(item)

    if scope == NATIONAL:
        for reached in cascade.by_kind(CHOKEPOINT):
            item = _chokepoint_item(cascade, reached, scope, moment)
            if item is not None:
                items.append(item)

    ranked = order(items)
    return ranked[:limit] if limit else ranked


# --------------------------------------------------------------------------
# subjects
# --------------------------------------------------------------------------


def _vessel_item(
    cascade: Cascade,
    reached: Reached,
    scope: str,
    now: Optional[datetime],
) -> Optional[AttentionItem]:
    """A hull's exposure, and whether anything can still be done about it."""
    exposure = reached.quantities.get(RISK)
    if exposure is None:
        return None

    already_entered = bool(exposure.attrs.get("already_entered"))
    hours_to_risk = exposure.attrs.get("hours_to_risk_area")
    chokepoint = exposure.attrs.get("chokepoint") or "the exposed water"

    # The window is the time before the hull enters the water. Once inside, a
    # diversion is not a decision anybody still has -- which is exactly the
    # case the product must never present as an opportunity.
    window = None if already_entered else hours_to_risk
    status = _status_for(window, already_entered=already_entered)

    delay = _downstream_delay(cascade, reached.node.identifier)
    operational = (
        Effect(
            value=delay.value,
            unit=HOURS,
            confidence=delay.confidence,
            statement=(
                f"about {delay.value:.0f} h added to this voyage if the diversion "
                "is taken"
            ),
            rule="vessel_reaches_port",
        )
        if delay is not None
        else Effect(
            value=None, unit=None,
            unavailable_because=(
                "no measured detour time exists for this routing, so the delay "
                "cannot be stated"
            ),
        )
    )

    if already_entered:
        recommended = None
        alternatives: List[Option] = []
        do_nothing = (
            f"{reached.node.label} is already inside {chokepoint}. It will "
            "transit under the current conditions; there is no diversion left "
            "to order."
        )
        headline = f"{reached.node.label} committed to {chokepoint}"
    else:
        recommended = Option(
            action="reroute",
            summary=f"Divert clear of {chokepoint} on the alternative routing",
            closes_in_hours=window,
            effect=operational,
            tradeoff="Adds passage time; removes the exposure entirely.",
        )
        alternatives = [
            Option(
                action="slow_steam",
                summary=(
                    "Reduce speed to hold position clear of the area until it "
                    "reopens"
                ),
                closes_in_hours=window,
                tradeoff=(
                    "Keeps the shorter routing and saves fuel, but the delay is "
                    "open-ended while the event holds."
                ),
            ),
            Option(
                action="hold",
                summary="Continue as planned and accept the exposure",
                tradeoff="No added passage time; the exposure is unchanged.",
            ),
        ]
        do_nothing = (
            f"{reached.node.label} enters {chokepoint} in about "
            f"{window:.0f} h at the current exposure." if window is not None
            else f"{reached.node.label} remains exposed at {chokepoint}."
        )
        headline = f"{reached.node.label} exposed at {chokepoint}"

    return AttentionItem(
        attention_id=f"att:{cascade.seed_key}:{reached.node.key}",
        subject_type=VESSEL,
        subject_id=reached.node.identifier,
        subject_label=reached.node.label,
        scope=scope,
        headline=headline,
        reason=(
            f"Exposure {exposure.value:.2f} at {chokepoint}, propagated from "
            f"{cascade.seed_key.split(':', 1)[-1]}."
        ),
        severity=exposure.value,
        confidence=exposure.confidence,
        urgency=urgency_score(window),
        status=status,
        action_deadline=_deadline(now, window),
        intervention_window_hours=window,
        baseline_outcome="Voyage runs to its current ETA on the planned routing.",
        do_nothing_outcome=do_nothing,
        recommended_action=recommended,
        alternative_actions=alternatives,
        expected_operational_effect=operational,
        expected_financial_effect=_no_price("a vessel-level cost basis"),
        cascade_id=cascade.seed_key,
        evidence_node_key=reached.node.key,
    )


def _port_item(
    cascade: Cascade,
    reached: Reached,
    scope: str,
    now: Optional[datetime],
) -> Optional[AttentionItem]:
    """Arrival bunching at a port, and the pressure it creates."""
    delay = reached.quantities.get(HOURS)
    pressure = reached.quantities.get(RATIO)
    if delay is None and pressure is None:
        return None

    # A port's window is the soonest affected arrival: once the first delayed
    # ship berths, restaggering the rest buys progressively less.
    window = _soonest_arrival_window(cascade)
    status = _status_for(window, already_entered=False)

    operational = (
        Effect(
            value=pressure.value,
            unit=RATIO,
            confidence=pressure.confidence,
            statement=(
                f"yard pressure up {pressure.value * 100:.0f}% against the "
                "current capacity index"
            ),
            rule="arrival_shift_becomes_pressure",
        )
        if pressure is not None
        else Effect(
            value=delay.value, unit=HOURS, confidence=delay.confidence,
            statement=f"{delay.value:.0f} h of aggregate arrival shift",
            rule="vessel_reaches_port",
        )
    )

    money = reached.quantities.get(INR)
    financial = (
        Effect(
            value=money.value, unit=INR, confidence=money.confidence,
            statement=f"about INR {money.value:,.0f} of berth time at risk",
            rule="pressure_becomes_cost",
        )
        if money is not None
        else _no_price("a berth day rate for this port")
    )

    aggregate_hours = delay.value if delay is not None else None
    return AttentionItem(
        attention_id=f"att:{cascade.seed_key}:{reached.node.key}",
        subject_type=PORT,
        subject_id=reached.node.identifier,
        subject_label=reached.node.label,
        scope=scope,
        headline=f"Arrival bunching building at {reached.node.label}",
        reason=(
            f"{aggregate_hours:.0f} h of aggregate arrival shift across affected "
            f"voyages bound here." if aggregate_hours is not None
            else "Affected voyages are bound here."
        ),
        severity=min(1.0, (pressure.value if pressure else 0.3)),
        confidence=operational.confidence or 0.5,
        urgency=urgency_score(window),
        status=status,
        action_deadline=_deadline(now, window),
        intervention_window_hours=window,
        baseline_outcome="Arrivals berth on their current sequence.",
        do_nothing_outcome=(
            "Delayed arrivals bunch into the same window and queue at anchor."
        ),
        recommended_action=Option(
            action="restagger_arrivals",
            summary="Raise arrival-window advisories to spread the affected calls",
            closes_in_hours=window,
            effect=operational,
            tradeoff=(
                "Each advisory needs a controller's review before it reaches a "
                "master."
            ),
        ),
        alternative_actions=[
            Option(
                action="open_berth",
                summary="Bring an additional berth or gang onto the affected window",
                tradeoff="Uses resource held for scheduled calls.",
            ),
        ],
        expected_operational_effect=operational,
        expected_financial_effect=financial,
        cascade_id=cascade.seed_key,
        evidence_node_key=reached.node.key,
    )


def _chokepoint_item(
    cascade: Cascade,
    reached: Reached,
    scope: str,
    now: Optional[datetime],
) -> Optional[AttentionItem]:
    """Systemic exposure at a strait: the national view's unit of concern."""
    exposure = reached.quantities.get(RISK)
    if exposure is None:
        return None

    hulls = cascade.total(VESSELS)
    lanes = [r.node.label for r in cascade.by_kind(LANE)]
    ports = [r.node.label for r in cascade.by_kind(PORT)]
    if not lanes:
        return None

    operational = (
        Effect(
            value=hulls.value, unit=VESSELS, confidence=hulls.confidence,
            statement=f"{hulls.value:.0f} voyages exposed across {len(lanes)} lanes",
            rule="lane_reaches_vessel",
        )
        if hulls is not None
        else Effect(
            value=None, unit=None,
            unavailable_because=(
                "no voyage in scope declares timing at this chokepoint, so the "
                "exposed count cannot be stated"
            ),
        )
    )

    return AttentionItem(
        attention_id=f"att:{cascade.seed_key}:{reached.node.key}",
        subject_type=CHOKEPOINT,
        subject_id=reached.node.identifier,
        subject_label=reached.node.label,
        scope=scope,
        headline=f"{reached.node.label} exposure reaching {len(ports)} Indian ports",
        reason=(
            f"{len(lanes)} trade lanes transit this chokepoint: "
            f"{', '.join(lanes[:3])}."
        ),
        severity=exposure.value,
        confidence=exposure.confidence,
        urgency=urgency_score(_soonest_arrival_window(cascade)),
        status=WATCH,
        intervention_window_hours=_soonest_arrival_window(cascade),
        action_deadline=_deadline(now, _soonest_arrival_window(cascade)),
        baseline_outcome="Traffic routes normally through the chokepoint.",
        do_nothing_outcome=(
            f"Exposure propagates to {len(ports)} destination ports as arrival "
            "bunching."
        ),
        recommended_action=Option(
            action="issue_national_advisory",
            summary="Brief affected port authorities on the projected bunching",
            tradeoff="Advisory only; the routing decision stays with each carrier.",
        ),
        expected_operational_effect=operational,
        expected_financial_effect=_no_price("a national cost basis"),
        cascade_id=cascade.seed_key,
        evidence_node_key=reached.node.key,
    )


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _status_for(window: Optional[float], *, already_entered: bool) -> str:
    """Where an item sits, decided by whether an option is still open."""
    if already_entered:
        return MONITOR_ONLY
    if window is None:
        return NO_ACTION_AVAILABLE
    if window <= MINIMUM_ACTIONABLE_WINDOW_HOURS:
        # Technically still ahead of the water, but not enough time to order and
        # execute a diversion. Offering it would be offering a fiction.
        return MONITOR_ONLY
    if window <= ACT_NOW_WINDOW_HOURS:
        return ACT_NOW
    if window <= WATCH_WINDOW_HOURS:
        return ACT_SOON
    return WATCH


def _deadline(now: Optional[datetime], window: Optional[float]) -> Optional[str]:
    if now is None or window is None or window <= 0:
        return None
    return (now + timedelta(hours=window)).isoformat()


def _downstream_delay(cascade: Cascade, vessel_id: str):
    """The arrival shift this vessel contributes, read off the port it feeds."""
    for reached in cascade.by_kind(PORT):
        quantity = reached.quantities.get(HOURS)
        if quantity is not None:
            return quantity
    return None


def _soonest_arrival_window(cascade: Cascade) -> Optional[float]:
    """The tightest still-open vessel window in the cascade."""
    windows: List[float] = []
    for reached in cascade.by_kind(VESSEL):
        exposure = reached.quantities.get(RISK)
        if exposure is None or exposure.attrs.get("already_entered"):
            continue
        hours = exposure.attrs.get("hours_to_risk_area")
        if hours is not None and hours > 0:
            windows.append(float(hours))
    return min(windows) if windows else None


def _no_price(missing: str) -> Effect:
    """Refuse to price, and say precisely what is missing.

    The financial twin is the most commercially valuable part of this product
    and the easiest to discredit. One invented rupee figure quoted back by a CFO
    who then finds it was a placeholder costs more than the feature is worth, so
    the absence is stated rather than filled.
    """
    return Effect(
        value=None,
        unit=None,
        unavailable_because=(
            f"this deployment has no {missing} configured, so the financial "
            "effect is not computed"
        ),
    )


__all__ = [
    "ACT_NOW_WINDOW_HOURS",
    "MINIMUM_ACTIONABLE_WINDOW_HOURS",
    "WATCH_WINDOW_HOURS",
    "attention_for",
]
