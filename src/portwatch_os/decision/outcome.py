"""The closure outcome model: what a routing option costs once the water has
actually closed for a stated length of time.

One physics, used twice. The mission scorecard scores a replayed decision
with it after the reveal, when the reopening and the backlog clearance are
known from the sources. The robust decision policy evaluates every option
with it *before* the reveal, under several stated durations, because the one
thing a closure claim never carries is how long the closure will last. A
decision engine that predicts with one model and is scored with another
cannot learn from being wrong; this module is the one model.

The model, as the scorecard states it:

*   A hull that reaches the closed water waits until it reopens, then takes
    its turn in a queue drained linearly in arrival order between the
    reopening and the backlog-clearance bound. Arriving early in the closure
    means queuing near the front; arriving late means queuing near the back.
*   A hull arriving after the reopening but before the backlog has cleared
    waits the remaining share of the drain.
*   A hull on the alternative routing takes its certain detour; the
    alternative is assumed open.
*   A hull that lands at another port takes the passage difference the routing
    geometry gives, floored at zero; onward carriage of its consignments to
    the booked port is not modelled and is said so.

The backlog drain is the one figure the model needs that a claim does not
state. It is taken from the two closures the product has recorded with their
sources -- the Ever Given (2021) and Cyclone Biparjoy at Kandla (2023) -- as a
fraction of the closure's own duration. Two recorded outcomes are evidence for
a stated assumption, not a distribution, and the policy evaluates every option
under both the recorded queue and no queue at all so that a recommendation
resting on the queue alone is caught.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from src.portwatch_os.decision.model import DecisionOption, DecisionProblem


def parse_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# the recorded backlog drains
# --------------------------------------------------------------------------

#: Ever Given, Suez, 2021: blocked 2021-03-23T05:40Z, reopened 2021-03-29T17:00Z
#: (155.3 h), backlog cleared by the end of 2021-04-03 (127.0 h after the
#: reopening). ``src.portwatch_os.missions.catalogue.OUTCOME``.
EVER_GIVEN_DRAIN_FRACTION = 0.818
#: Cyclone Biparjoy, Kandla, 2023: closed 2023-06-14T05:32Z, reopened
#: 2023-06-17T12:13Z (78.7 h), operations in full swing 2023-06-19T12:00Z
#: (47.8 h after the reopening). ``src.portwatch_os.missions.biparjoy.OUTCOME``.
BIPARJOY_DRAIN_FRACTION = 0.607

#: The two queue models the policy evaluates under. ``RECORDED`` is the mean of
#: the two recorded fractions; ``NONE`` is the water reopening with nobody
#: waiting. A recommendation must survive both.
QUEUE_MODELS: Dict[str, Dict[str, Any]] = {
    "RECORDED": {
        "drainFraction": round((EVER_GIVEN_DRAIN_FRACTION + BIPARJOY_DRAIN_FRACTION) / 2.0, 3),
        "basis": (
            "backlog drain as a fraction of the closure's duration, the mean of the two closures the product "
            f"records with sources: Ever Given 2021 ({EVER_GIVEN_DRAIN_FRACTION:.2f}) and Biparjoy/Kandla 2023 "
            f"({BIPARJOY_DRAIN_FRACTION:.2f}); a stated assumption, not a calibrated figure"
        ),
    },
    "NONE": {
        "drainFraction": 0.0,
        "basis": "no queue forms: the water reopens with nobody waiting; the optimistic bound on the baseline",
    },
}
DEFAULT_QUEUE_MODEL = "RECORDED"


# --------------------------------------------------------------------------
# the closure window
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ClosureWindow:
    """One realisation of the closure: when it began, when the water reopened
    and when the backlog it caused had cleared."""

    blocked_from: datetime
    reopened_at: datetime
    cleared_at: datetime

    @property
    def closure_hours(self) -> float:
        return max(0.0, (self.reopened_at - self.blocked_from).total_seconds() / 3600.0)

    @property
    def drain_hours(self) -> float:
        return max(0.0, (self.cleared_at - self.reopened_at).total_seconds() / 3600.0)

    @classmethod
    def with_drain(cls, blocked_from: datetime, reopened_at: datetime, *, drain_fraction: float) -> "ClosureWindow":
        """A window whose backlog drains a stated fraction of the closure's length."""
        reopened = max(reopened_at, blocked_from)
        hours = (reopened - blocked_from).total_seconds() / 3600.0
        return cls(blocked_from, reopened, reopened + timedelta(hours=max(0.0, drain_fraction) * hours))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blockedFrom": self.blocked_from.isoformat(timespec="seconds"),
            "reopenedAt": self.reopened_at.isoformat(timespec="seconds"),
            "clearedAt": self.cleared_at.isoformat(timespec="seconds"),
            "closureHours": round(self.closure_hours, 1),
            "drainHours": round(self.drain_hours, 1),
        }


