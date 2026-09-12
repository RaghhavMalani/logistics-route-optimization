"""AIS messages, validated and normalised into one canonical shape.

An AIS message is a claim by a transponder about the ship it is bolted to. It
is frequently incomplete -- static data arrives on a different cadence from
positions, and a vessel can report a position for hours before it ever
announces its name -- and it is occasionally wrong, because the fields are
entered by hand. The normaliser's job is to preserve exactly what was said and
nothing more.

That "nothing more" is the rule that shapes this module. A position report
carries an MMSI and a position. It does not carry an IMO, a name or a
destination, and an observation built from it must have ``None`` in those
fields, not a value looked up from somewhere else. Filling them in would make
the observation look more complete than the transponder's claim, and the fusion
layer downstream needs to be able to tell "this message said the name was X"
from "we think the name is X". Those are different confidences with different
evidence, and conflating them at the normaliser is how a wrong merge becomes
impossible to unpick.

Every observation keeps a reference to the raw message it came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

#: The subset of AISStream message classes this deployment consumes. Anything
#: else is counted and dropped -- not an error, just not a claim we model.
POSITION_REPORT = "PositionReport"
STANDARD_CLASS_B = "StandardClassBPositionReport"
SHIP_STATIC_DATA = "ShipStaticData"

CONSUMED_TYPES: Tuple[str, ...] = (POSITION_REPORT, STANDARD_CLASS_B, SHIP_STATIC_DATA)

#: Sentinel values the AIS standard uses for "not available". A transponder
#: that reports 511 for heading is saying it has no heading, and passing that
#: through as a bearing would point the icon due north-and-a-bit for no reason.
HEADING_UNAVAILABLE = 511
COG_UNAVAILABLE = 360.0
SOG_UNAVAILABLE = 102.3
LAT_UNAVAILABLE = 91.0
LON_UNAVAILABLE = 181.0

#: Navigational status codes, per ITU-R M.1371. 15 is "not defined".
NAV_STATUS: Dict[int, str] = {
    0: "under way using engine",
    1: "at anchor",
    2: "not under command",
    3: "restricted manoeuvrability",
    4: "constrained by draught",
    5: "moored",
    6: "aground",
    7: "engaged in fishing",
    8: "under way sailing",
    14: "AIS-SART active",
    15: "not defined",
}


class AisMessageError(ValueError):
    """A message that cannot be turned into an observation, and why."""


@dataclass(frozen=True)
class AisObservation:
    """One claim by one transponder, exactly as made.

    Identity fields are ``None`` unless the message carried them. There is no
    constructor path that fills them in, and the fusion layer is the only place
    that may relate this observation to a named ship.
    """

    provider_id: str
    message_type: str
    mmsi: str
    lat: float
    lon: float
    #: When the transponder reported. ``ingested_at`` is when we received it.
    source_timestamp: datetime
    ingested_at: datetime

    #: Kinematics. ``None`` where the message used its "not available" sentinel.
    sog_knots: Optional[float] = None
    cog_degrees: Optional[float] = None
    heading_degrees: Optional[float] = None
    nav_status: Optional[str] = None

    #: Identity, only as stated. Position reports carry none of these.
    imo: Optional[str] = None
    name: Optional[str] = None
    callsign: Optional[str] = None
    #: Free text typed by a crew member. Never resolved to a port here.
    destination_text: Optional[str] = None
    #: ETA as the transponder encoded it, only when it encoded one.
    eta_text: Optional[str] = None

    #: A pointer to the raw message, not the message itself, so the observation
    #: stays small and the raw envelope stays available for audit.
    raw_ref: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_identity(self) -> bool:
        """Whether this message said anything about who the ship is."""
        return any((self.imo, self.name, self.callsign))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "providerId": self.provider_id,
            "messageType": self.message_type,
            "mmsi": self.mmsi,
            "imo": self.imo,
            "name": self.name,
            "callsign": self.callsign,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "sogKnots": self.sog_knots,
            "cogDegrees": self.cog_degrees,
            "headingDegrees": self.heading_degrees,
            "navStatus": self.nav_status,
            "destinationText": self.destination_text,
            "etaText": self.eta_text,
            "sourceTimestamp": self.source_timestamp.isoformat(),
            "ingestedAt": self.ingested_at.isoformat(),
            "rawRef": self.raw_ref,
            "provenance": self.provenance,
        }


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------


def _mmsi(value: Any) -> str:
    """An MMSI is nine digits. Anything else is not a vessel identifier."""
    text = str(value or "").strip()
    if not text.isdigit() or len(text) != 9:
        raise AisMessageError(f"{value!r} is not a nine-digit MMSI")
    return text


def _coordinate(value: Any, *, sentinel: float, bound: float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise AisMessageError(f"{name} {value!r} is not a number") from None
    if number == sentinel or abs(number) > bound:
        raise AisMessageError(f"{name} {number} is the not-available sentinel or out of range")
    return number


def _optional_number(value: Any, *, sentinel: Optional[float] = None) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if sentinel is not None and number == sentinel:
        return None
    return number


def _optional_text(value: Any) -> Optional[str]:
    """Trim AIS padding. An all-@ or empty field is 'not provided', not a name."""
    if value is None:
        return None
    text = str(value).replace("@", "").strip()
    return text or None


def _optional_imo(value: Any) -> Optional[str]:
    """IMO 0 is the transponder's way of saying 'none'. It is not an IMO."""
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return str(number) if number > 0 else None


