"""Typed money: amounts that know their currency, rates that know their unit,
and arithmetic that refuses to add what cannot be added.

The failure this module exists to prevent is quiet and expensive: a charter
rate in US dollars per day added to a berth charge in rupees per hour, the sum
labelled "cost", and the number quoted by a CFO. Every value here carries a
dimension, and the only operations permitted are the dimensionally valid ones:

*   ``Money + Money`` requires the same currency, or it raises.
*   ``Rate * Quantity`` requires the quantity's unit to be the rate's
    denominator (hours convert to days explicitly, never implicitly), and it
    yields ``Money`` in the rate's currency.
*   Cross-currency totals go through an :class:`FxTable` holding explicit,
    sourced observations. With no observation for the pair, the total is
    refused rather than approximated -- a refusal is a fact, an approximation
    is a guess dressed as one.

Nothing here knows what a charter or a berth is. It knows currencies, units
and dimensions, which is all it needs to be trusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


class CurrencyMismatch(ValueError):
    """Two amounts in different currencies were combined without an FX rate."""


class DimensionError(ValueError):
    """A rate was applied to a quantity in the wrong unit."""


class FxUnavailable(ValueError):
    """No observation exists for the currency pair a conversion needs."""


#: Units a quantity may carry. Time units convert among themselves; nothing
#: else converts to anything.
HOUR = "hour"
DAY = "day"
TONNE = "tonne"
TEU = "teu"
TEU_DAY = "teu_day"
GRT = "grt"
GRT_HOUR = "grt_hour"
NM = "nm"
MOVE = "move"
CALL = "call"
CRANE_HOUR = "crane_hour"
UNITS: Tuple[str, ...] = (
    HOUR, DAY, TONNE, TEU, TEU_DAY, GRT, GRT_HOUR, NM, MOVE, CALL, CRANE_HOUR,
)

_TIME_TO_HOURS: Dict[str, float] = {HOUR: 1.0, DAY: 24.0}


def _currency(code: str) -> str:
    code = (code or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError(f"{code!r} is not an ISO-4217 currency code")
    return code


@dataclass(frozen=True)
class Quantity:
    """A magnitude in one of the units a rate can be applied to."""

    value: float
    unit: str

    def __post_init__(self) -> None:
        if self.unit not in UNITS:
            raise DimensionError(f"{self.unit!r} is not a unit money can be charged per")

    def converted(self, unit: str) -> "Quantity":
        """Change unit. Only time units convert; anything else is a dimension error."""
        if unit == self.unit:
            return self
        if self.unit in _TIME_TO_HOURS and unit in _TIME_TO_HOURS:
            hours = self.value * _TIME_TO_HOURS[self.unit]
            return Quantity(hours / _TIME_TO_HOURS[unit], unit)
        raise DimensionError(f"cannot convert {self.unit} to {unit}")

    def to_dict(self) -> Dict[str, Any]:
        return {"value": round(self.value, 4), "unit": self.unit}


@dataclass(frozen=True)
class Money:
    amount: float
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _currency(self.currency))

    def __add__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        if other.currency != self.currency:
            raise CurrencyMismatch(
                f"cannot add {self.currency} and {other.currency} without an FX "
                "observation; use FxTable.total()"
            )
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        if other.currency != self.currency:
            raise CurrencyMismatch(
                f"cannot subtract {other.currency} from {self.currency} without an "
                "FX observation"
            )
        return Money(self.amount - other.amount, self.currency)

    def scaled(self, factor: float) -> "Money":
        return Money(self.amount * factor, self.currency)

    def to_dict(self) -> Dict[str, Any]:
        return {"amount": round(self.amount, 2), "currency": self.currency}

    def __str__(self) -> str:
        return f"{self.currency} {self.amount:,.0f}"


@dataclass(frozen=True)
class Rate:
    """Money per unit: USD per day, INR per GRT-hour, USD per tonne."""

    amount: float
    currency: str
    per: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _currency(self.currency))
        if self.per not in UNITS:
            raise DimensionError(f"{self.per!r} is not a unit a rate can be per")

    def __mul__(self, quantity: Quantity) -> Money:
        if not isinstance(quantity, Quantity):
            return NotImplemented
        if quantity.unit != self.per:
            if quantity.unit in _TIME_TO_HOURS and self.per in _TIME_TO_HOURS:
                quantity = quantity.converted(self.per)
            else:
                raise DimensionError(
                    f"a rate per {self.per} cannot be applied to a quantity in "
                    f"{quantity.unit}"
                )
        return Money(self.amount * quantity.value, self.currency)

    def to_dict(self) -> Dict[str, Any]:
        return {"amount": self.amount, "currency": self.currency, "per": self.per}

    def __str__(self) -> str:
        return f"{self.currency} {self.amount:,.4g}/{self.per}"


# --------------------------------------------------------------------------
# foreign exchange
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FxObservation:
    """One observed exchange rate: ``1 base = rate quote``, and where from."""

    base: str
    quote: str
    rate: float
    observed_at: str
    source: str
    source_type: str = "MARKET_DATA"
    provenance: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "base", _currency(self.base))
        object.__setattr__(self, "quote", _currency(self.quote))
        if isinstance(self.rate, bool) or not isinstance(self.rate, (int, float)) or not math.isfinite(self.rate) \
                or self.rate <= 0:
            raise ValueError("an exchange rate must be a finite positive number")
        if not self.source:
            raise ValueError("an FX observation must name its source")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base": self.base, "quote": self.quote, "rate": self.rate,
            "observedAt": self.observed_at, "source": self.source,
            "sourceType": self.source_type, "provenance": self.provenance,
        }


class FxTable:
    """Explicit exchange observations, and conversions that cite them."""

    def __init__(self, observations: Iterable[FxObservation] = ()) -> None:
        self._pairs: Dict[Tuple[str, str], FxObservation] = {}
        for observation in observations:
            self.add(observation)

    def add(self, observation: FxObservation) -> None:
        self._pairs[(observation.base, observation.quote)] = observation

    def observation(self, base: str, quote: str) -> Optional[FxObservation]:
        return self._pairs.get((_currency(base), _currency(quote)))

    def convert(self, money: Money, to: str) -> Tuple[Money, Optional[FxObservation]]:
        """Convert, returning the observation used; identity conversions use none."""
        target = _currency(to)
        if money.currency == target:
            return money, None
        direct = self._pairs.get((money.currency, target))
        if direct is not None:
            return Money(money.amount * direct.rate, target), direct
        inverse = self._pairs.get((target, money.currency))
        if inverse is not None:
            return Money(money.amount / inverse.rate, target), inverse
        raise FxUnavailable(
            f"no FX observation for {money.currency}->{target}; cross-currency "
            "aggregation is refused rather than approximated"
        )

    def total(self, amounts: Sequence[Money], *, currency: str) -> Tuple[Money, List[FxObservation]]:
        """Sum in one currency, citing every observation the sum relied on."""
        target = _currency(currency)
        running = Money(0.0, target)
        used: List[FxObservation] = []
        for amount in amounts:
            converted, observation = self.convert(amount, target)
            running = running + converted
            if observation is not None and observation not in used:
                used.append(observation)
        return running, used

    def to_dict(self) -> Dict[str, Any]:
        return {"observations": [o.to_dict() for o in self._pairs.values()]}

    def __len__(self) -> int:
        return len(self._pairs)


def total(amounts: Sequence[Money], *, currency: str, fx: Optional[FxTable] = None) -> Tuple[Money, List[FxObservation]]:
    """Sum amounts into one currency. Without an FX table, mixed currencies raise."""
    table = fx if fx is not None else FxTable()
    return table.total(amounts, currency=currency)


__all__ = [
    "CALL",
    "CRANE_HOUR",
    "CurrencyMismatch",
    "DAY",
    "DimensionError",
    "FxObservation",
    "FxTable",
    "FxUnavailable",
    "GRT",
    "GRT_HOUR",
    "HOUR",
    "MOVE",
    "Money",
    "NM",
    "Quantity",
    "Rate",
    "TEU",
    "TEU_DAY",
    "TONNE",
    "UNITS",
    "total",
]
