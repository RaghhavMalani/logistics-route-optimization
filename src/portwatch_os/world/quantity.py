"""Dimensioned magnitudes, and the arithmetic a cascade is allowed to do.

A consequence does not keep its units as it travels. "The Red Sea is dangerous"
is a risk; "fourteen voyages are exposed" is a count; "plus 4.1 days" is a
duration; "yard pressure up 12%" is a ratio; "18.4 lakh rupees" is money. Each
is a different kind of thing, and the step between them is where the reasoning
actually lives.

So a quantity carries its unit, and the propagation layer may only move between
units through a named transfer function. That rules out the failure this design
exists to prevent: a graph that multiplies a severity by a distance, calls the
result an impact, and cannot say what it means.

Three rules hold throughout.

*   **Confidence travels with the value, multiplicatively.** A conclusion three
    inferences deep cannot be more certain than the weakest inference in it.
*   **A missing input is not a zero.** A transfer that cannot be computed
    returns ``None`` and the cascade records why, exactly as the exposure graph
    already does with its ``notes``. A zero would be a claim; ``None`` is the
    honest absence of one.
*   **A quantity knows when it is true.** Everything here is temporal. A
    magnitude that has expired is not evidence about now, and a cascade run at
    a future instant must not pick it up.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# units
# --------------------------------------------------------------------------

#: Probability-like, 0..1. Aggregates by noisy-OR, never by addition: two
#: independent threats to one lane do not make a risk of 1.6.
RISK = "risk"
#: A count of hulls. Additive.
VESSELS = "vessels"
#: Duration, hours. Additive. The unit most of the operational layer speaks.
HOURS = "hours"
#: Twenty-foot equivalent units of cargo. Additive.
TEU = "teu"
#: Quay time consumed, berth-hours. Additive.
BERTH_HOURS = "berth_hours"
#: A dimensionless proportion, e.g. yard occupancy pressure. Additive.
RATIO = "ratio"
#: Indian rupees. Additive. The unit a CFO reads.
INR = "inr"

UNITS: Tuple[str, ...] = (RISK, VESSELS, HOURS, TEU, BERTH_HOURS, RATIO, INR)

#: How several inbound quantities of one unit combine at a single node.
NOISY_OR = "noisy_or"
SUM = "sum"

AGGREGATION: Dict[str, str] = {
    RISK: NOISY_OR,
    VESSELS: SUM,
    HOURS: SUM,
    TEU: SUM,
    BERTH_HOURS: SUM,
    RATIO: SUM,
    INR: SUM,
}

#: Units bounded above by 1.0, clamped after any arithmetic.
_BOUNDED = frozenset({RISK})

UNIT_LABELS: Dict[str, str] = {
    RISK: "risk",
    VESSELS: "vessels",
    HOURS: "h",
    TEU: "TEU",
    BERTH_HOURS: "berth-h",
    RATIO: "%",
    INR: "INR",
}


class UnitError(ValueError):
    """Two quantities were combined that do not share a unit."""


# --------------------------------------------------------------------------
# time
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Interval:
    """When something is true. Open at either end.

    An open start reads as "true as far back as this graph knows", which is the
    honest reading for a routing fact such as a lane transiting a strait. An
    open end reads as "still true", not "true forever" -- a distinction that
    matters the moment a cascade is run at a future instant.
    """

    start: Optional[datetime] = None
    end: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError(
                f"an interval cannot end ({self.end.isoformat()}) before it starts "
                f"({self.start.isoformat()})"
            )

    def contains(self, moment: datetime) -> bool:
        if self.start is not None and moment < self.start:
            return False
        if self.end is not None and moment > self.end:
            return False
        return True

    def overlaps(self, other: "Interval") -> bool:
        if self.end is not None and other.start is not None and self.end < other.start:
            return False
        if other.end is not None and self.start is not None and other.end < self.start:
            return False
        return True

    def clipped_to(self, other: "Interval") -> "Interval":
        """The overlap of two intervals: a derived quantity's validity window."""
        start = _later(self.start, other.start)
        end = _earlier(self.end, other.end)
        if start is not None and end is not None and end < start:
            # No overlap. Collapse to an instant rather than raise -- the caller
            # is asking what a derived value's window is, and an empty window is
            # a legitimate answer to that.
            return Interval(start, start)
        return Interval(start, end)

    @property
    def is_empty(self) -> bool:
        return (
            self.start is not None and self.end is not None and self.start == self.end
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": None if self.start is None else self.start.isoformat(),
            "end": None if self.end is None else self.end.isoformat(),
        }


ALWAYS = Interval()


def _later(a: Optional[datetime], b: Optional[datetime]) -> Optional[datetime]:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _earlier(a: Optional[datetime], b: Optional[datetime]) -> Optional[datetime]:
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def window(start: datetime, hours: float) -> Interval:
    """An interval of ``hours`` beginning at ``start``."""
    return Interval(start, start + timedelta(hours=hours))


