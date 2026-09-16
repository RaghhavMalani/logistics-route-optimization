"""Structural exposure: which Indian cargo classes an event can reach, and how.

The question this answers is the one a ministry desk asks first: "which of
our cargo categories does this chokepoint touch?" The answer is a chain,

    EVENT -> CHOKEPOINT -> LANE -> PORT -> COMMODITY CLASS

or, for an event that acts on a port directly,

    EVENT -> PORT -> COMMODITY CLASS

and every link in it is a catalogue fact with a source: the register says
which straits the event bears on, the lane catalogue says which lanes
transit them and which Indian ports they serve, and the trade catalogue
says which classes each port handles and who says so.

What the answer is not is a number. No tonnage, share or value is attached
to any link, because none is held. The product calls the result STRUCTURAL
EXPOSURE, counts the distinct chains behind each class so a reader can see
how many routes lead there, and stops. A class reached through more chains
is not "more exposed" in any measured sense; it is reached through more
chains, and the payload says exactly that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.portwatch_os.global_eye.exposure import LANES_BY_CHOKEPOINT, TRADE_LANES
from src.portwatch_os.global_eye.ingest import CHOKEPOINT_NAMES
from src.portwatch_os.global_eye.model import GlobalEvent
from src.portwatch_os.trade.catalogue import CLASSES, LABELS, PortClass, port_classes

EXPOSURE_KIND = "STRUCTURAL EXPOSURE"
DISCLAIMER = (
    "Structural exposure only: each link is a catalogued fact with a source. No tonnage, trade value or "
    "share is held by this deployment, none is estimated, and a class reached through more chains is not "
    "thereby more exposed in any measured sense."
)


@dataclass(frozen=True)
class Chain:
    event_id: str
    chokepoint: Optional[str]
    lane_code: Optional[str]
    port_code: str
    commodity_class: str
    sources: Tuple[Dict[str, Any], ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eventId": self.event_id,
            "chokepoint": self.chokepoint,
            "chokepointName": None if self.chokepoint is None else CHOKEPOINT_NAMES.get(self.chokepoint, self.chokepoint),
            "laneCode": self.lane_code,
            "laneName": None if self.lane_code is None else TRADE_LANES[self.lane_code].name,
            "portCode": self.port_code,
            "commodityClass": self.commodity_class,
            "label": LABELS[self.commodity_class],
            "path": [p for p in (
                f"event:{self.event_id}",
                None if self.chokepoint is None else f"chokepoint:{self.chokepoint}",
                None if self.lane_code is None else f"lane:{self.lane_code}",
                f"port:{self.port_code}",
                f"commodity:{self.commodity_class}",
            ) if p],
            "sources": list(self.sources),
        }


def _port_links() -> Dict[str, List[PortClass]]:
    out: Dict[str, List[PortClass]] = {}
    for link in port_classes():
        out.setdefault(link.port_code, []).append(link)
    return out


def chains_for(event: GlobalEvent, *, port_links: Optional[Dict[str, List[PortClass]]] = None) -> List[Chain]:
    """Every structural chain from one event to a commodity class."""
    links = port_links or _port_links()
    chains: List[Chain] = []
    seen: set = set()

    def add(chokepoint: Optional[str], lane_code: Optional[str], port_code: str) -> None:
        for link in links.get(port_code, []):
            marker = (chokepoint, lane_code, port_code, link.commodity_class)
            if marker in seen:
                continue
            seen.add(marker)
            chains.append(Chain(event.event_id, chokepoint, lane_code, port_code, link.commodity_class, link.sources))

    for chokepoint in event.chokepoints:
        for lane_code in LANES_BY_CHOKEPOINT.get(chokepoint, []):
            lane = TRADE_LANES[lane_code]
            for port_code in lane.india_ports:
                add(chokepoint, lane_code, port_code)
    for port_code in getattr(event, "threatened_ports", None) or []:
        add(None, None, port_code)
    return chains


def structural_exposure(
    events: Sequence[GlobalEvent],
    *,
    event_id: Optional[str] = None,
    port_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Structural exposure for every live event, or one, optionally at one port."""
    links = _port_links()
    selected = [e for e in events if event_id is None or e.event_id == event_id]
    rows: List[Dict[str, Any]] = []
    by_class: Dict[str, Dict[str, Any]] = {
        cls: {"commodityClass": cls, "label": LABELS[cls], "chains": 0, "events": set(), "chokepoints": set(),
              "lanes": set(), "ports": set()}
        for cls in CLASSES
    }
    for event in selected:
        chains = chains_for(event, port_links=links)
        if port_code:
            chains = [c for c in chains if c.port_code == port_code]
        for chain in chains:
            rows.append(chain.to_dict())
            bucket = by_class[chain.commodity_class]
            bucket["chains"] += 1
            bucket["events"].add(chain.event_id)
            if chain.chokepoint:
                bucket["chokepoints"].add(chain.chokepoint)
            if chain.lane_code:
                bucket["lanes"].add(chain.lane_code)
            bucket["ports"].add(chain.port_code)
    classes = []
    for cls in CLASSES:
        bucket = by_class[cls]
        classes.append({
            "commodityClass": cls, "label": LABELS[cls], "exposed": bucket["chains"] > 0,
            "chains": bucket["chains"], "events": sorted(bucket["events"]),
            "chokepoints": sorted(bucket["chokepoints"]), "lanes": sorted(bucket["lanes"]),
            "ports": sorted(bucket["ports"]),
            "statement": (
                f"{LABELS[cls]}: reached through {bucket['chains']} chain(s) from {len(bucket['events'])} event(s) "
                f"via {len(bucket['ports'])} port(s)" if bucket["chains"] else f"{LABELS[cls]}: no structural chain from the selected events"
            ),
        })
    return {
        "kind": EXPOSURE_KIND,
        "eventId": event_id,
        "portCode": port_code,
        "events": [e.event_id for e in selected],
        "classes": classes,
        "chains": rows,
        "catalogue": {"ports": sorted(links), "classes": list(CLASSES)},
        "disclaimer": DISCLAIMER,
    }


__all__ = ["Chain", "DISCLAIMER", "EXPOSURE_KIND", "chains_for", "structural_exposure"]
