"""The Signal Fabric: licence-aware provider resolution.

Most interesting maritime data is available and not licensed for commercial
redistribution. Licence is therefore a first-class field here, and the resolver
refuses rather than degrades -- see :mod:`~src.portwatch_os.fabric.model` for
why a silent fallback across a licence boundary is the failure this exists to
prevent.
"""

from src.portwatch_os.fabric.model import (
    AVAILABLE,
    CAPABILITIES,
    COMMERCIAL,
    CONFIGURABLE,
    DEMO,
    GOVERNMENT,
    MODES,
    PLANNED,
    ProviderHealth,
    RESEARCH,
    UNAVAILABLE,
)
from src.portwatch_os.fabric.licence import (
    ALLOWED,
    LicencePolicy,
    PROHIBITED,
    REQUIRES_REVIEW,
    TermsEvidence,
    UNKNOWN,
)
from src.portwatch_os.fabric.products import (
    ProductCatalogue,
    ProductResolution,
    Provider,
    ProviderProduct,
    default_catalogue,
)
from src.portwatch_os.fabric.adapters import (
    AIS_UNAVAILABLE,
    Availability,
    BaseAdapter,
    LIVE_AIS,
    SIMULATED_TRAFFIC,
    ais_mode,
    build_adapters,
)
from src.portwatch_os.fabric.observation import (
    DEGRADED,
    OK,
    Observation,
    QualityVerdict,
    REJECTED,
    assess,
    observe,
)
from src.portwatch_os.fabric.registry import SignalFabric, get_fabric

__all__ = [
    "AIS_UNAVAILABLE",
    "AVAILABLE",
    "Availability",
    "BaseAdapter",
    "DEGRADED",
    "LIVE_AIS",
    "OK",
    "Observation",
    "QualityVerdict",
    "REJECTED",
    "SIMULATED_TRAFFIC",
    "ais_mode",
    "assess",
    "build_adapters",
    "observe",
    "CAPABILITIES",
    "COMMERCIAL",
    "CONFIGURABLE",
    "DEMO",
    "GOVERNMENT",
    "MODES",
    "PLANNED",
    "ALLOWED",
    "LicencePolicy",
    "PROHIBITED",
    "ProductCatalogue",
    "ProductResolution",
    "Provider",
    "ProviderHealth",
    "ProviderProduct",
    "REQUIRES_REVIEW",
    "RESEARCH",
    "TermsEvidence",
    "UNKNOWN",
    "SignalFabric",
    "UNAVAILABLE",
    "default_catalogue",
    "get_fabric",
]
