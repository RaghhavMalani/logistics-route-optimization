"""The Global Eye event model.

Global Eye is not news on a map. It is a chain that has to survive being read by
someone who will act on it:

    EVENT -> REGION/CHOKEPOINT -> TRADE LANE -> VESSEL -> PORT -> IMPACT -> ACTION

Every link in that chain is computed from something measurable, and where a link
cannot be computed it is reported as unavailable rather than filled in. The
dataclasses here define what a link is allowed to carry.

The honesty rules this module enforces:

*   A ``GlobalEvent`` carries its sources. ``source_count`` is the number of
    distinct outlets that reported it, and ``confidence`` is derived from that
    count and the source spread, not asserted.
*   ``probability`` is optional and is ``None`` until the calibration layer has
    enough resolved outcomes in that category to produce one. An uncalibrated
    severity is never dressed up as a probability.
*   ``forecast_track`` on a storm-like event is only populated when the feed
    actually carried one. There is no synthesised cone of uncertainty.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# taxonomy
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EventCategory:
    """One kind of disruption, with what it does to maritime operations.

    ``base_persistence_hours`` is how long an event of this kind typically stays
    operationally relevant. It sets the default resolution horizon for the
    outcome claim, so a strike is not scored on a cyclone's clock.
    """

    key: str
    label: str
    #: Coarse grouping for the UI's filter rail.
    group: str
    base_persistence_hours: float
    #: Whether the category typically acts on a chokepoint, a port, or an area.
    acts_on: str
    description: str


CATEGORIES: Dict[str, EventCategory] = {
    c.key: c
    for c in [
        EventCategory("conflict", "Conflict / war", "security", 336.0, "chokepoint",
                      "Armed conflict or naval action affecting a sea area or approach."),
        EventCategory("piracy", "Piracy / attack", "security", 168.0, "chokepoint",
                      "Attacks on merchant shipping in a defined risk area."),
        EventCategory("sanctions", "Sanctions", "policy", 720.0, "area",
                      "Trade restrictions changing which cargoes and flags may move."),
        EventCategory("strike", "Labour action", "operations", 120.0, "port",
                      "Industrial action affecting terminal or hinterland throughput."),
        EventCategory("port_closure", "Port closure", "operations", 72.0, "port",
                      "A port or terminal suspending operations."),
        EventCategory("protest", "Protest / unrest", "operations", 72.0, "port",
                      "Civil disruption around port access or hinterland corridors."),
        EventCategory("earthquake", "Earthquake", "natural", 168.0, "area",
                      "Seismic event with potential quay, crane or channel damage."),
        EventCategory("cyclone", "Cyclone / storm", "natural", 96.0, "area",
                      "Tropical cyclone or severe storm system over a sea area."),
        EventCategory("tsunami", "Tsunami", "natural", 48.0, "area",
                      "Tsunami warning or wave arrival affecting coastal facilities."),
        EventCategory("flood", "Flood", "natural", 120.0, "port",
                      "Flooding affecting terminal operations or hinterland access."),
        EventCategory("canal_restriction", "Canal restriction", "chokepoint", 480.0, "chokepoint",
                      "Transit limits on a canal: draught, slot count or closure."),
        EventCategory("chokepoint_disruption", "Chokepoint disruption", "chokepoint", 240.0,
                      "chokepoint",
                      "Passage through a strait or canal degraded, restricted or avoided."),
        EventCategory("energy_shock", "Energy shock", "market", 336.0, "area",
                      "Bunker or crude price movement changing routing economics."),
        EventCategory("commodity_shock", "Commodity shock", "market", 336.0, "area",
                      "Commodity supply or demand shift changing trade volumes."),
        EventCategory("regulatory", "Regulatory change", "policy", 720.0, "area",
                      "Rule change affecting emissions, routing, crewing or cargo."),
        EventCategory("logistics_disruption", "Logistics disruption", "operations", 168.0, "area",
                      "Rail, road, inland terminal or carrier network disruption."),
        EventCategory("infrastructure", "Infrastructure failure", "operations", 120.0, "port",
                      "Crane, lock, channel or power failure at a facility."),
    ]
}

CATEGORY_KEYS = tuple(CATEGORIES)

#: Ordered so the first matching rule wins. Specific phrases precede generic
#: ones, because "port strike" must classify as a strike rather than as unrest.
CLASSIFIER_RULES: List[Tuple[Tuple[str, ...], str]] = [
    (("tsunami", "tsunami warning"), "tsunami"),
    (("cyclone", "typhoon", "hurricane", "storm surge", "tropical storm",
      "depression intensif"), "cyclone"),
    (("earthquake", "seismic", "magnitude 6", "magnitude 7"), "earthquake"),
    (("flood", "inundat", "waterlogg"), "flood"),
    (("port strike", "dock workers", "dockworker", "labour strike", "labor strike",
      "union walkout", "industrial action"), "strike"),
    (("port closure", "port closed", "suspends operations", "terminal closure",
      "halts operations"), "port_closure"),
    (("protest", "blockade", "unrest", "demonstration", "riot"), "protest"),
    (("sanction", "embargo", "export ban", "import ban", "tariff"), "sanctions"),
    (("piracy", "pirate", "hijack", "boarded by armed", "armed robbery at sea"), "piracy"),
    (("draught restriction", "draft restriction", "transit slots", "canal restriction",
      "canal draft", "reduces daily transits"), "canal_restriction"),
    (("missile", "drone attack", "naval strike", "war", "conflict", "airstrike",
      "attacks on shipping", "houthi"), "conflict"),
    (("crude", "brent", "opec", "bunker price", "lng price", "gas price",
      "fuel price"), "energy_shock"),
    (("grain", "wheat", "iron ore", "coal price", "commodity price",
      "export quota"), "commodity_shock"),
    (("imo 2", "emission rule", "carbon levy", "regulation", "new rules for",
      "compliance deadline"), "regulatory"),
    (("rail disruption", "freight backlog", "inland terminal", "trucking",
      "supply chain disruption", "container shortage"), "logistics_disruption"),
    (("crane failure", "lock failure", "power outage", "channel silt",
      "dredging"), "infrastructure"),
    (("red sea", "bab-el-mandeb", "suez", "hormuz", "malacca", "panama canal",
      "strait"), "chokepoint_disruption"),
]

#: Chokepoint keyed by the phrases that name it. Kept next to the classifier so
#: one pass over a headline resolves both the category and the place.
CHOKEPOINT_RULES: List[Tuple[Tuple[str, ...], str]] = [
    (("strait of hormuz", "hormuz"), "HORMUZ"),
    (("bab-el-mandeb", "bab el mandeb", "red sea", "gulf of aden", "houthi"),
     "BAB_EL_MANDEB"),
    (("suez canal", "suez"), "SUEZ"),
    (("strait of malacca", "malacca", "singapore strait"), "MALACCA"),
    (("panama canal", "gatun"), "PANAMA"),
]


def classify(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(category_key, chokepoint_code)`` for a headline.

    Both may be ``None``. An unclassifiable item is not forced into a category:
    the ingestion layer counts it and the UI reports how many items the feed
    carried that Global Eye could not place.
    """
    lowered = (text or "").lower()
    category: Optional[str] = None
    for phrases, key in CLASSIFIER_RULES:
        if any(phrase in lowered for phrase in phrases):
            category = key
            break
    chokepoint: Optional[str] = None
    for phrases, code in CHOKEPOINT_RULES:
        if any(phrase in lowered for phrase in phrases):
            chokepoint = code
            break
    return category, chokepoint


