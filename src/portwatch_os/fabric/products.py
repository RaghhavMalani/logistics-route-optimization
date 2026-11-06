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
_INGEST_REVIEWED = "2026-11-04"


def _review(terms, checked, finding, *, commercial=REQUIRES_REVIEW,
            government=REQUIRES_REVIEW, redistribution=REQUIRES_REVIEW):
    return LicencePolicy(
        commercial_use=commercial,
        government_use=government,
        redistribution=redistribution,
        attribution_required=True,
        evidence=TermsEvidence(
            checked_urls=((terms,) if terms else ()) + tuple(checked),
            reviewed_at=_INGEST_REVIEWED,
            terms_url=terms,
            finding=finding,
        ),
    )


def _ingest_candidates() -> list[Provider]:
    return [
        Provider('gdelt-bigquery', 'GDELT / Google BigQuery', homepage='https://www.gdeltproject.org/', products=(
            ProviderProduct('gdelt-bigquery-gkg', 'GDELT partitioned GKG discovery', (EVENTS,),
                _review('https://www.gdeltproject.org/about.html',
                    ('https://blog.gdeltproject.org/geographic-featureid-to-common-name-crosswalk-may-2018-update/amp/',
                     'https://cloud.google.com/bigquery/docs/best-practices-costs'),
                    'GDELT data may be reused with citation and link; linked articles retain publisher rights. Collect index dates and document links only. BigQuery compute is billed separately: require an explicit billing project, credentials and a daily byte budget, a partition predicate, a dry run and maximum bytes billed. No paid query is enabled by a default.',
                    commercial=ALLOWED, government=ALLOWED, redistribution=ALLOWED),
                endpoint='gdelt-bq.gdeltv2.gkg_partitioned', cost_class=PAID,
                coverage='Indian maritime document discovery; index metadata, not verified events'),)),
        Provider('open-meteo-trials', 'Open-Meteo candidate products', homepage='https://open-meteo.com/', products=tuple(
            ProviderProduct(key, title, (capability,),
                _review('https://open-meteo.com/en/terms', (docs,),
                    'Free API service is restricted to noncommercial use; data is CC BY 4.0 with attribution. Retain provider response availability and forecast valid times separately. These trial snapshots do not change the decision policy.',
                    commercial=PROHIBITED, redistribution=ALLOWED), endpoint=endpoint,
                coverage='13 registered Indian ports; modelled forecasts, not observations')
            for key, title, capability, docs, endpoint in (
                ('open-meteo-marine-extended', 'Marine waves, swell and currents trial', MARINE,
                 'https://open-meteo.com/en/docs/marine-weather-api', 'https://marine-api.open-meteo.com/v1/marine'),
                ('open-meteo-ensemble', 'Weather ensemble member trial', WEATHER,
                 'https://open-meteo.com/en/docs/ensemble-api', 'https://ensemble-api.open-meteo.com/v1/ensemble')))),
        Provider("copernicus-marine", "Copernicus Marine", homepage="https://data.marine.copernicus.eu/", products=(
            ProviderProduct(
                "copernicus-marine-forecast", "Global Ocean wave and current forecasts", (MARINE,),
                _review(
                    "https://marine.copernicus.eu/user-corner/service-commitments-and-licence",
                    (
                        "https://help.marine.copernicus.eu/en/articles/4220332-how-to-register-for-copernicus-marine-service",
                        "https://help.marine.copernicus.eu/en/articles/4444611-citing-copernicus-marine-products-and-services",
                        "https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_WAV_001_027/description",
                        "https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_PHY_001_024/description",
                    ),
                    "Provider guidance permits commercial and other uses with credit and documents service redistribution with attribution and product DOIs. The canonical agreement returned HTTP 403 during this review. Confirm its current version before public redistribution.",
                    commercial=ALLOWED, government=ALLOWED,
                ),
                credential_type=API_KEY, synthetic=True, coverage="Global; trial target Arabian Sea and Bay of Bengal",
                notes="Toolbox account or supported sign-in required. Waves DOI 10.48670/moi-00017 and physics DOI 10.48670/moi-00016. Use forecast issue time for lag when available.",
            ),
        )),
        Provider("incois", "INCOIS", homepage="https://incois.gov.in/", products=(
            ProviderProduct(
                "incois-osf", "Ocean State Forecast", (MARINE,),
                _review(
                    "https://incois.gov.in/site/disclaimer.jsp",
                    ("https://incois.gov.in/oceanservices/osfforecast.jsp",),
                    'Commercial reproduction needs competent-authority permission. The disclaimer says it "is not permitted" without permission. The map shows issue dates and modelled layers. A supported machine-readable OSF feed and its retention rights remain unverified.',
                    commercial=PROHIBITED,
                ),
                synthetic=True, coverage="Indian seas and coast",
                notes="Link to the official forecast pending a qualified feed and reuse permission.",
            ),
        )),
        Provider("imd-rsmc", "IMD RSMC New Delhi", homepage="https://rsmcnewdelhi.imd.gov.in/", products=(
            ProviderProduct(
                "imd-rsmc-cyclone", "Tropical cyclone bulletins", (DISASTER,),
                _review(
                    "https://rsmcnewdelhi.imd.gov.in/copyright-policy.php",
                    ("https://rsmcnewdelhi.imd.gov.in/images/pdf/faq.pdf",),
                    "The RSMC requires permission for partial or full reproduction and acknowledgement when cited. Link to the bulletin and seek written permission before retaining or republishing bulletin content.",
                ),
                coverage="North Indian Ocean", latency_class=HOURLY,
            ),
        )),
        Provider("nho", "National Hydrographic Office", homepage="https://hydrobharat.gov.in/", products=(
            ProviderProduct(
                "nho-navarea-viii", "NAVAREA VIII in-force warnings", (),
                _review(
                    "https://hydrobharat.gov.in/wp-content/uploads/2019/12/23-of-2019.pdf",
                    ("https://hydrobharat.gov.in/navarea-warnings/",
                     "https://hydrobharat.gov.in/documents/d/guest/special-edition-final-26-dec-24"),
                    "The Indian Notices to Mariners edition permits copying and prohibits commercial sale of copies. The live In-Force warning page and special edition describe the product. Confirm the permission for the standalone feed before redistributing full text.",
                ),
                status=AVAILABLE, latency_class=HOURLY, coverage="NAVAREA VIII",
                notes="Existing retained NHO warning context. Use the product issue date and explicit cancellation time rather than inferring expiry from the warning series year.",
            ),
        )),
        Provider("frankfurter", "Frankfurter / European Central Bank", homepage="https://frankfurter.dev/", products=(
            ProviderProduct(
                "frankfurter-ecb-fx", "ECB reference rates via Frankfurter", (),
                _review(
                    "https://frankfurter.dev/license/",
                    ("https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html",
                     "https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html"),
                    "Frankfurter defers to upstream data terms. ECB permits accurate reuse with attribution, requires disclosure of alterations and adds conditions for sold publications. Trial only the unmodified ECB EUR/INR and EUR/USD reference rates, with their original dates.",
                    commercial=ALLOWED, government=ALLOWED, redistribution=ALLOWED,
                ),
                endpoint="https://api.frankfurter.dev/v2/providers/ecb/rates",
                coverage="ECB reference rates; EUR base",
                notes="Daily reference observations. Any INR/USD cross is derived and separate from FRED DEXINUS. This feed does not carry Brent.",
            ),
        )),
        Provider("pib", "Press Information Bureau / Ministry of Ports, Shipping and Waterways", homepage="https://www.pib.gov.in/", products=(
            ProviderProduct(
                "pib-ports-rss", "Official port press-release links via PIB RSS", (EVENTS,),
                _review(
                    "https://shipmin.gov.in/en/footer/copyrightpolicy",
                    ("https://www.pib.gov.in/ViewRss.aspx?lang=1&reg=1",
                     "https://accreditation.pib.gov.in/Documents/CopyrightPolicy.pdf"),
                    "The Ministry permits accurate attributed reproduction of its own website material and excludes third-party material. PIB lists a government-wide RSS feed. The separate accreditation copyright policy does not establish a licence for the press-release feed. Scope the trial to Ministry links and issue dates pending feed-specific terms.",
                ),
                latency_class=HOURLY, coverage="Indian port notices issued by the Ministry",
                endpoint="https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=1",
            ),
        )),
    ]


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
                        commercial_use=REQUIRES_REVIEW,
                        government_use=REQUIRES_REVIEW,
                        redistribution=REQUIRES_REVIEW,
                        attribution_required=True,
                        evidence=TermsEvidence(
                            checked_urls=(
                                "https://aisstream.io/",
                                "https://aisstream.io/documentation",
                                "https://github.com/aisstream/aisstream",
                                "https://github.com/aisstream/aisstream/issues/24",
                            ),
                            reviewed_at=_INGEST_REVIEWED,
                            terms_url=None,
                            finding=(
                                "No terms of use, data licence or acceptable-use "
                                "policy was found on the homepage, the documentation "
                                "or the repository README. The service describes "
                                "itself as \"a free api to stream global AIS data via "
                                "websockets\". A code licence, where one exists, does "
                                "not cover the data. The public-display question in issue 24 "
                                "does not establish permission for retention or public display."
                            ),
                        ),
                        summary=(
                            "The service documents authenticated access. Retention for "
                            "the new trial and any public display need written confirmation."
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
                    policy=_review(
                        "https://www.gdeltproject.org/about.html",
                        (),
                        "The project's terms permit commercial, academic and governmental use and redistribution of GDELT data with a citation and link. Linked publisher content remains subject to publisher rights.",
                        commercial=ALLOWED, government=ALLOWED, redistribution=ALLOWED,
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
                    status=AVAILABLE,
                    latency_class=NEAR_REALTIME,
                    coverage="global",
                    trust=0.95,
                    endpoint="https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
                    notes="Fixed backend provider for the native intelligence globe. Five-minute cache; stale fallback keeps its original fetch timestamp. Live clock only.",
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
                    policy=_review(
                        "https://www.imf.org/en/About/copyright-and-terms",
                        ("https://portwatch.imf.org/",
                         "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/Daily_Ports_Data/FeatureServer/0"),
                        "IMF special statistical data terms permit accurate attributed reuse of qualifying IMF Data. Commercial reuse calls for a permission request. Confirm the Daily Ports layer is in scope, including its upstream rights and automation limits, before enrolling it in the new worker.",
                    ),
                    status=AVAILABLE,
                    latency_class=DAILY,
                    coverage="global ports",
                    trust=0.8,
                    notes="Behind the port registry.",
                ),
            ),
        ),
        Provider(
            provider_id="gods-eye-view",
            name="God's Eye View",
            homepage="https://github.com/bilawalsidhu/gods-eye-view",
            products=(ProviderProduct(
                product_id="gods-eye-view-code",
                name="God's Eye View globe and layer code",
                capabilities=(GEOGRAPHY,),
                policy=LicencePolicy(
                    commercial_use=ALLOWED, government_use=ALLOWED, redistribution=ALLOWED,
                    attribution_required=True,
                    evidence=TermsEvidence(
                        checked_urls=("https://github.com/bilawalsidhu/gods-eye-view/blob/9542a5e58b19277d1f9b6698a46f69fdaa5fc5c1/LICENSE",),
                        reviewed_at="2026-10-06",
                        terms_url="https://github.com/bilawalsidhu/gods-eye-view/blob/9542a5e58b19277d1f9b6698a46f69fdaa5fc5c1/LICENSE",
                        finding="Pinned source code is MIT, copyright 2026 Bilawal Sidhu. Bundled datasets and third-party media have separate terms and are not imported.",
                    ),
                    summary="MIT source code only; preserve copyright and permission notice.",
                ),
                status=AVAILABLE, latency_class=STATIC, coverage="globe renderer; no data coverage implied",
                trust=0.0,
                notes="React uses the upstream application lifecycle, Cesium viewer, earthquake layer and camera feed-type helpers. Software renderer, not a geographic observation source. Full notice served at /gods-eye-view-LICENSE.txt.",
            ),),
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
    ] + _ingest_candidates()


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
