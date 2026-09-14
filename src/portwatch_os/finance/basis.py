"""The cost basis: every rate the financial twin is allowed to price with, and
where each one came from.

There are no default values in this module. A deployment that has configured
nothing has a cost basis that prices nothing, and every financial figure
downstream is ``UNKNOWN`` with the missing primitive named. That is the whole
design: a rupee figure that came from a placeholder is the single most
damaging number this product could show, because it is the one a finance team
would quote.

A rate is one primitive (charter per day, berth hire per GRT-hour, bunker per
tonne) with a value, a currency, a unit, a scope, a validity window, a source
and the evidence for it. Six source types are distinguished and never
conflated:

    CUSTOMER_CONTRACT   the customer's own negotiated terms
    PUBLIC_TARIFF       a published scale of rates, retrieved and cited
    PORT_TARIFF         a port's own schedule supplied through its provider
    MARKET_DATA         an observed market price
    USER_ASSUMPTION     a figure an operator typed in for a scenario
    UNAVAILABLE         nothing; the primitive prices nothing

A public tariff is not a customer's cost. It is what the port publishes; what
a carrier actually pays is a contract this deployment does not hold, and the
label travels with every figure so the two are never confused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.portwatch_os.finance.money import (
    CALL,
    CRANE_HOUR,
    DAY,
    GRT,
    GRT_HOUR,
    MOVE,
    Rate,
    TEU,
    TEU_DAY,
    TONNE,
)
from src.portwatch_os.clock import world_now
from src.portwatch_os.clock import wall_now

CUSTOMER_CONTRACT = "CUSTOMER_CONTRACT"
PUBLIC_TARIFF = "PUBLIC_TARIFF"
PORT_TARIFF = "PORT_TARIFF"
MARKET_DATA = "MARKET_DATA"
USER_ASSUMPTION = "USER_ASSUMPTION"
UNAVAILABLE = "UNAVAILABLE"
SOURCE_TYPES: Tuple[str, ...] = (
    CUSTOMER_CONTRACT, PUBLIC_TARIFF, PORT_TARIFF, MARKET_DATA, USER_ASSUMPTION, UNAVAILABLE,
)


@dataclass(frozen=True)
class Primitive:
    key: str
    label: str
    #: The unit a rate for this primitive is charged per.
    per: str
    description: str


PRIMITIVES: Dict[str, Primitive] = {
    p.key: p for p in [
        Primitive("charter_day", "Vessel charter", DAY, "Time-charter equivalent per day."),
        Primitive("demurrage_day", "Demurrage", DAY, "Per day beyond laytime."),
        Primitive("detention_day", "Detention", DAY, "Per day of equipment held."),
        Primitive("bunker_price_t", "Bunker price", TONNE, "Fuel price per tonne."),
        Primitive("fuel_burn_t_day", "Fuel burn", DAY,
                  "Tonnes per day at service speed. A consumption figure, not a price; "
                  "held here so its provenance travels with the cost it drives."),
        Primitive("berth_hire_grt_hour", "Berth hire", GRT_HOUR, "Per GRT per hour alongside."),
        Primitive("anchorage_grt_hour", "Anchorage", GRT_HOUR, "Per GRT per hour at anchor."),
        Primitive("port_dues_grt", "Port dues", GRT, "Per GRT on each entry."),
        Primitive("pilotage_grt", "Pilotage and towage", GRT, "Per GRT per movement."),
        Primitive("terminal_handling_move", "Terminal handling", MOVE, "Per crane move."),
        Primitive("crane_hour", "Crane hire", CRANE_HOUR, "Per crane per hour."),
        Primitive("yard_storage_teu_day", "Yard storage", TEU_DAY, "Per TEU per day in the yard."),
        Primitive("reefer_storage_teu_day", "Reefer storage", TEU_DAY, "Per powered TEU per day."),
        Primitive("cargo_dwell_teu_day", "Cargo dwell", TEU_DAY, "Carrying cost per TEU per day of dwell."),
        Primitive("missed_connection_teu", "Missed connection", TEU, "Per TEU that misses its connection."),
        Primitive("inventory_carrying_teu_day", "Inventory carrying", TEU_DAY,
                  "Cargo owner's carrying cost per TEU per day late."),
        Primitive("port_call", "Port call", CALL, "Flat charge per call where a tariff states one."),
    ]
}


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class CostRate:
    """One priced primitive, with everything a reader needs to trust or reject it."""

    primitive: str
    value: float
    currency: str
    unit: str
    #: What the rate applies to: a port locode, a vessel class, a company id,
    #: or "*" for any.
    scope: str
    valid_from: Optional[str]
    valid_to: Optional[str]
    #: A human-readable source: the document title, the contract reference,
    #: the operator's name.
    source: str
    source_type: str
    confidence: float
    #: The evidence: URL, retrieval instant, document hash, section, verbatim
    #: text, or for an assumption the actor and purpose.
    provenance: Dict[str, Any] = field(default_factory=dict)
    #: The vessel status a tariff row applies to, where a tariff distinguishes
    #: foreign-going from coastal.
    vessel_status: Optional[str] = None
    #: The vessel type a tariff row applies to (container, tanker, ...).
    vessel_type: Optional[str] = None
    #: Tariff tiers by gross tonnage. A tier with a base amount charges that
    #: amount for the first ``tier_min_grt`` and ``value`` per GRT above it;
    #: without one it charges ``value`` on the whole tonnage.
    tier_min_grt: Optional[float] = None
    tier_max_grt: Optional[float] = None
    tier_base_amount: Optional[float] = None
    label: str = ""

    def __post_init__(self) -> None:
        if self.primitive not in PRIMITIVES:
            raise ValueError(f"{self.primitive!r} is not a cost primitive this basis knows")
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"{self.source_type!r} is not a cost source type")
        expected = PRIMITIVES[self.primitive].per
        if self.unit != expected:
            raise ValueError(
                f"{self.primitive} is charged per {expected}, not per {self.unit}"
            )
        if not self.source:
            raise ValueError("a cost rate must name its source")
        if self.source_type == USER_ASSUMPTION and not self.provenance.get("enteredBy"):
            raise ValueError("an assumption must record who entered it")

    @property
    def rate(self) -> Rate:
        return Rate(self.value, self.currency, self.unit)

    @property
    def is_assumption(self) -> bool:
        return self.source_type == USER_ASSUMPTION

    def valid_at(self, moment: datetime) -> bool:
        start, end = _parse(self.valid_from), _parse(self.valid_to)
        if start is not None and moment < start:
            return False
        if end is not None and moment > end:
            return False
        return True

    def matches(
        self,
        scope: Optional[str],
        vessel_status: Optional[str],
        *,
        vessel_type: Optional[str] = None,
        gt: Optional[float] = None,
    ) -> bool:
        if self.scope not in ("*", scope):
            return False
        if self.vessel_status is not None and vessel_status is not None \
                and self.vessel_status != vessel_status:
            return False
        if self.vessel_type is not None and vessel_type is not None \
                and self.vessel_type != vessel_type:
            return False
        if self.tier_min_grt is not None or self.tier_max_grt is not None:
            if gt is None:
                return False
            if self.tier_min_grt is not None and gt <= self.tier_min_grt and self.tier_min_grt > 0:
                return False
            if self.tier_max_grt is not None and gt > self.tier_max_grt:
                return False
        return True

    def charge_for_grt(self, gt: float):
        """The money a tonnage-based row charges for ``gt`` gross tons."""
        from src.portwatch_os.finance.money import Money

        if self.tier_base_amount is not None and self.tier_min_grt is not None:
            return Money(self.tier_base_amount + self.value * max(0.0, gt - self.tier_min_grt),
                         self.currency)
        return Money(self.value * gt, self.currency)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primitive": self.primitive,
            "label": self.label or PRIMITIVES[self.primitive].label,
            "value": self.value,
            "currency": self.currency,
            "unit": self.unit,
            "scope": self.scope,
            "vesselStatus": self.vessel_status,
            "vesselType": self.vessel_type,
            "tier": (
                None if self.tier_min_grt is None and self.tier_max_grt is None
                else {"minGrt": self.tier_min_grt, "maxGrt": self.tier_max_grt,
                      "baseAmount": self.tier_base_amount}
            ),
            "validFrom": self.valid_from,
            "validTo": self.valid_to,
            "source": self.source,
            "sourceType": self.source_type,
            "isAssumption": self.is_assumption,
            "confidence": self.confidence,
            "provenance": self.provenance,
        }


def assumption(
    primitive: str,
    value: float,
    currency: str,
    *,
    entered_by: str,
    purpose: str = "scenario",
    scope: str = "*",
    note: str = "",
    entered_at: Optional[str] = None,
) -> CostRate:
    """A figure an operator typed in. Labelled ASSUMPTION everywhere it is used."""
    return CostRate(
        primitive=primitive, value=float(value), currency=currency,
        unit=PRIMITIVES[primitive].per, scope=scope, valid_from=None, valid_to=None,
        source=f"entered by {entered_by} for {purpose}", source_type=USER_ASSUMPTION,
        confidence=0.5,
        provenance={
            "enteredBy": entered_by, "purpose": purpose, "note": note,
            # wall-clock: audit stamp of a person entering an assumption
            "enteredAt": entered_at or wall_now().isoformat(timespec="seconds"),
        },
    )


def observation(
    primitive: str,
    value: float,
    currency: str,
    *,
    source: str,
    observed_at: str,
    scope: str = "*",
    confidence: float = 0.8,
    provenance: Optional[Dict[str, Any]] = None,
) -> CostRate:
    """A market observation: a bunker price, say. Sourced and dated."""
    return CostRate(
        primitive=primitive, value=float(value), currency=currency,
        unit=PRIMITIVES[primitive].per, scope=scope, valid_from=observed_at, valid_to=None,
        source=source, source_type=MARKET_DATA, confidence=confidence,
        provenance={"observedAt": observed_at, **(provenance or {})},
    )


@dataclass
class CostSchedule:
    """A set of rates from one document, carrying the document's provenance."""

    schedule_id: str
    title: str
    source_type: str
    scope: str
    rates: List[CostRate] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    #: Whether the terms permit the use this deployment makes of the document.
    #: Recorded, never inferred: "not stated" is the honest default.
    reuse: str = "REQUIRES_REVIEW"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scheduleId": self.schedule_id,
            "title": self.title,
            "sourceType": self.source_type,
            "scope": self.scope,
            "rates": [r.to_dict() for r in self.rates],
            "provenance": self.provenance,
            "reuse": self.reuse,
            "notes": self.notes,
            "validFrom": min((r.valid_from for r in self.rates if r.valid_from), default=None),
            "validTo": max((r.valid_to for r in self.rates if r.valid_to), default=None),
        }