# --------------------------------------------------------------------------
# events
# --------------------------------------------------------------------------

#: How the event's location was established. Shown wherever a marker is drawn,
#: because a coordinate inferred from a chokepoint name is not a geocode.
GEO_EXACT = "reported"
GEO_CHOKEPOINT = "chokepoint_centroid"
GEO_PORT = "port_location"
GEO_UNKNOWN = "unlocated"


@dataclass
class EventSource:
    """One report of an event. Several of these make one event."""

    outlet: str
    url: Optional[str] = None
    published_at: Optional[str] = None
    title: Optional[str] = None
    #: Feed the item arrived on, e.g. "GDELT" or "GDACS".
    feed: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GlobalEvent:
    """One maritime-relevant disruption, assembled from one or more reports."""

    event_id: str
    title: str
    category: str
    region: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    geolocation_basis: str
    first_seen: str
    last_seen: str
    sources: List[EventSource] = field(default_factory=list)
    #: Distinct outlets. Corroboration, not article count.
    source_count: int = 0
    #: Derived from corroboration and source spread. Never a free parameter.
    confidence: float = 0.0
    #: 0..1. How disruptive this would be if it holds.
    severity: float = 0.0
    #: Calibrated probability of the claim in ``claim`` holding over
    #: ``horizon_hours``. ``None`` until the calibration layer can produce one.
    probability: Optional[float] = None
    #: What the probability, if any, is about.
    claim: Optional[str] = None
    horizon_hours: float = 72.0
    chokepoints: List[str] = field(default_factory=list)
    #: Storm track where the feed carried one. Empty is empty, never invented.
    forecast_track: List[Dict[str, Any]] = field(default_factory=list)
    #: Free-text of the reports, kept for the evidence drawer.
    excerpts: List[str] = field(default_factory=list)
    #: Ports the feed itself named, before exposure is computed.
    reported_ports: List[str] = field(default_factory=list)
    #: How many raw items were merged into this event.
    report_count: int = 1
    #: Set when calibration adjusted the raw probability, with the reason.
    calibration_note: Optional[str] = None
    data_source: str = ""

    @property
    def category_spec(self) -> Optional[EventCategory]:
        return CATEGORIES.get(self.category)

    @property
    def located(self) -> bool:
        return self.lat is not None and self.lon is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eventId": self.event_id,
            "title": self.title,
            "category": self.category,
            "categoryLabel": (self.category_spec.label if self.category_spec else self.category),
            "categoryGroup": (self.category_spec.group if self.category_spec else "other"),
            "region": self.region,
            "coordinates": (
                {"lat": self.lat, "lon": self.lon} if self.located else None
            ),
            "geolocationBasis": self.geolocation_basis,
            "firstSeen": self.first_seen,
            "lastSeen": self.last_seen,
            "sources": [s.to_dict() for s in self.sources],
            "sourceCount": self.source_count,
            "reportCount": self.report_count,
            "confidence": round(self.confidence, 3),
            "severity": round(self.severity, 3),
            "probability": None if self.probability is None else round(self.probability, 3),
            "claim": self.claim,
            "horizonHours": self.horizon_hours,
            "chokepoints": list(self.chokepoints),
            "forecastTrack": list(self.forecast_track),
            "excerpts": self.excerpts[:6],
            "reportedPorts": list(self.reported_ports),
            "calibrationNote": self.calibration_note,
            "dataSource": self.data_source,
        }


