"""Provider-neutral remote sensing metadata; credentials never enter resources."""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


@dataclass(frozen=True)
class GeospatialLayer:
    layerId: str
    portCode: str
    kind: str
    bounds: List[float]
    horizontalCrs: str
    verticalDatum: Optional[str] = None
    acquisitionFrom: Optional[str] = None
    acquisitionThrough: Optional[str] = None
    firstAvailableAt: Optional[str] = None
    nativeResolutionM: Optional[float] = None
    resamplingMethod: Optional[str] = None
    noDataDefinition: Optional[str] = None
    sourceProduct: Optional[str] = None
    processingVersion: Optional[str] = None
    sourceHashes: List[str] = field(default_factory=list)
    attribution: Optional[str] = None
    quality: str = "Unknown"
    displayResource: Optional[Dict[str, Any]] = None
    assetIds: List[str] = field(default_factory=list)
    analyticalResource: Optional[Dict[str, Any]] = None
    schemaVersion: str = "geospatial-layer/1"

    def to_dict(self):
        from .geometry import coordinate, QUALITY
        if self.horizontalCrs != "EPSG:4326" or len(self.bounds) != 4:
            raise ValueError("Layer bounds require EPSG:4326 west/south/east/north")
        west, south, east, north = self.bounds
        coordinate(west, south)
        coordinate(east, north)
        if west >= east or south >= north or self.quality not in QUALITY:
            raise ValueError("Invalid bounds or quality")
        if self.nativeResolutionM is not None:
            import math
            if not math.isfinite(self.nativeResolutionM) or self.nativeResolutionM <= 0:
                raise ValueError("Resolution must be positive")
        if self.displayResource and self.displayResource.get("valueKind") != "display":
            raise ValueError("Display RGB must be labelled display, never analytical")
        return asdict(self)
