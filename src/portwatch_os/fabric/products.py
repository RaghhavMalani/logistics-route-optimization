"""Providers, their products, and the resolver that picks between them.

The unit of licensing is the product. Open-Meteo is one provider with two
products that answer "may we use this commercially" differently, and the
resolver has to be able to choose the paid one for a paying deployment and the
free one for research -- or refuse, when only the free one is configured.

Every product's policy carries the evidence it rests on. The entries below
record what was actually read on 2026-09-12 and what it said, including the
three AISStream pages that said nothing. That last case is the reason the
four-state permission model exists: the previous registry labelled AISStream
non-commercial, and on inspection that was an inference nobody had checked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.portwatch_os.fabric.licence import (
    ALLOWED,
    API_KEY,
    CONTRACT,
    CREDENTIAL_TYPES,
    LicencePolicy,
    NO_CREDENTIAL,
    PROHIBITED,
    REQUIRES_REVIEW,
    TermsEvidence,
    UNKNOWN,
)
from src.portwatch_os.fabric.model import (
    AIS,
    AVAILABLE,
    CAPABILITIES,
    CONFIGURABLE,
    COST_CLASSES,
    DAILY,
    DISASTER,
    ENTERPRISE,
    EVENTS,
    FIRE,
    FREE,
    FREEMIUM,
    GEOGRAPHY,
    HOURLY,
    LATENCY_CLASSES,
    MARINE,
    MODES,
    NEAR_REALTIME,
    PAID,
    PLANNED,
    PORT_STATS,
    ProviderHealth,
    REALTIME,
    SEISMIC,
    STATIC,
    STATUSES,
    UNAVAILABLE,
    VESSEL_REGISTRY,
    WEATHER,
)


class ProductError(ValueError):
    """A product was declared that this registry cannot hold."""


@dataclass
class ProviderProduct:
    """One thing a provider sells or gives away, with its own terms."""

    product_id: str
    name: str
    capabilities: Tuple[str, ...]
    policy: LicencePolicy
    status: str = PLANNED
    credential_type: str = NO_CREDENTIAL
    cost_class: str = FREE
    latency_class: str = DAILY
    coverage: str = "unspecified"
    #: The endpoint family this product serves. Informational; adapters own
    #: the actual URLs.
    endpoint: Optional[str] = None
    #: 0..1, assigned rather than learned until the ledger can fit it.
    trust: float = 0.5
    health: ProviderHealth = field(default_factory=ProviderHealth)
    #: True when the product models its data rather than observing it.
    synthetic: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ProductError(f"{self.status!r} is not a product status")
        if self.credential_type not in CREDENTIAL_TYPES:
            raise ProductError(f"{self.credential_type!r} is not a credential type")
        if self.cost_class not in COST_CLASSES:
            raise ProductError(f"{self.cost_class!r} is not a cost class")
        if self.latency_class not in LATENCY_CLASSES:
            raise ProductError(f"{self.latency_class!r} is not a latency class")
        unknown = [c for c in self.capabilities if c not in CAPABILITIES]
        if unknown:
            raise ProductError(
                f"{self.product_id} declares capabilities this fabric does not "
                f"model: {', '.join(unknown)}"
            )

    def eligible_for(self, mode: str, capability: str) -> Tuple[bool, Optional[str]]:
        if capability not in self.capabilities:
            return False, f"{self.name} does not provide {capability}"
        if self.status in (PLANNED, UNAVAILABLE):
            return False, f"{self.name} is {self.status.lower()} in this deployment"
        permitted, reason = self.policy.permits(mode)
        if not permitted:
            return False, f"{self.name}: {reason}"
        return True, None

    def to_dict(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        return {
            "productId": self.product_id,
            "name": self.name,
            "capabilities": list(self.capabilities),
            "policy": self.policy.to_dict(),
            "status": self.status,
            "credentialType": self.credential_type,
            "costClass": self.cost_class,
            "latencyClass": self.latency_class,
            "coverage": self.coverage,
            "endpoint": self.endpoint,
            "trust": round(self.trust, 3),
            "health": self.health.to_dict(now=now),
            "synthetic": self.synthetic,
            "notes": self.notes,
        }


@dataclass
class Provider:
    """An organisation, and the products it offers. Licences live on products."""

    provider_id: str
    name: str
    products: Tuple[ProviderProduct, ...]
    homepage: Optional[str] = None

    def product(self, product_id: str) -> Optional[ProviderProduct]:
        return next((p for p in self.products if p.product_id == product_id), None)

    def to_dict(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        return {
            "providerId": self.provider_id,
            "name": self.name,
            "homepage": self.homepage,
            "products": [p.to_dict(now=now) for p in self.products],
        }


@dataclass(frozen=True)
class ProductResolution:
    """What may serve a capability in a mode, and everything passed over."""

    capability: str
    mode: str
    product: Optional[ProviderProduct]
    provider: Optional[Provider]
    rejected: Tuple[Tuple[str, str], ...] = ()

    @property
    def available(self) -> bool:
        return self.product is not None

    @property
    def synthetic(self) -> bool:
        return bool(self.product and self.product.synthetic)

    def to_dict(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "mode": self.mode,
            "status": AVAILABLE if self.available else UNAVAILABLE,
            "synthetic": self.synthetic,
            "provider": None if self.provider is None else {
                "providerId": self.provider.provider_id, "name": self.provider.name,
            },
            "product": None if self.product is None else self.product.to_dict(now=now),
            "rejected": [
                {"productId": pid, "reason": reason} for pid, reason in self.rejected
            ],
        }


# --------------------------------------------------------------------------
# the catalogue, with what was read
# --------------------------------------------------------------------------

_REVIEWED = "2026-09-12"


def default_catalogue() -> List[Provider]:
    """Every provider this deployment knows, at its verified terms."""
    return [
        # ------------------------------------------------------ Open-Meteo --
        Provider(
            provider_id="open-meteo",
            name="Open-Meteo",
            homepage="https://open-meteo.com/",
            products=(
                ProviderProduct(
                    product_id="open-meteo-free",
                    name="Open-Meteo free API",
                    capabilities=(WEATHER, MARINE),
                    policy=LicencePolicy(
                        commercial_use=PROHIBITED,
                        government_use=REQUIRES_REVIEW,
                        redistribution=ALLOWED,
                        attribution_required=True,
                        data_licence="CC-BY 4.0",
                        evidence=TermsEvidence(
                            checked_urls=("https://open-meteo.com/en/terms",),
                            reviewed_at=_REVIEWED,
                            terms_url="https://open-meteo.com/en/terms",
                            finding=(
                                '"You may only use the free API services for '
                                'non-commercial purposes." Data: "provided under '
                                'the terms of the CC-BY 4.0 licence." Rate limit: '
                                "under 10,000 calls/day, 5,000/hour, 600/minute."
                            ),
                        ),
                        summary=(
                            "Free tier is non-commercial. The data itself is CC-BY "
                            "4.0, so redistribution with attribution is permitted; "
                            "it is the *service* that may not be used commercially."
                        ),
                    ),
                    status=AVAILABLE,
                    credential_type=NO_CREDENTIAL,
                    cost_class=FREE,
                    latency_class=HOURLY,
                    coverage="global; marine variables for global oceans",
                    endpoint="api.open-meteo.com, marine-api.open-meteo.com",
                    trust=0.78,
                    notes=(
                        "The forecast the weather layer and twin already read. "
                        "Government use is not addressed by the published terms."
                    ),
                ),
                ProviderProduct(
                    product_id="open-meteo-customer",
                    name="Open-Meteo API subscription",
                    capabilities=(WEATHER, MARINE),
                    policy=LicencePolicy(
                        commercial_use=ALLOWED,
                        government_use=ALLOWED,
                        redistribution=ALLOWED,
                        attribution_required=True,
                        data_licence="CC-BY 4.0",
                        evidence=TermsEvidence(
                            checked_urls=("https://open-meteo.com/en/terms",),
                            reviewed_at=_REVIEWED,
                            terms_url="https://open-meteo.com/en/terms",
                            finding=(
                                '"If you plan to use our service for commercial '
                                'purposes or require additional API calls, we kindly '
                                'request you to consider subscribing to our API '
                                'plans." Tiers named: Standard, Professional, '
                                "Enterprise."
                            ),
                        ),
                        summary="Paid plans permit commercial use of the same data.",
                    ),
                    status=CONFIGURABLE,
                    credential_type=API_KEY,
                    cost_class=PAID,
                    latency_class=HOURLY,
                    coverage="global",
                    endpoint="customer-api.open-meteo.com",
                    trust=0.78,
                    notes="Needs OPEN_METEO_API_KEY. Same adapter, different host.",
                ),
            ),
        ),

        # ------------------------------------------------------- AISStream --
        Provider(
            provider_id="aisstream",
            name="AISStream",
            homepage="https://aisstream.io/",
            products=(
                ProviderProduct(
                    product_id="aisstream-websocket",
                    name="AISStream websocket",
                    capabilities=(AIS,),
                    policy=LicencePolicy(
                        # Three pages checked. None carries terms for the data
                        # service. The previous registry said "non-commercial";
                        # that was an inference and it is withdrawn.
                        commercial_use=REQUIRES_REVIEW,
                        government_use=REQUIRES_REVIEW,
                        redistribution=REQUIRES_REVIEW,
                        attribution_required=True,
                        evidence=TermsEvidence(
                            checked_urls=(
                                "https://aisstream.io/",
                                "https://aisstream.io/documentation",
                                "https://github.com/aisstream/aisstream",
                            ),
                            reviewed_at=_REVIEWED,
                            terms_url=None,
                            finding=(
                                "No terms of use, data licence or acceptable-use "
                                "policy was found on the homepage, the documentation "
                                "or the repository README. The service describes "
                                "itself as \"a free api to stream global AIS data via "
                                "websockets\". A code licence, where one exists, does "
                                "not cover the data. Commercial standing is therefore "
                                "unverified, not prohibited."
                            ),
                        ),
                        summary=(
                            "Terms not published. Usable for research and demo; a "
                            "paying deployment needs written confirmation from the "
                            "operator before it may rely on this."
                        ),
                    ),
                    status=CONFIGURABLE,
                    credential_type=API_KEY,
                    cost_class=FREE,
                    latency_class=REALTIME,
                    coverage="global, varying with receiver density",
                    endpoint="wss://stream.aisstream.io/v0/stream",
                    trust=0.6,
                    notes="Needs AISSTREAM_API_KEY.",
                ),
            ),
        ),

        # ------------------------------------------------------ AIS replay --
        Provider(
            provider_id="portwatch",
            name="PortWatch",
            products=(
                ProviderProduct(
                    product_id="ais-replay",
                    name="Deterministic AIS replay",
                    capabilities=(AIS,),
                    policy=LicencePolicy(
                        commercial_use=ALLOWED,
                        government_use=ALLOWED,
                        redistribution=ALLOWED,
                        attribution_required=False,
                        evidence=TermsEvidence(
                            checked_urls=(),
                            reviewed_at=_REVIEWED,
                            finding="Generated by this project. No third-party terms apply.",
                        ),
                        summary="Simulated positions, labelled as such on every surface.",
                    ),
                    status=AVAILABLE,
                    latency_class=STATIC,
                    coverage="Indian Ocean traffic model",
                    trust=0.35,
                    synthetic=True,
                    notes=(
                        "Not observed traffic and never presented as such. Exists so "
                        "the product is demonstrable without an AIS licence."
                    ),
                ),
            ),
        ),

        # --------------------------------------------- Global Fishing Watch --
        Provider(
            provider_id="global-fishing-watch",
            name="Global Fishing Watch",
            homepage="https://globalfishingwatch.org/",
            products=(
                ProviderProduct(
                    product_id="gfw-api",
                    name="Global Fishing Watch APIs",
                    capabilities=(VESSEL_REGISTRY,),
                    policy=LicencePolicy(
                        commercial_use=PROHIBITED,
                        # The page says governments use it; it does not state the
                        # terms under which they do. A person has to ask.
                        government_use=REQUIRES_REVIEW,
                        redistribution=REQUIRES_REVIEW,
                        attribution_required=True,
                        evidence=TermsEvidence(
                            checked_urls=(
                                "https://globalfishingwatch.org/our-apis/documentation/",
                            ),
                            reviewed_at=_REVIEWED,
                            terms_url="https://globalfishingwatch.org/our-apis/documentation/",
                            finding=(
                                '"Global Fishing Watch APIs are only available for '
                                'non-commercial purposes." The page notes use by '
                                '"researchers, governments and technology companies" '
                                "without stating the government terms."
                            ),
                        ),
                        summary="Non-commercial only, by published terms.",
                    ),
                    status=PLANNED,
                    credential_type=API_KEY,
                    latency_class=DAILY,
                    coverage="global",
                    trust=0.85,
                    notes="No adapter exists. Identity across 40+ registries.",
                ),
            ),
        ),

        # ----------------------------------------------------- commercial --
        Provider(
            provider_id="spire",
            name="Spire Maritime",
            homepage="https://spire.com/maritime/",
            products=(
                ProviderProduct(
                    product_id="spire-ais",
                    name="Spire AIS",
                    capabilities=(AIS, VESSEL_REGISTRY),
                    policy=LicencePolicy(
                        commercial_use=ALLOWED,
                        government_use=ALLOWED,
                        redistribution=REQUIRES_REVIEW,
                        attribution_required=False,
                        evidence=TermsEvidence(
                            checked_urls=("https://spire.com/maritime/",),
                            reviewed_at=_REVIEWED,
                            finding=(
                                "Commercial satellite and terrestrial AIS sold under "
                                "contract. Redistribution rights are per-agreement and "
                                "not published; a contract would specify them."
                            ),
                        ),
                        summary="Commercial under contract; redistribution per agreement.",
                    ),
                    status=PLANNED,
                    credential_type=CONTRACT,
                    cost_class=ENTERPRISE,
                    latency_class=NEAR_REALTIME,
                    coverage="global",
                    trust=0.9,
                    notes="No adapter exists. Named so the commercial path is visible.",
                ),
            ),
        ),
        Provider(
            provider_id="kpler",
            name="Kpler",
            homepage="https://www.kpler.com/",
            products=(
                ProviderProduct(
                    product_id="kpler-maritime",
                    name="Kpler maritime APIs",
                    capabilities=(AIS, PORT_STATS, VESSEL_REGISTRY),
                    policy=LicencePolicy(
                        commercial_use=ALLOWED,
                        government_use=ALLOWED,
                        redistribution=REQUIRES_REVIEW,
                        attribution_required=False,
                        evidence=TermsEvidence(
                            checked_urls=("https://www.kpler.com/",),
                            reviewed_at=_REVIEWED,
                            finding=(
                                "Commercial vessel tracking under contract. "
                                "Redistribution terms are per-agreement."
                            ),
                        ),
                        summary="Commercial under contract.",
                    ),
                    status=PLANNED,
                    credential_type=CONTRACT,
                    cost_class=ENTERPRISE,
                    latency_class=NEAR_REALTIME,
                    coverage="global",
                    trust=0.9,
                    notes="No adapter exists.",
                ),
            ),
        ),

        # ----------------------------------------------------- open feeds --
        Provider(
            provider_id="gdelt",
            name="GDELT",
            homepage="https://www.gdeltproject.org/",
            products=(
                ProviderProduct(
                    product_id="gdelt-events",
                    name="GDELT event feed",
                    capabilities=(EVENTS,),
                    policy=_open(
                        "https://www.gdeltproject.org/about.html",
                        "Open data project; datasets are freely available with attribution.",
                    ),
                    status=AVAILABLE,
                    latency_class=NEAR_REALTIME,
                    coverage="global news",
                    trust=0.55,
                    notes="The feed Global Eye ingests.",
                ),
            ),
        ),
        Provider(
            provider_id="gdacs",
            name="GDACS",
            products=(
                ProviderProduct(
                    product_id="gdacs-alerts",
                    name="GDACS disaster alerts",
                    capabilities=(DISASTER,),
                    policy=_open("https://www.gdacs.org/", "Public disaster alerting service."),
                    status=CONFIGURABLE,
                    latency_class=HOURLY,
                    coverage="global disasters",
                    trust=0.75,
                    notes="No adapter wired yet.",
                ),
            ),
        ),
        Provider(
            provider_id="usgs",
            name="USGS",
            products=(
                ProviderProduct(
                    product_id="usgs-earthquakes",
                    name="USGS earthquake feed",
                    capabilities=(SEISMIC,),
                    policy=_open(
                        "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits",
                        "US government work; public domain.",
                    ),
                    status=CONFIGURABLE,
                    latency_class=NEAR_REALTIME,
                    coverage="global",
                    trust=0.95,
                    notes="No adapter wired yet.",
                ),
            ),
        ),
        Provider(
            provider_id="nasa-firms",
            name="NASA FIRMS",
            products=(
                ProviderProduct(
                    product_id="firms-active-fire",
                    name="FIRMS active fire",
                    capabilities=(FIRE,),
                    policy=_open("https://firms.modaps.eosdis.nasa.gov/", "NASA open data."),
                    status=PLANNED,
                    credential_type=API_KEY,
                    latency_class=NEAR_REALTIME,
                    coverage="global",
                    trust=0.85,
                    notes="No adapter exists.",
                ),
            ),
        ),
        Provider(
            provider_id="imf-portwatch",
            name="IMF PortWatch",
            products=(
                ProviderProduct(
                    product_id="imf-portwatch-data",
                    name="IMF PortWatch port statistics",
                    capabilities=(PORT_STATS,),
                    policy=_open("https://portwatch.imf.org/", "Open data with attribution."),
                    status=AVAILABLE,
                    latency_class=DAILY,
                    coverage="global ports",
                    trust=0.8,
                    notes="Behind the port registry.",
                ),
            ),
        ),
        Provider(
            provider_id="natural-earth",
            name="Natural Earth",
            products=(
                ProviderProduct(
                    product_id="natural-earth-vectors",
                    name="Natural Earth vectors",
                    capabilities=(GEOGRAPHY,),
                    policy=LicencePolicy(
                        commercial_use=ALLOWED,
                        government_use=ALLOWED,
                        redistribution=ALLOWED,
                        attribution_required=False,
                        evidence=TermsEvidence(
                            checked_urls=("https://www.naturalearthdata.com/about/terms-of-use/",),
                            reviewed_at=_REVIEWED,
                            terms_url="https://www.naturalearthdata.com/about/terms-of-use/",
                            finding="Public domain.",
                        ),
                        summary="Public domain.",
                    ),
                    status=AVAILABLE,
                    latency_class=STATIC,
                    coverage="global",
                    trust=1.0,
                    notes="Coastlines and borders the chart draws.",
                ),
            ),
        ),
    ]


def _open(url: str, finding: str) -> LicencePolicy:
    return LicencePolicy(
        commercial_use=ALLOWED,
        government_use=ALLOWED,
        redistribution=ALLOWED,
        attribution_required=True,
        evidence=TermsEvidence(
            checked_urls=(url,), reviewed_at=_REVIEWED, terms_url=url, finding=finding,
        ),
        summary="Open data with attribution.",
    )


# --------------------------------------------------------------------------
# the resolver
# --------------------------------------------------------------------------


class ProductCatalogue:
    """Providers and products, and the mode-aware resolver over them."""

    def __init__(
        self,
        providers: Optional[Sequence[Provider]] = None,
        *,
        mode: str = "COMMERCIAL",
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"{mode!r} is not a deployment mode")
        self.mode = mode
        self._providers: Dict[str, Provider] = {
            p.provider_id: p
            for p in (providers if providers is not None else default_catalogue())
        }

    def providers(self) -> List[Provider]:
        return sorted(self._providers.values(), key=lambda p: p.provider_id)

    def products(self, *, capability: Optional[str] = None) -> List[Tuple[Provider, ProviderProduct]]:
        rows = [
            (provider, product)
            for provider in self.providers()
            for product in provider.products
            if capability is None or capability in product.capabilities
        ]
        return sorted(rows, key=lambda r: r[1].product_id)

    def product(self, product_id: str) -> Optional[Tuple[Provider, ProviderProduct]]:
        for provider in self._providers.values():
            found = provider.product(product_id)
            if found is not None:
                return provider, found
        return None

    def resolve(
        self,
        capability: str,
        *,
        mode: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> ProductResolution:
        """The best legally usable product, or UNAVAILABLE with every reason.

        A product whose permission is REQUIRES_REVIEW or UNKNOWN is rejected
        for COMMERCIAL and GOVERNMENT exactly as a PROHIBITED one is. That is
        the property this registry exists to hold: a paying deployment cannot be
        built on a source whose licence is a guess.
        """
        active = mode or self.mode
        if active not in MODES:
            raise ValueError(f"{active!r} is not a deployment mode")

        eligible: List[Tuple[Provider, ProviderProduct]] = []
        rejected: List[Tuple[str, str]] = []
        for provider, product in self.products(capability=capability):
            ok, reason = product.eligible_for(active, capability)
            if ok:
                eligible.append((provider, product))
            elif reason:
                rejected.append((product.product_id, reason))

        if not eligible:
            return ProductResolution(
                capability=capability, mode=active, product=None, provider=None,
                rejected=tuple(rejected),
            )

        freshness_rank = {"fresh": 0, "unknown": 1, "stale": 2, "cold": 3}
        cost_rank = {FREE: 0, FREEMIUM: 1, PAID: 2, ENTERPRISE: 3}
        eligible.sort(
            key=lambda pair: (
                -pair[1].trust,
                freshness_rank.get(pair[1].health.freshness(now=now), 1),
                cost_rank.get(pair[1].cost_class, 9),
                pair[1].product_id,
            )
        )
        provider, chosen = eligible[0]
        for _, other in eligible[1:]:
            rejected.append((other.product_id, f"{chosen.name} ranked higher"))
        return ProductResolution(
            capability=capability, mode=active, product=chosen, provider=provider,
            rejected=tuple(rejected),
        )

    def report(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "providers": [p.to_dict(now=now) for p in self.providers()],
            "resolution": {
                capability: self.resolve(capability, now=now).to_dict(now=now)
                for capability in CAPABILITIES
            },
        }


__all__ = [
    "ProductCatalogue",
    "ProductError",
    "ProductResolution",
    "Provider",
    "ProviderProduct",
    "default_catalogue",
]
