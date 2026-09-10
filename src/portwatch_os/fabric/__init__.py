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
from src.portwatch_os.fabric.registry import SignalFabric, default_providers, get_fabric

__all__ = [
    "AVAILABLE",
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
