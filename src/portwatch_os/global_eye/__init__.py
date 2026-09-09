"""Global Eye: world events, and what they do to Indian maritime operations.

Not news on a map. The chain is

    EVENT -> CHOKEPOINT -> TRADE LANE -> VESSEL -> PORT -> IMPACT -> ACTION

and every hop is computed from something measurable. See
:mod:`~src.portwatch_os.global_eye.exposure` for the graph and
:mod:`~src.portwatch_os.global_eye.calibration` for how a severity heuristic
earns the right to be shown as a probability.
"""

from src.portwatch_os.global_eye.calibration import (
    Calibrator,
    apply_calibration,
    claims_for,
    fit_calibrator,
    raw_score,
)
from src.portwatch_os.global_eye.exposure import (
    TRADE_LANES,
    EventImpact,
    LaneExposure,
    PortExposure,
    TradeLane,
    VesselExposure,
    VesselVoyage,
    aggregate_port_risk,
    build_impact,
    lane_exposure,
    lanes_for_ports,
    port_exposure,
)
from src.portwatch_os.global_eye.ingest import (
    CHOKEPOINT_GEO,
    CHOKEPOINT_NAMES,
    IngestReport,
    RawItem,
    from_news_bundle,
    ingest,
    normalise,
)
from src.portwatch_os.global_eye.model import (
    CATEGORIES,
    CATEGORY_KEYS,
    EventCategory,
    EventSource,
    GlobalEvent,
    classify,
    confidence_from_sources,
    severity_from_text,
    similarity,
)

__all__ = [
    "CATEGORIES", "CATEGORY_KEYS", "CHOKEPOINT_GEO", "CHOKEPOINT_NAMES",
    "TRADE_LANES", "Calibrator", "EventCategory", "EventImpact", "EventSource",
    "GlobalEvent", "IngestReport", "LaneExposure", "PortExposure", "RawItem",
    "TradeLane", "VesselExposure", "VesselVoyage", "aggregate_port_risk",
    "apply_calibration", "build_impact", "claims_for", "classify",
    "confidence_from_sources", "fit_calibrator", "from_news_bundle", "ingest",
    "lane_exposure", "lanes_for_ports", "normalise", "port_exposure",
    "raw_score", "severity_from_text", "similarity",
]