# --------------------------------------------------------------------------
# identity and corroboration
# --------------------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9]+")
#: Words too common in maritime headlines to carry identity.
_STOPWORDS = frozenset(
    """a an the of in on at to for and or with from by as is are was were be been
    said says new after over into out up down about more most than that this these
    those it its his her their our your ships ship port ports sea seas news report
    reports amid amid's""".split()
)


def tokenise(text: str) -> List[str]:
    return [w for w in _WORD.findall((text or "").lower()) if w not in _STOPWORDS and len(w) > 2]


def similarity(a: str, b: str) -> float:
    """Jaccard overlap of content words. Cheap, stable and good enough here.

    Headline dedupe does not need embeddings: the same wire story reprinted by
    nine outlets shares most of its nouns, and two genuinely different events in
    the same strait share few. Anything more elaborate would be harder to explain
    to an operator asking why two rows merged.
    """
    left, right = set(tokenise(a)), set(tokenise(b))
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def event_id_for(category: str, anchor: str, day: str) -> str:
    digest = hashlib.sha1(f"{category}|{anchor}|{day}".encode("utf-8")).hexdigest()
    return f"GE-{category[:4].upper()}-{digest[:10]}"


def confidence_from_sources(
    sources: Sequence[EventSource],
    *,
    severity: float = 0.0,
) -> float:
    """Confidence from corroboration breadth, not from how alarming the text is.

    Two independent outlets are worth far more than one outlet filing four
    updates, so the count is over distinct domains. The curve saturates: past
    about six outlets more reporting adds little, because the remaining
    uncertainty is about what the event *does*, not whether it happened.
    """
    outlets = {s.outlet.strip().lower() for s in sources if s.outlet}
    feeds = {s.feed for s in sources if s.feed}
    n = len(outlets)
    if n == 0:
        return 0.15
    breadth = 1.0 - (0.62 ** n)          # 0.38, 0.62, 0.76, 0.85 ...
    # A second independent feed (GDACS confirming a GDELT story) is stronger
    # evidence than a second newspaper.
    multi_feed = 0.12 if len(feeds) > 1 else 0.0
    # Severity does not create confidence, but a trivially minor item that only
    # one outlet carried should not sit at the same confidence as a major one.
    floor = 0.10 + 0.10 * min(1.0, severity)
    return float(max(floor, min(0.97, breadth + multi_feed)))


