"""Financial evaluation: a cost per option, component by component, with every
component either priced, zero for a stated reason, or unknown for a stated
reason.

The distinction between zero and unknown is the whole module. "Fuel
difference: 0" means the option burns the same fuel as the plan. "Fuel
difference: unknown -- no bunker price is configured" means the product cannot
say. A total that silently treated the second as the first would be wrong in
the direction that flatters the recommendation, so a total exists only when
every component is priced or explicitly zero; otherwise the evaluation carries
a *partial* total, the list of what is missing, and no headline figure.

Every priced component names its rate, and every rate names its source type.
Where any component rests on a ``USER_ASSUMPTION`` the whole evaluation is
flagged ``ASSUMPTION``, because a total that mixes a tariff with a typed-in
charter rate is exactly as assumed as its weakest term.

Cross-currency totals go through the explicit FX table. Without an
observation for the pair, the components stay in their own currencies and the
total is unknown with the FX gap named.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from src.portwatch_os.finance.basis import CostBasis, CostRate, PRIMITIVES, USER_ASSUMPTION
from src.portwatch_os.finance.money import (
    CurrencyMismatch,
    FxObservation,
    FxTable,
    FxUnavailable,
    GRT,
    GRT_HOUR,
    Money,
    Quantity,
)

KNOWN = "KNOWN"
ZERO = "ZERO"
UNKNOWN = "UNKNOWN"
STATES = (KNOWN, ZERO, UNKNOWN)


@dataclass
class CostComponent:
    key: str
    label: str
    state: str
    money: Optional[Money] = None
    quantity: Optional[Quantity] = None
    rate: Optional[Dict[str, Any]] = None
    basis: str = ""
    reason: str = ""
    is_assumption: bool = False
    source_type: Optional[str] = None
    #: The operational measure this component priced, for the evidence trail.
    driver: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "state": self.state,
            "money": None if self.money is None else self.money.to_dict(),
            "quantity": None if self.quantity is None else self.quantity.to_dict(),
            "rate": self.rate,
            "basis": self.basis,
            "reason": self.reason,
            "isAssumption": self.is_assumption,
            "sourceType": self.source_type,
            "driver": self.driver,
        }


@dataclass
class FinancialEvaluation:
    currency: str
    components: List[CostComponent] = field(default_factory=list)
    total: Optional[Money] = None
    partial_total: Optional[Money] = None
    unknown: List[Dict[str, str]] = field(default_factory=list)
    assumption: bool = False
    source_types: List[str] = field(default_factory=list)
    fx_used: List[FxObservation] = field(default_factory=list)
    range: Optional[Dict[str, Any]] = None
    notes: List[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.total is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "components": [c.to_dict() for c in self.components],
            "total": None if self.total is None else self.total.to_dict(),
            "partialTotal": None if self.partial_total is None else self.partial_total.to_dict(),
            "complete": self.complete,
            "unknown": self.unknown,
            "assumption": self.assumption,
            "label": "ASSUMPTION" if self.assumption else ("PUBLIC_TARIFF" if "PUBLIC_TARIFF" in self.source_types else None),
            "sourceTypes": self.source_types,
            "fxUsed": [o.to_dict() for o in self.fx_used],
            "range": self.range,
            "notes": self.notes,
        }


class Pricer:
    """Prices components against one basis, at one instant, in one currency."""

    def __init__(
        self,
        basis: CostBasis,
        *,
        at: datetime,
        currency: str = "USD",
        fx: Optional[FxTable] = None,
        scope: Optional[str] = None,
        vessel_status: Optional[str] = None,
        vessel_type: Optional[str] = None,
    ) -> None:
        self.basis = basis
        self.at = at
        self.currency = currency
        self.fx = fx if fx is not None else FxTable()
        self.scope = scope
        self.vessel_status = vessel_status
        self.vessel_type = vessel_type

    # -- components --------------------------------------------------------
    def zero(self, key: str, label: str, because: str, *, driver: Optional[str] = None) -> CostComponent:
        return CostComponent(key, label, ZERO, money=None, reason=because, driver=driver)

    def unknown(self, key: str, label: str, because: str, *, driver: Optional[str] = None) -> CostComponent:
        return CostComponent(key, label, UNKNOWN, money=None, reason=because, driver=driver)

    def priced(
        self,
        key: str,
        label: str,
        primitive: str,
        quantity: Optional[Quantity],
        *,
        driver: Optional[str] = None,
        scope: Optional[str] = None,
        grt: Optional[float] = None,
        zero_because: Optional[str] = None,
    ) -> CostComponent:
        """Price ``quantity`` at the basis's rate for ``primitive``.

        A ``None`` quantity means the driving measure is unknown, which makes
        the component unknown whatever the basis holds. A zero quantity is a
        zero component with the reason given. A missing or lapsed rate is an
        unknown component naming the gap.
        """
        if quantity is None:
            return self.unknown(key, label, f"{label.lower()} cannot be priced: its driving "
                                "quantity is unknown", driver=driver)
        if abs(quantity.value) < 1e-9:
            return self.zero(key, label, zero_because or f"no {PRIMITIVES[primitive].label.lower()} "
                             "is incurred under this option", driver=driver)
        found = self.basis.lookup(
            primitive, at=self.at, scope=scope or self.scope,
            vessel_status=self.vessel_status, vessel_type=self.vessel_type, gt=grt,
        )
        if found.rate is None:
            return self.unknown(key, label, found.reason, driver=driver)
        rate = found.rate
        try:
            if rate.unit in (GRT, GRT_HOUR) and grt is not None:
                # Tonnage charges: the tariff's tier arithmetic on the tonnage,
                # then the quantity (hours, or a single entry) on top.
                per_unit = rate.charge_for_grt(grt)
                money = Money(per_unit.amount * quantity.value, per_unit.currency)
            else:
                money = rate.rate * quantity
        except Exception as exc:  # noqa: BLE001 - a dimension error is an unknown, named
            return self.unknown(key, label, f"{label.lower()} cannot be priced: {exc}", driver=driver)
        return CostComponent(
            key, label, KNOWN, money=money, quantity=quantity, rate=rate.to_dict(),
            basis=f"{rate.source_type} · {rate.source}", reason=found.reason,
            is_assumption=rate.is_assumption, source_type=rate.source_type, driver=driver,
        )

    # -- totals --------------------------------------------------------------
    def evaluation(
        self,
        components: Sequence[CostComponent],
        *,
        range_from: Optional[Dict[str, Any]] = None,
        notes: Sequence[str] = (),
    ) -> FinancialEvaluation:
        evaluation = FinancialEvaluation(currency=self.currency, components=list(components),
                                         notes=list(notes))
        evaluation.unknown = [
            {"key": c.key, "label": c.label, "reason": c.reason}
            for c in components if c.state == UNKNOWN
        ]
        evaluation.assumption = any(c.is_assumption for c in components)
        evaluation.source_types = sorted({c.source_type for c in components if c.source_type})
        known = [c.money for c in components if c.state == KNOWN and c.money is not None]
        if known:
            try:
                partial, used = self.fx.total(known, currency=self.currency)
                evaluation.partial_total = partial
                evaluation.fx_used = used
            except FxUnavailable as exc:
                evaluation.notes.append(str(exc))
                evaluation.unknown.append({"key": "fx", "label": "Currency conversion",
                                           "reason": str(exc)})
                evaluation.partial_total = None
        else:
            evaluation.partial_total = Money(0.0, self.currency)
        if not evaluation.unknown:
            evaluation.total = evaluation.partial_total
        if evaluation.total is not None and range_from:
            evaluation.range = range_from
        elif evaluation.total is not None:
            evaluation.range = {
                "available": False,
                "reason": "the driving quantities carry a confidence, not an interval; a cost "
                          "range needs an interval on the delay or the fuel figure",
            }
        return evaluation


def avoidable_cost(
    baseline: Optional[FinancialEvaluation],
    option: Optional[FinancialEvaluation],
) -> Dict[str, Any]:
    """Cost of doing nothing against the option's cost, where both are complete.

    Positive avoidable cost means the option is expected to cost less than
    continuing the plan. Anything short of two complete totals in one currency
    is reported as not computable, with the gaps listed -- the number a finance
    team would act on is exactly the one that must not be approximated.
    """
    if baseline is None or option is None:
        return {"available": False, "reason": "one side of the comparison was not priced"}
    if baseline.total is None or option.total is None:
        gaps = [u["label"] for u in baseline.unknown] + [u["label"] for u in option.unknown]
        return {
            "available": False,
            "reason": "unknown components on at least one side: " + ", ".join(sorted(set(gaps))),
            "costOfDoingNothing": None if baseline.total is None else baseline.total.to_dict(),
            "optionCost": None if option.total is None else option.total.to_dict(),
            "partial": {
                "costOfDoingNothing": None if baseline.partial_total is None else baseline.partial_total.to_dict(),
                "optionCost": None if option.partial_total is None else option.partial_total.to_dict(),
                "note": "partial totals omit the unknown components and must not be compared as if complete",
            },
        }
    try:
        difference = baseline.total - option.total
    except CurrencyMismatch as exc:
        return {"available": False, "reason": str(exc)}
    return {
        "available": True,
        "costOfDoingNothing": baseline.total.to_dict(),
        "optionCost": option.total.to_dict(),
        "expectedAvoidableCost": difference.to_dict(),
        "assumption": baseline.assumption or option.assumption,
        "label": "ASSUMPTION" if (baseline.assumption or option.assumption) else None,
    }


__all__ = [
    "CostComponent",
    "FinancialEvaluation",
    "KNOWN",
    "Pricer",
    "STATES",
    "UNKNOWN",
    "ZERO",
    "avoidable_cost",
]
