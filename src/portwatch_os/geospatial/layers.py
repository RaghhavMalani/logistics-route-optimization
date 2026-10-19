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
        from datetime import datetime, timezone
        from urllib.parse import urlparse
        import re
        if self.schemaVersion != "geospatial-layer/1" or self.kind not in ("raster", "vector"):
            raise ValueError("Unsupported layer schema/kind")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", self.layerId) or not re.fullmatch(r"[A-Z0-9]{5}", self.portCode):
            raise ValueError("Invalid layer/port identity")
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
        if self.displayResource is not None and (not isinstance(self.displayResource, dict) or self.displayResource.get("valueKind") != "display"):
            raise ValueError("Display RGB must be labelled display, never analytical")
        times = {}
        for key in ("acquisitionFrom", "acquisitionThrough", "firstAvailableAt"):
            value = getattr(self, key)
            if value is not None:
                try:
                    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except (ValueError, AttributeError) as exc:
                    raise ValueError("Invalid ISO acquisition/availability date") from exc
                if "T" in value and dt.tzinfo is None:
                    raise ValueError("Timestamp requires timezone")
                times[key] = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        if self.acquisitionFrom and self.acquisitionThrough:
            if times["acquisitionFrom"] > times["acquisitionThrough"]:
                raise ValueError("Acquisition interval reversed")
        if not isinstance(self.sourceHashes, list) or any(not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h) for h in self.sourceHashes):
            raise ValueError("sourceHashes must contain lowercase SHA-256 digests")
        if not isinstance(self.assetIds, list) or any(not isinstance(i, str) or not i for i in self.assetIds) or len(set(self.assetIds)) != len(self.assetIds):
            raise ValueError("assetIds must be unique strings")
        for resource in (self.displayResource, self.analyticalResource):
            if resource is None: continue
            if not isinstance(resource, dict) or not isinstance(resource.get("url"), str):
                raise ValueError("Resource requires URL")
            url = urlparse(resource["url"])
            if url.username or url.password or url.fragment or resource["url"].startswith("//"):
                raise ValueError("Credential-bearing or ambiguous resource URL")
            if url.scheme and url.scheme != "https":
                raise ValueError("External resources require HTTPS")
            if not url.scheme and not resource["url"].startswith("/"):
                raise ValueError("Local resources require an absolute URL path")
            if resource.get("expiresAt"):
                try:
                    expiry = datetime.fromisoformat(resource["expiresAt"].replace("Z", "+00:00"))
                    if expiry.tzinfo is None: raise ValueError("Timezone missing")
                except (ValueError, AttributeError) as exc:
                    raise ValueError("Invalid resource expiry") from exc
        if self.analyticalResource and self.analyticalResource.get("valueKind") == "display":
            raise ValueError("Display RGB cannot be an analytical resource")
        return asdict(self)