def utc(moment: Optional[datetime] = None) -> datetime:
    """A timezone-aware UTC instant. Naive input is read as UTC, not local."""
    if moment is None:
        return datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


# --------------------------------------------------------------------------
# quantities
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Quantity:
    """A magnitude, its unit, how sure of it we are, and when it holds."""

    value: float
    unit: str
    #: 0..1. Multiplicative along a chain.
    confidence: float = 1.0
    interval: Interval = ALWAYS
    #: Detail a transfer wants to carry forward -- the detour distance a delay
    #: came from, say. Never used in arithmetic; shown to people.
    attrs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.unit not in UNITS:
            raise UnitError(f"{self.unit!r} is not a unit this graph carries")
        object.__setattr__(self, "value", _bound(self.unit, self.value))
        object.__setattr__(self, "confidence", _clamp(self.confidence))

    # -- arithmetic ------------------------------------------------------
    def scaled(self, factor: float, *, confidence: float = 1.0) -> "Quantity":
        """Multiply the magnitude, attenuating the confidence alongside it."""
        return replace(
            self,
            value=_bound(self.unit, self.value * factor),
            confidence=_clamp(self.confidence * _clamp(confidence)),
        )

    def converted(
        self,
        value: float,
        unit: str,
        *,
        confidence: float = 1.0,
        interval: Optional[Interval] = None,
        **attrs: Any,
    ) -> "Quantity":
        """A new quantity in another unit, carrying this one's confidence.

        The only sanctioned way to change unit. A transfer calls this so the
        confidence chain is never quietly reset to 1.0 by a hop that happened to
        produce a fresh number.
        """
        return Quantity(
            value=value,
            unit=unit,
            confidence=_clamp(self.confidence * _clamp(confidence)),
            interval=self.interval if interval is None else interval,
            attrs=dict(attrs),
        )

    def combined_with(self, other: "Quantity") -> "Quantity":
        """Aggregate two quantities of one unit arriving at one node."""
        if self.unit != other.unit:
            raise UnitError(
                f"cannot combine {self.unit} with {other.unit}; a transfer function "
                "is what moves between units"
            )
        how = AGGREGATION[self.unit]
        if how == NOISY_OR:
            value = 1.0 - (1.0 - self.value) * (1.0 - other.value)
        else:
            value = self.value + other.value
        return Quantity(
            value=value,
            unit=self.unit,
            # Either path alone would have supported the claim, so the aggregate
            # takes the stronger confidence rather than the product.
            confidence=max(self.confidence, other.confidence),
            interval=self.interval.clipped_to(other.interval),
            attrs={**self.attrs, **other.attrs},
        )

    @property
    def is_negligible(self) -> bool:
        return abs(self.value) < 1e-9

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": round(self.value, 4),
            "unit": self.unit,
            "unitLabel": UNIT_LABELS[self.unit],
            "confidence": round(self.confidence, 4),
            "interval": self.interval.to_dict(),
            "attrs": self.attrs,
        }

    def __str__(self) -> str:
        if self.unit == RATIO:
            return f"{self.value * 100:.1f}%"
        if self.unit == INR:
            return f"INR {self.value:,.0f}"
        if self.unit == VESSELS:
            return f"{self.value:.0f} vessels"
        if self.unit == RISK:
            return f"risk {self.value:.2f}"
        return f"{self.value:.1f} {UNIT_LABELS[self.unit]}"


def risk(
    value: float, *, confidence: float = 1.0, interval: Interval = ALWAYS, **attrs: Any
) -> Quantity:
    return Quantity(value, RISK, confidence, interval, dict(attrs))


def hours(
    value: float, *, confidence: float = 1.0, interval: Interval = ALWAYS, **attrs: Any
) -> Quantity:
    return Quantity(value, HOURS, confidence, interval, dict(attrs))


def aggregate(quantities: Sequence[Quantity]) -> Dict[str, Quantity]:
    """Fold a mixed bag of quantities into one per unit."""
    folded: Dict[str, Quantity] = {}
    for quantity in quantities:
        existing = folded.get(quantity.unit)
        folded[quantity.unit] = (
            quantity if existing is None else existing.combined_with(quantity)
        )
    return folded


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _bound(unit: str, value: float) -> float:
    return _clamp(value) if unit in _BOUNDED else float(value)


__all__ = [
    "AGGREGATION",
    "ALWAYS",
    "BERTH_HOURS",
    "HOURS",
    "INR",
    "Interval",
    "NOISY_OR",
    "Quantity",
    "RATIO",
    "RISK",
    "SUM",
    "TEU",
    "UNITS",
    "UNIT_LABELS",
    "UnitError",
    "VESSELS",
    "aggregate",
    "hours",
    "risk",
    "utc",
    "window",
]
