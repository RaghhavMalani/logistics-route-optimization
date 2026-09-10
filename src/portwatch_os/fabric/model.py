"""The Signal Fabric: where data comes from, and whether it may be used here.

Most of the interesting maritime data in the world is available and *not*
licensed for commercial redistribution. Global Fishing Watch states its APIs are
for non-commercial use. Several excellent public feeds are research-only or
carry attribution obligations. A product that wires those directly into features
does not discover the problem at integration time -- it discovers it during a
customer's procurement review, by which point the dependency is load-bearing.

So licence is a first-class property of a source here, not a note in a README,
and the resolver refuses rather than degrades: asking for AIS in COMMERCIAL mode
returns either a provider that may legally serve it or ``UNAVAILABLE``. There is
deliberately no path that quietly falls back to a research feed because the
commercial one was not configured. A wrong answer about provenance is worse than
no answer, because nobody audits an answer they were given confidently.

The second thing this buys is honesty about freshness. A provider that has not
returned an observation in six hours is not "live", and a product that keeps
calling it live is lying in the most damaging place -- the one the operator
trusts to tell them the picture is current.

Nothing here fetches. This is the registry and the policy; adapters live with
the features that use them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# modes
# --------------------------------------------------------------------------

#: Anything goes that the licence permits for research. Non-commercial sources
#: are eligible.
RESEARCH = "RESEARCH"
#: The public demo. Non-commercial sources are eligible but every payload must
#: carry its attribution, and nothing is presented as a customer's own data.
DEMO = "DEMO"
#: A paying deployment. Only sources whose licence permits commercial use.
COMMERCIAL = "COMMERCIAL"
#: A government deployment. Commercial-use terms plus a redistribution right,
#: because the output is shared between agencies.
GOVERNMENT = "GOVERNMENT"

MODES: Tuple[str, ...] = (RESEARCH, DEMO, COMMERCIAL, GOVERNMENT)

# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------

#: Configured, reachable, and returning observations in this deployment.
AVAILABLE = "AVAILABLE"
#: Supported, with a seam already in the code, but needs a key or an endpoint.
CONFIGURABLE = "CONFIGURABLE"
#: A named intention. No adapter exists yet, and the registry says so rather
#: than implying one.
PLANNED = "PLANNED"
#: Known to this registry and not usable here -- wrong licence for the mode, or
#: a dead endpoint.
UNAVAILABLE = "UNAVAILABLE"

STATUSES: Tuple[str, ...] = (AVAILABLE, CONFIGURABLE, PLANNED, UNAVAILABLE)

# --------------------------------------------------------------------------
# capability
# --------------------------------------------------------------------------

AIS = "ais"
WEATHER = "weather"
MARINE = "marine"
EVENTS = "events"
DISASTER = "disaster"
SEISMIC = "seismic"
FIRE = "fire"
PORT_STATS = "port_stats"
GEOGRAPHY = "geography"
VESSEL_REGISTRY = "vessel_registry"

CAPABILITIES: Tuple[str, ...] = (
    AIS, WEATHER, MARINE, EVENTS, DISASTER, SEISMIC, FIRE, PORT_STATS,
    GEOGRAPHY, VESSEL_REGISTRY,
)

#: Latency bands, coarse on purpose: the difference between 200ms and 400ms
#: does not change a routing decision, and the difference between minutes and
#: days does.
REALTIME = "realtime"
NEAR_REALTIME = "near_realtime"
HOURLY = "hourly"
DAILY = "daily"
STATIC = "static"

LATENCY_CLASSES: Tuple[str, ...] = (REALTIME, NEAR_REALTIME, HOURLY, DAILY, STATIC)

FREE = "free"
FREEMIUM = "freemium"
PAID = "paid"
ENTERPRISE = "enterprise"

COST_CLASSES: Tuple[str, ...] = (FREE, FREEMIUM, PAID, ENTERPRISE)


class FabricError(ValueError):
    """A provider declared something this registry cannot hold."""


@dataclass(frozen=True)
class ProviderLicense:
    """What a source's terms permit. The field that decides eligibility."""

    commercial_use: bool
    redistribution: bool
    attribution_required: bool
    #: The human-readable terms, so a procurement question has an answer that is
    #: not "somebody checked once".
    summary: str = ""
    url: Optional[str] = None

    def permits(self, mode: str) -> Tuple[bool, Optional[str]]:
        """Whether this licence allows a mode, and why not when it does not."""
        if mode in (RESEARCH, DEMO):
            return True, None
        if not self.commercial_use:
            return False, (
                "the licence does not permit commercial use, so this source "
                f"cannot serve a {mode} deployment"
            )
        if mode == GOVERNMENT and not self.redistribution:
            return False, (
                "a government deployment shares output between agencies, which "
                "this licence does not permit"
            )
        return True, None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commercialUse": self.commercial_use,
            "redistribution": self.redistribution,
            "attributionRequired": self.attribution_required,
            "summary": self.summary,
            "url": self.url,
        }


