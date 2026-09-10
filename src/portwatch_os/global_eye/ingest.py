"""Turning a raw feed into Global Eye events.

The input is whatever the connectors produced -- GDELT article rows, GDACS
hazard rows, the exported ``news_bundle.json``. The output is a list of
:class:`GlobalEvent`, deduplicated, corroborated and located.

Deduplication is the part that earns its keep. A single Red Sea incident arrives
as fourteen headlines from nine outlets, and an interface that lists all
fourteen as separate events is worse than useless: it makes a quiet week look
like a crisis and a crisis look like noise. Merging them into one event with
nine sources is also what makes ``source_count`` -- and therefore confidence --
mean something.

Two items merge when they share a category *and* an anchor (chokepoint, region
or port), are within :data:`MERGE_WINDOW_HOURS` of each other, and their
headlines overlap above :data:`MERGE_SIMILARITY`. All four conditions, because
each alone produces obvious false merges: two different strikes in the same week,
or two unrelated stories that both mention "Suez".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.portwatch_os.global_eye.model import (
    CATEGORIES,
    GEO_CHOKEPOINT,
    GEO_EXACT,
    GEO_PORT,
    GEO_UNKNOWN,
    EventSource,
    GlobalEvent,
    classify,
    confidence_from_sources,
    event_id_for,
    iso,
    parse_time,
    severity_from_text,
    similarity,
    tokenise,
)
from src.utils import port_registry
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

#: Two reports further apart than this are separate events even if identical.
MERGE_WINDOW_HOURS = 36.0

#: Headline overlap required to merge. Tuned so wire-service reprints merge and
#: two distinct incidents at the same chokepoint do not.
MERGE_SIMILARITY = 0.34

#: Chokepoint centroids. Same table as the terminal's, kept here because the
#: ingestion layer must be able to place an event without the frontend.
CHOKEPOINT_GEO: Dict[str, Tuple[float, float, str]] = {
    "HORMUZ": (26.6, 56.3, "Persian Gulf approach"),
    "BAB_EL_MANDEB": (12.6, 43.3, "Red Sea / Gulf of Aden"),
    "SUEZ": (30.0, 32.55, "Suez Canal"),
    "MALACCA": (2.5, 101.0, "Strait of Malacca"),
    "PANAMA": (9.08, -79.68, "Panama Canal"),
}

CHOKEPOINT_NAMES: Dict[str, str] = {
    "HORMUZ": "Strait of Hormuz",
    "BAB_EL_MANDEB": "Bab-el-Mandeb",
    "SUEZ": "Suez Canal",
    "MALACCA": "Strait of Malacca",
    "PANAMA": "Panama Canal",
}


@dataclass
class IngestReport:
    """What ingestion did, so the UI never has to guess."""

    raw_items: int = 0
    classified: int = 0
    unclassified: int = 0
    merged_into: int = 0
    located: int = 0
    unlocated: int = 0
    feeds: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rawItems": self.raw_items,
            "classified": self.classified,
            "unclassified": self.unclassified,
            "events": self.merged_into,
            "located": self.located,
            "unlocated": self.unlocated,
            "feeds": self.feeds,
            "notes": self.notes,
        }


@dataclass
class RawItem:
    """One report, normalised out of whatever feed it came from."""

    title: str
    outlet: str
    feed: str
    published_at: Optional[datetime]
    url: Optional[str] = None
    category: Optional[str] = None
    chokepoint: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    region: Optional[str] = None
    severity: Optional[float] = None
    ports: List[str] = field(default_factory=list)
    track: List[Dict[str, Any]] = field(default_factory=list)


def _outlet_of(row: Dict[str, Any]) -> str:
    for key in ("source", "domain", "outlet", "provider"):
        value = row.get(key)
        if value:
            return str(value).strip().lower()
    url = str(row.get("url") or "")
    if "//" in url:
        return url.split("//", 1)[1].split("/", 1)[0].lower()
    return "unattributed"


def normalise(rows: Iterable[Dict[str, Any]], *, feed: str = "unknown") -> List[RawItem]:
    """Normalise feed rows into :class:`RawItem`, classifying as we go."""
    out: List[RawItem] = []
    for row in rows:
        title = str(row.get("title") or row.get("text") or row.get("headline") or "").strip()
        if not title:
            continue

        # A feed that already typed the item is trusted over the text classifier;
        # the classifier is the fallback, not the authority.
        category = _category_from_row(row)
        chokepoint = _chokepoint_from_row(row)
        guessed_category, guessed_choke = classify(title)
        category = category or guessed_category
        chokepoint = chokepoint or guessed_choke

        lat, lon = _coords_from_row(row)
        severity = row.get("severityScore", row.get("severity"))
        try:
            severity = float(severity) if severity is not None else None
        except (TypeError, ValueError):
            severity = None

        ports = [
            str(p).upper()
            for p in (row.get("affectedPorts") or row.get("ports") or [])
            if p
        ]

        out.append(
            RawItem(
                title=title,
                outlet=_outlet_of(row),
                feed=str(row.get("feed") or feed),
                published_at=parse_time(
                    row.get("timestamp") or row.get("date") or row.get("seendate")
                    or row.get("publishedAt")
                ),
                url=row.get("url"),
                category=category,
                chokepoint=chokepoint,
                lat=lat,
                lon=lon,
                region=row.get("region") or row.get("entity"),
                severity=severity,
                ports=ports,
                track=list(row.get("forecastTrack") or row.get("track") or []),
            )
        )
    return out


def _category_from_row(row: Dict[str, Any]) -> Optional[str]:
    raw = row.get("category") or row.get("tag") or row.get("shock_type")
    if not raw:
        return None
    key = str(raw).strip().lower()
    if key in CATEGORIES:
        return key
    # The existing pipeline uses its own shock vocabulary; map it rather than
    # inventing a parallel taxonomy.
    legacy = {
        "chokepoint_closure": "chokepoint_disruption",
        "weather_extreme": "cyclone",
        "conflict": "conflict",
        "strike": "strike",
        "sanctions": "sanctions",
    }
    return legacy.get(key)


def _chokepoint_from_row(row: Dict[str, Any]) -> Optional[str]:
    raw = row.get("chokepoint")
    if not raw:
        return None
    code = str(raw).strip().upper().replace("-", "_")
    return code if code in CHOKEPOINT_GEO else None


def _coords_from_row(row: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    coords = row.get("coordinates") or row.get("location")
    if isinstance(coords, dict):
        try:
            return float(coords["lat"]), float(coords["lon"])
        except (KeyError, TypeError, ValueError):
            return None, None
    try:
        if row.get("lat") is not None and row.get("lon") is not None:
            return float(row["lat"]), float(row["lon"])
    except (TypeError, ValueError):
        pass
    return None, None


def _anchor(item: RawItem) -> str:
    """The place two reports must agree on to be the same event."""
    if item.chokepoint:
        return f"choke:{item.chokepoint}"
    if item.ports:
        return f"port:{sorted(item.ports)[0]}"
    if item.region:
        return f"region:{str(item.region).strip().lower()}"
    return "region:unspecified"


def _locate(item: RawItem) -> Tuple[Optional[float], Optional[float], str, Optional[str]]:
    """Coordinates and the basis for them. Never a guess presented as a geocode."""
    if item.lat is not None and item.lon is not None:
        return item.lat, item.lon, GEO_EXACT, item.region
    if item.chokepoint and item.chokepoint in CHOKEPOINT_GEO:
        lat, lon, region = CHOKEPOINT_GEO[item.chokepoint]
        return lat, lon, GEO_CHOKEPOINT, item.region or region
    for code in item.ports:
        record = port_registry.resolve(code)
        if record:
            return record.lat, record.lon, GEO_PORT, item.region or record.region
    return None, None, GEO_UNKNOWN, item.region


def ingest(
    items: Sequence[RawItem],
    *,
    now: Optional[datetime] = None,
    data_source: str = "",
) -> Tuple[List[GlobalEvent], IngestReport]:
    """Merge normalised reports into corroborated events."""
    now = now or datetime.now(timezone.utc)
    report = IngestReport(raw_items=len(items))
    report.feeds = sorted({item.feed for item in items if item.feed})

    usable = [item for item in items if item.category]
    report.classified = len(usable)
    report.unclassified = len(items) - len(usable)
    if report.unclassified:
        report.notes.append(
            f"{report.unclassified} feed items carried no maritime-relevant classification "
            "and were not turned into events."
        )

    # Group by (category, anchor) first: two events can never merge across
    # either, so similarity only has to be computed inside a group.
    groups: Dict[Tuple[str, str], List[RawItem]] = {}
    for item in usable:
        groups.setdefault((item.category or "", _anchor(item)), []).append(item)

    events: List[GlobalEvent] = []
    for (category, anchor), group in groups.items():
        group.sort(key=lambda i: i.published_at or now)
        clusters: List[List[RawItem]] = []
        for item in group:
            placed = False
            for cluster in clusters:
                head = cluster[0]
                gap = _hours_between(head.published_at, item.published_at)
                if gap is not None and gap > MERGE_WINDOW_HOURS:
                    continue
                if max(similarity(item.title, other.title) for other in cluster) >= MERGE_SIMILARITY:
                    cluster.append(item)
                    placed = True
                    break
            if not placed:
                clusters.append([item])

        for cluster in clusters:
            events.append(_assemble(cluster, category, anchor, now, data_source))

    events.sort(key=lambda e: (-(e.severity * e.confidence), e.event_id))
    report.merged_into = len(events)
    report.located = sum(1 for e in events if e.located)
    report.unlocated = len(events) - report.located
    if report.unlocated:
        report.notes.append(
            f"{report.unlocated} events could not be placed on the chart and are listed "
            "in the register only."
        )
    log.info(
        "Global Eye ingest: %d raw items -> %d events (%d unclassified).",
        report.raw_items, report.merged_into, report.unclassified,
    )
    return events, report


def _assemble(
    cluster: Sequence[RawItem],
    category: str,
    anchor: str,
    now: datetime,
    data_source: str,
) -> GlobalEvent:
    """Fold one cluster of reports into a single event."""
    times = [item.published_at for item in cluster if item.published_at]
    first = min(times) if times else now
    last = max(times) if times else now

    # The longest headline usually carries the most detail; the shortest is
    # usually a truncated aggregator line.
    lead = max(cluster, key=lambda i: len(i.title))

    sources = [
        EventSource(
            outlet=item.outlet,
            url=item.url,
            published_at=iso(item.published_at),
            title=item.title,
            feed=item.feed,
        )
        for item in cluster
    ]
    distinct_outlets = {s.outlet for s in sources if s.outlet}

    # Severity is the strongest claim in the cluster, not the mean: one outlet
    # reporting a closure while eight report delays is a closure story, and
    # averaging it away would hide the case that matters.
    severities = [
        item.severity if item.severity is not None else severity_from_text(item.title, category)
        for item in cluster
    ]
    severity = max(severities)
    confidence = confidence_from_sources(sources, severity=severity)

    lat, lon, basis, region = _locate(lead)
    if lat is None:
        for item in cluster:
            lat, lon, basis, region = _locate(item)
            if lat is not None:
                break

    chokepoints = sorted({item.chokepoint for item in cluster if item.chokepoint})
    ports = sorted({p for item in cluster for p in item.ports})
    track = next((item.track for item in cluster if item.track), [])

    spec = CATEGORIES.get(category)
    horizon = spec.base_persistence_hours if spec else 72.0

    # Two distinct incidents can share a category, an anchor and a day -- two
    # separate Bab-el-Mandeb attacks in one morning, say -- so the cluster's own
    # content has to enter the identity or the second one overwrites the first.
    signature = "~".join(sorted(tokenise(lead.title))[:8]) or lead.title[:40]

    return GlobalEvent(
        event_id=event_id_for(category, f"{anchor}#{signature}", first.strftime("%Y%m%d")),
        title=lead.title,
        category=category,
        region=region or (CHOKEPOINT_NAMES.get(chokepoints[0]) if chokepoints else None),
        lat=lat,
        lon=lon,
        geolocation_basis=basis,
        first_seen=iso(first) or "",
        last_seen=iso(last) or "",
        sources=sources,
        source_count=len(distinct_outlets),
        confidence=confidence,
        severity=severity,
        probability=None,          # calibration fills this, or nothing does
        claim=_claim_for(category),
        horizon_hours=min(horizon, 72.0) if spec and spec.acts_on == "chokepoint" else horizon,
        chokepoints=chokepoints,
        forecast_track=list(track),
        excerpts=[item.title for item in cluster][:6],
        reported_ports=ports,
        report_count=len(cluster),
        data_source=data_source,
    )


def _claim_for(category: str) -> str:
    """The falsifiable statement this event's probability will be about."""
    spec = CATEGORIES.get(category)
    acts_on = spec.acts_on if spec else "area"
    if acts_on == "chokepoint":
        return "material transit disruption at the named chokepoint"
    if acts_on == "port":
        return "measurable throughput loss at the named port"
    return "measurable operational impact in the named area"


def _hours_between(a: Optional[datetime], b: Optional[datetime]) -> Optional[float]:
    if a is None or b is None:
        return None
    return abs((b - a).total_seconds()) / 3600.0


def from_news_bundle(
    bundle: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Tuple[List[GlobalEvent], IngestReport]:
    """Build Global Eye events from the exported ``news_bundle.json``.

    This is the path the shipped product takes: the existing connectors already
    fetch GDELT and GDACS and record their provenance, so Global Eye consumes
    their output rather than opening a second, unaudited network path.
    """
    rows = list(bundle.get("events") or [])
    source = str((bundle.get("summary") or {}).get("dataSource") or "news_bundle.json")
    items = normalise(rows, feed="GDELT/GDACS")
    return ingest(items, now=now, data_source=source)


__all__ = [
    "CHOKEPOINT_GEO",
    "CHOKEPOINT_NAMES",
    "MERGE_SIMILARITY",
    "MERGE_WINDOW_HOURS",
    "IngestReport",
    "RawItem",
    "from_news_bundle",
    "ingest",
    "normalise",
]