def _timestamp(value: Any, *, now: datetime) -> Tuple[datetime, bool]:
    """The transponder's time, and whether we actually had one.

    AISStream's ``time_utc`` is a string with a nanosecond fraction and a
    trailing ``UTC`` word, which ``fromisoformat`` will not read. Where the
    field is absent or unparseable the ingest time stands in and the fact is
    recorded, so the observation reports UNKNOWN freshness rather than LIVE.
    """
    if not value:
        return now, False
    text = str(value).strip()
    for suffix in (" UTC", " +0000 UTC", "+0000 UTC"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    # Trim sub-microsecond precision; Python parses at most six digits.
    if "." in text:
        head, frac = text.split(".", 1)
        frac = "".join(ch for ch in frac if ch.isdigit())[:6]
        text = f"{head}.{frac}" if frac else head
    text = text.replace(" ", "T", 1) if "T" not in text else text
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return now, False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed, True


# --------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------


def normalise(
    envelope: Dict[str, Any],
    *,
    provider_id: str = "aisstream",
    now: Optional[datetime] = None,
    raw_ref: str = "",
) -> AisObservation:
    """Turn one AISStream envelope into a canonical observation.

    Raises :class:`AisMessageError` for anything that is not a usable claim --
    an unconsumed message type, a malformed MMSI, a position at the sentinel --
    so the caller can count and drop rather than reason about garbage.
    """
    moment = now or datetime.now(timezone.utc)
    message_type = str(envelope.get("MessageType") or "")
    if message_type not in CONSUMED_TYPES:
        raise AisMessageError(f"{message_type!r} is not a message type this world consumes")

    meta = envelope.get("MetaData") or {}
    body = (envelope.get("Message") or {}).get(message_type) or {}

    mmsi = _mmsi(meta.get("MMSI") or body.get("UserID"))
    lat = _coordinate(meta.get("latitude", meta.get("Latitude")),
                      sentinel=LAT_UNAVAILABLE, bound=90.0, name="latitude")
    lon = _coordinate(meta.get("longitude", meta.get("Longitude")),
                      sentinel=LON_UNAVAILABLE, bound=180.0, name="longitude")
    source_ts, time_known = _timestamp(meta.get("time_utc"), now=moment)

    provenance: Dict[str, Any] = {
        "source_time_known": time_known,
        "meta_ship_name": _optional_text(meta.get("ShipName")),
    }

    if message_type in (POSITION_REPORT, STANDARD_CLASS_B):
        status_code = body.get("NavigationalStatus")
        nav_status = NAV_STATUS.get(int(status_code)) if isinstance(status_code, int) else None
        heading = _optional_number(body.get("TrueHeading"), sentinel=HEADING_UNAVAILABLE)
        return AisObservation(
            provider_id=provider_id,
            message_type=message_type,
            mmsi=mmsi,
            lat=lat,
            lon=lon,
            source_timestamp=source_ts,
            ingested_at=moment,
            sog_knots=_optional_number(body.get("Sog"), sentinel=SOG_UNAVAILABLE),
            cog_degrees=_optional_number(body.get("Cog"), sentinel=COG_UNAVAILABLE),
            heading_degrees=heading,
            nav_status=nav_status,
            # A position report says nothing about identity. The MetaData
            # ShipName is AISStream's own join against earlier static data,
            # kept in provenance rather than promoted to a claim by this message.
            raw_ref=raw_ref,
            provenance=provenance,
        )

    # ShipStaticData: identity, as the transponder encoded it.
    eta = body.get("Eta")
    eta_text = None
    if isinstance(eta, dict) and any(eta.get(k) for k in ("Month", "Day", "Hour", "Minute")):
        eta_text = (
            f"{int(eta.get('Month') or 0):02d}-{int(eta.get('Day') or 0):02d} "
            f"{int(eta.get('Hour') or 0):02d}:{int(eta.get('Minute') or 0):02d}"
        )
    return AisObservation(
        provider_id=provider_id,
        message_type=message_type,
        mmsi=mmsi,
        lat=lat,
        lon=lon,
        source_timestamp=source_ts,
        ingested_at=moment,
        imo=_optional_imo(body.get("ImoNumber")),
        name=_optional_text(body.get("Name")),
        callsign=_optional_text(body.get("CallSign")),
        destination_text=_optional_text(body.get("Destination")),
        eta_text=eta_text,
        raw_ref=raw_ref,
        provenance=provenance,
    )


__all__ = [
    "AisMessageError",
    "AisObservation",
    "CONSUMED_TYPES",
    "NAV_STATUS",
    "POSITION_REPORT",
    "SHIP_STATIC_DATA",
    "STANDARD_CLASS_B",
    "normalise",
]
