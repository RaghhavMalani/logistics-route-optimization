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
    ProviderDefinition,
    ProviderHealth,
    ProviderLicense,
    RESEARCH,
    Resolution,
    UNAVAILABLE,
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
from src.portwatch_os.fabric.registry import SignalFabric, default_providers, get_fabric

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
    "ProviderDefinition",
    "ProviderHealth",
    "ProviderLicense",
    "RESEARCH",
    "Resolution",
    "SignalFabric",
    "UNAVAILABLE",
    "default_providers",
    "get_fabric",
]
