"""World entity fusion: assertions, identity links, canonical vessels."""

from src.portwatch_os.fusion.destination import (
    COUNTRY,
    DestinationResolution,
    FOREIGN,
    LOCODE,
    NONE,
    resolve_destination,
)
from src.portwatch_os.fusion.engine import (
    DEFAULT_IMO_CLAIMS_BEFORE_MOVE,
    DEFAULT_MMSI_REUSE_WINDOW,
    FusionEngine,
    FusionOutcome,
    get_engine,
    reset_engine,
)
from src.portwatch_os.fusion.model import (
    ATTR_DESTINATION,
    ATTR_IMO,
    ATTR_NAME,
    ATTR_POSITION,
    Candidate,
    CanonicalVessel,
    Conflict,
    EntityAssertion,
    FLEET_ID,
    FLEET_REGISTRY,
    IMO,
    IdentityLink,
    MMSI,
    NAME,
    OBSERVED_AIS,
    SIMULATED_TRAFFIC,
    STRONG,
    WEAK,
)

__all__ = [
    "ATTR_DESTINATION", "ATTR_IMO", "ATTR_NAME", "ATTR_POSITION",
    "COUNTRY", "Candidate", "CanonicalVessel", "Conflict",
    "DEFAULT_IMO_CLAIMS_BEFORE_MOVE", "DEFAULT_MMSI_REUSE_WINDOW",
    "DestinationResolution", "EntityAssertion", "FLEET_ID", "FLEET_REGISTRY", "FOREIGN",
    "FusionEngine", "FusionOutcome", "IMO", "IdentityLink", "LOCODE", "MMSI", "NAME", "NONE",
    "OBSERVED_AIS", "SIMULATED_TRAFFIC", "STRONG", "WEAK",
    "get_engine", "reset_engine", "resolve_destination",
]