@dataclass(frozen=True)
class Lookup:
    """What the basis found for one primitive, or why it found nothing."""

    primitive: str
    rate: Optional[CostRate]
    reason: str

    @property
    def available(self) -> bool:
        return self.rate is not None


class CostBasis:
    """Every rate a deployment holds. Empty by default, and honest about it."""

    def __init__(self, rates: Iterable[CostRate] = ()) -> None:
        self._rates: List[CostRate] = list(rates)
        self._schedules: List[CostSchedule] = []

    # -- building ----------------------------------------------------------
    def add(self, rate: CostRate) -> None:
        self._rates.append(rate)

    def add_schedule(self, schedule: CostSchedule) -> None:
        self._schedules.append(schedule)
        self._rates.extend(schedule.rates)

    @property
    def rates(self) -> List[CostRate]:
        return list(self._rates)

    @property
    def schedules(self) -> List[CostSchedule]:
        return list(self._schedules)

    # -- reading -----------------------------------------------------------
    def lookup(
        self,
        primitive: str,
        *,
        at: datetime,
        scope: Optional[str] = None,
        vessel_status: Optional[str] = None,
        vessel_type: Optional[str] = None,
        gt: Optional[float] = None,
    ) -> Lookup:
        """The best rate for a primitive, or the reason there is none.

        Preference is by source type -- a customer contract over a tariff over
        market data over an assumption -- and within a type the most specific
        scope wins. A rate outside its validity window is reported as lapsed,
        which is a different and more useful absence than "none configured".
        """
        if primitive not in PRIMITIVES:
            return Lookup(primitive, None, f"{primitive} is not a cost primitive")
        candidates = [
            r for r in self._rates
            if r.primitive == primitive
            and r.matches(scope, vessel_status, vessel_type=vessel_type, gt=gt)
        ]
        if not candidates:
            return Lookup(primitive, None, f"no {PRIMITIVES[primitive].label.lower()} rate is configured"
                          + (f" for {scope}" if scope else ""))
        live = [r for r in candidates if r.valid_at(at)]
        if not live:
            lapsed = candidates[0]
            return Lookup(
                primitive, None,
                f"the only {PRIMITIVES[primitive].label.lower()} rate held ({lapsed.source}) "
                f"is outside its validity ({lapsed.valid_from or 'open'} to "
                f"{lapsed.valid_to or 'open'}); not used",
            )
        order = {CUSTOMER_CONTRACT: 0, PORT_TARIFF: 1, PUBLIC_TARIFF: 2, MARKET_DATA: 3, USER_ASSUMPTION: 4}
        live.sort(key=lambda r: (order.get(r.source_type, 9), 0 if r.scope == scope else 1, -r.confidence))
        return Lookup(primitive, live[0], f"{live[0].source_type} · {live[0].source}")

    def coverage(self, *, at: datetime, scope: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Every primitive and what the basis can do about it right now."""
        out: Dict[str, Dict[str, Any]] = {}
        for key, primitive in PRIMITIVES.items():
            found = self.lookup(key, at=at, scope=scope)
            out[key] = {
                "label": primitive.label,
                "per": primitive.per,
                "available": found.available,
                "sourceType": None if found.rate is None else found.rate.source_type,
                "source": None if found.rate is None else found.rate.source,
                "isAssumption": bool(found.rate and found.rate.is_assumption),
                "reason": found.reason,
            }
        return out

    def to_dict(self, *, at: Optional[datetime] = None) -> Dict[str, Any]:
        moment = at or world_now()
        return {
            "rates": [r.to_dict() for r in self._rates],
            "schedules": [s.to_dict() for s in self._schedules],
            "coverage": self.coverage(at=moment),
            "primitives": [
                {"key": p.key, "label": p.label, "per": p.per, "description": p.description}
                for p in PRIMITIVES.values()
            ],
            "sourceTypes": list(SOURCE_TYPES),
            "note": (
                "No default rate exists. A primitive with no configured rate prices "
                "nothing, and every figure built on it is reported as unknown."
            ),
        }


__all__ = [
    "CUSTOMER_CONTRACT",
    "CostBasis",
    "CostRate",
    "CostSchedule",
    "Lookup",
    "MARKET_DATA",
    "PORT_TARIFF",
    "PRIMITIVES",
    "PUBLIC_TARIFF",
    "Primitive",
    "SOURCE_TYPES",
    "UNAVAILABLE",
    "USER_ASSUMPTION",
    "assumption",
    "observation",
]