@dataclass
class ProviderHealth:
    """Whether a source is actually answering, and when it last did.

    Freshness is separate from status on purpose: a provider can be correctly
    configured, licensed and reachable, and still be stale because its upstream
    stopped publishing. Calling that "live" is the lie an operator is least able
    to catch.
    """

    last_success: Optional[str] = None
    last_failure: Optional[str] = None
    consecutive_failures: int = 0
    note: str = ""

    def freshness(self, *, now: Optional[datetime] = None,
                  stale_after_hours: float = 6.0) -> str:
        if self.last_success is None:
            return "unknown"
        try:
            seen = datetime.fromisoformat(self.last_success.replace("Z", "+00:00"))
        except ValueError:
            return "unknown"
        moment = now or datetime.now(seen.tzinfo)
        age = (moment - seen).total_seconds() / 3600.0
        if age <= stale_after_hours:
            return "fresh"
        if age <= stale_after_hours * 4:
            return "stale"
        return "cold"

    def to_dict(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        return {
            "lastSuccess": self.last_success,
            "lastFailure": self.last_failure,
            "consecutiveFailures": self.consecutive_failures,
            "freshness": self.freshness(now=now),
            "note": self.note,
        }


@dataclass
class ProviderDefinition:
    """One source of world data, and everything needed to decide about it."""

    provider_id: str
    name: str
    capabilities: Tuple[str, ...]
    license: ProviderLicense
    status: str = PLANNED
    latency_class: str = DAILY
    cost_class: str = FREE
    #: Free-text: "global", "Indian ports", "Indian Ocean". Not a geometry --
    #: a claim to precision this registry does not have.
    coverage: str = "unspecified"
    auth_required: bool = False
    #: 0..1. How much this source's observations have been worth historically.
    #: Assigned, not learned, until the ledger has enough to fit it -- and it is
    #: documented as assigned rather than dressed up as measured.
    trust: float = 0.5
    health: ProviderHealth = field(default_factory=ProviderHealth)
    #: Providers to try, in order, when this one cannot serve.
    fallbacks: Tuple[str, ...] = ()
    #: True when this source produces modelled data rather than observations.
    #: A structural flag rather than a sentence in `notes`, because "is this
    #: real?" is the question a buyer asks last and cares about most, and prose
    #: is not something a caller can check.
    synthetic: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise FabricError(f"{self.status!r} is not a provider status")
        if self.latency_class not in LATENCY_CLASSES:
            raise FabricError(f"{self.latency_class!r} is not a latency class")
        if self.cost_class not in COST_CLASSES:
            raise FabricError(f"{self.cost_class!r} is not a cost class")
        unknown = [c for c in self.capabilities if c not in CAPABILITIES]
        if unknown:
            raise FabricError(
                f"{self.provider_id} declares capabilities this fabric does not "
                f"model: {', '.join(unknown)}"
            )

    def eligible_for(self, mode: str, capability: str) -> Tuple[bool, Optional[str]]:
        """Whether this provider may serve a capability in a mode, and why not."""
        if capability not in self.capabilities:
            return False, f"{self.name} does not provide {capability}"
        if self.status in (PLANNED, UNAVAILABLE):
            return False, (
                f"{self.name} is {self.status.lower()} in this deployment"
            )
        permitted, reason = self.license.permits(mode)
        if not permitted:
            return False, f"{self.name}: {reason}"
        return True, None

    def to_dict(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        return {
            "providerId": self.provider_id,
            "name": self.name,
            "capabilities": list(self.capabilities),
            "license": self.license.to_dict(),
            "status": self.status,
            "latencyClass": self.latency_class,
            "costClass": self.cost_class,
            "coverage": self.coverage,
            "authRequired": self.auth_required,
            "trust": round(self.trust, 3),
            "health": self.health.to_dict(now=now),
            "fallbacks": list(self.fallbacks),
            "synthetic": self.synthetic,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class Resolution:
    """The answer to "what may serve this capability, here?"."""

    capability: str
    mode: str
    provider: Optional[ProviderDefinition]
    #: Every provider considered and why it was not chosen. The audit trail a
    #: procurement review actually wants.
    rejected: Tuple[Tuple[str, str], ...] = ()

    @property
    def available(self) -> bool:
        return self.provider is not None

    @property
    def synthetic(self) -> bool:
        """Whether the resolved source models its data rather than observing it.

        Surfaced on the resolution, not only on the provider, so a caller that
        acts on "AIS is available" cannot miss that what it resolved to is a
        replay. Legally usable and not observed are different questions, and a
        commercial deployment has to be able to tell them apart.
        """
        return bool(self.provider and self.provider.synthetic)

    def to_dict(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "mode": self.mode,
            "status": AVAILABLE if self.available else UNAVAILABLE,
            "synthetic": self.synthetic,
            "provider": None if self.provider is None else self.provider.to_dict(now=now),
            "rejected": [
                {"providerId": pid, "reason": reason} for pid, reason in self.rejected
            ],
        }


__all__ = [
    "AIS",
    "AVAILABLE",
    "CAPABILITIES",
    "COMMERCIAL",
    "CONFIGURABLE",
    "COST_CLASSES",
    "DAILY",
    "DEMO",
    "DISASTER",
    "ENTERPRISE",
    "EVENTS",
    "FIRE",
    "FREE",
    "FREEMIUM",
    "FabricError",
    "GEOGRAPHY",
    "GOVERNMENT",
    "HOURLY",
    "LATENCY_CLASSES",
    "MARINE",
    "MODES",
    "NEAR_REALTIME",
    "PAID",
    "PLANNED",
    "PORT_STATS",
    "ProviderDefinition",
    "ProviderHealth",
    "ProviderLicense",
    "REALTIME",
    "RESEARCH",
    "Resolution",
    "SEISMIC",
    "STATIC",
    "STATUSES",
    "UNAVAILABLE",
    "VESSEL_REGISTRY",
    "WEATHER",
]