# --------------------------------------------------------------------------
# the model
# --------------------------------------------------------------------------


def option_derived(option: DecisionOption) -> Dict[str, Any]:
    """The option's derived state whether it was feasible or rejected."""
    if option.evaluation is not None:
        return option.evaluation.derived
    return (option.provenance.get("rejectedEvaluation") or {}).get("derived", {}) or {}


def closure_delay_hours(
    option: DecisionOption,
    window: ClosureWindow,
    *,
    clock: datetime,
) -> Optional[Dict[str, Any]]:
    """Hours the option adds against the plan under ``window``, or None where
    the model does not cover the action.

    ``clock`` is the instant the option's timings are measured from -- the
    problem's own ``at``. The answer carries ``how`` so a scorecard, a
    benchmark or a decision panel can show the arithmetic rather than the
    number alone.
    """
    derived = option_derived(option)
    if not derived:
        return None
    hours_to_choke = derived.get("hoursToChokepoint")
    hold = float(derived.get("holdHours") or 0.0)

    if option.action in ("REROUTE", "SPEED_UP"):
        eta = option.measure("eta")
        if eta is None or not eta.available:
            return None
        return {"hours": round(eta.value, 1), "how": "certain detour on the alternative routing; the alternative was open"}
    if option.action == "CHANGE_DESTINATION_PORT":
        eta = option.measure("eta")
        shift = None if eta is None else (eta.attrs or {}).get("arrivalShiftAtAlternative")
        if shift is None:
            return None
        target = option.params.get("portCode")
        return {"hours": round(max(0.0, float(shift)), 1),
                "how": f"landed at {target}, {float(shift):+.0f} h against the planned passage; {target} was open; "
                       "onward carriage of consignments to the booked port is not modelled"}
    if hours_to_choke is None:
        return None

    arrival = clock + timedelta(hours=float(hours_to_choke))
    reopened, blocked_from, cleared = window.reopened_at, window.blocked_from, window.cleared_at
    drain_hours = max(0.0, (cleared - reopened).total_seconds() / 3600.0)
    if arrival < reopened:
        wait = (reopened - arrival).total_seconds() / 3600.0
        share = (arrival - blocked_from).total_seconds() / max(1.0, (reopened - blocked_from).total_seconds())
        queue = drain_hours * max(0.0, min(1.0, share))
        return {"hours": round(hold + wait + queue, 1),
                "how": f"held {hold:.0f} h, waited {wait:.0f} h for the reopening, then {queue:.0f} h of "
                       f"queue (arrival share {share:.2f} of the blocked period)"}
    if arrival < cleared:
        remaining = (cleared - arrival).total_seconds() / 3600.0
        fraction = remaining / max(1.0, drain_hours)
        queue = remaining * fraction
        return {"hours": round(hold + queue, 1),
                "how": f"held {hold:.0f} h, arrived after the reopening, {queue:.0f} h of residual queue"}
    return {"hours": round(hold, 1), "how": f"held {hold:.0f} h; arrived after the backlog had cleared"}


def destination_of(option: DecisionOption, problem: DecisionProblem) -> Optional[str]:
    """The port the option lands at: the alternative for a diversion, else the plan's."""
    if option.action == "CHANGE_DESTINATION_PORT":
        return option.params.get("portCode")
    return option_derived(option).get("destinationPort") or problem.subject_id


__all__ = [
    "BIPARJOY_DRAIN_FRACTION",
    "ClosureWindow",
    "DEFAULT_QUEUE_MODEL",
    "EVER_GIVEN_DRAIN_FRACTION",
    "QUEUE_MODELS",
    "closure_delay_hours",
    "destination_of",
    "option_derived",
    "parse_instant",
]