def severity_from_text(text: str, category: Optional[str]) -> float:
    """A transparent severity heuristic, and it is labelled as one everywhere.

    Word-list scoring is crude. It is used because the alternative -- asking a
    language model to assign a number -- would put an invented figure into an
    operational chain, which this product does not do. The number is coarse, its
    derivation is visible, and the calibration layer is what turns it into
    something with a measured meaning.
    """
    lowered = (text or "").lower()
    score = 0.30
    strong = ("closed", "closure", "suspend", "halt", "blockade", "shut",
              "evacuat", "sink", "sunk", "killed", "destroy", "emergency",
              "state of emergency", "force majeure")
    medium = ("attack", "strike", "restrict", "delay", "disrupt", "damage",
              "warning", "threat", "diverted", "reroute", "backlog")
    light = ("concern", "risk", "monitor", "may", "could", "considering",
             "talks", "plan")
    score += 0.34 * sum(1 for w in strong if w in lowered) ** 0.5
    score += 0.16 * sum(1 for w in medium if w in lowered) ** 0.5
    score -= 0.08 * sum(1 for w in light if w in lowered) ** 0.5
    spec = CATEGORIES.get(category or "")
    if spec and spec.group in ("security", "chokepoint"):
        score += 0.08
    return float(max(0.05, min(0.98, score)))


def parse_time(value: Any) -> Optional[datetime]:
    if value in (None, "", "NaT"):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    # GDELT's compact form, e.g. 20260908T093000Z.
    compact = re.fullmatch(r"(\d{8})T?(\d{6})Z?", text.replace("-", "").replace(":", ""))
    if compact:
        try:
            parsed = datetime.strptime(compact.group(1) + compact.group(2), "%Y%m%d%H%M%S")
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def iso(value: Optional[datetime]) -> Optional[str]:
    return None if value is None else value.astimezone(timezone.utc).isoformat(timespec="seconds")


def decay_factor(last_seen: Optional[str], now: datetime, half_life_hours: float) -> float:
    """How much an event still counts, given how long since it was last reported.

    An event nobody has mentioned for three half-lives is not deleted -- it stays
    in the ledger and its outcome is still scored -- but it stops driving the
    live exposure picture.
    """
    seen = parse_time(last_seen)
    if seen is None or half_life_hours <= 0:
        return 1.0
    age_hours = max(0.0, (now - seen).total_seconds() / 3600.0)
    return float(0.5 ** (age_hours / half_life_hours))


__all__ = [
    "CATEGORIES",
    "CATEGORY_KEYS",
    "CHOKEPOINT_RULES",
    "CLASSIFIER_RULES",
    "GEO_CHOKEPOINT",
    "GEO_EXACT",
    "GEO_PORT",
    "GEO_UNKNOWN",
    "EventCategory",
    "EventSource",
    "GlobalEvent",
    "classify",
    "confidence_from_sources",
    "decay_factor",
    "event_id_for",
    "iso",
    "parse_time",
    "severity_from_text",
    "similarity",
    "tokenise",
]
