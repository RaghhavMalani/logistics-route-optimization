"""Canonical Indian port registry -- one source of truth for the whole system.

Before this module the repository carried three separate port tables (the
modelling registry in :mod:`src.utils.config`, a ``PORT_META`` dict in the ports
API route and a ``PORTS``/``PORT_RISKS`` table in a backend service). They
disagreed on codes (INHAL vs INCCU), on which ports existed at all, and one of
them shipped hardcoded congestion numbers. Everything now resolves through here.

Each entry ties together the four identifiers a maritime system needs:

    model_id     the id used inside the pipeline (panel, forecast, regimes)
    locode       UN/LOCODE, the identifier a port authority actually uses
    portwatch_id the IMF PortWatch satellite-AIS feed id
    display name / short name

plus geography (lat/lon, coast) and the static capacity attributes the TFT
consumes. Lookup is tolerant: any of the identifiers, the short name or the
display name resolves to the same record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class PortRecord:
    """One physical port, addressable by any of its identifiers."""

    model_id: str
    locode: str
    name: str
    short: str
    authority: str
    lat: float
    lon: float
    coast: str            # west | east | south
    region: str           # modelling region used by the static feature frame
    capacity: float       # relative daily capacity, 0..1
    berth_count: int
    connectivity: float   # hinterland road/rail connectivity, 0..1
    portwatch_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "modelId": self.model_id,
            "code": self.locode,
            "name": self.name,
            "short": self.short,
            "authority": self.authority,
            "location": {"lat": self.lat, "lon": self.lon},
            "coast": self.coast,
            "capacityIndex": self.capacity,
            "berthCount": self.berth_count,
            "connectivityScore": self.connectivity,
        }


# Capacity/berth/connectivity mirror src.utils.config.PORTS so the static
# feature frame the TFT consumes stays identical; they are relative planning
# figures for the prototype, not official port-authority statistics.
PORTS: List[PortRecord] = [
    PortRecord("DEENDAYAL", "INIXY", "Deendayal (Kandla)", "KDL",
               "Deendayal Port Authority", 23.02, 70.22, "west", "West",
               1.00, 14, 0.84, ("port540",)),
    PortRecord("MUNDRA", "INMUN", "Mundra", "MUN",
               "Adani Ports & SEZ", 22.74, 69.70, "west", "West",
               0.98, 11, 0.85, ("port777",)),
    PortRecord("JNPT", "INNSA", "JNPA / Nhava Sheva", "JNP",
               "Jawaharlal Nehru Port Authority", 18.95, 72.95, "west", "West",
               0.80, 13, 0.92, ("port776",)),
    PortRecord("MUMBAI", "INBOM", "Mumbai", "BOM",
               "Mumbai Port Authority", 18.96, 72.84, "west", "West",
               0.45, 10, 0.80, ()),
    PortRecord("MORMUGAO", "INMRM", "Mormugao", "MRM",
               "Mormugao Port Authority", 15.40, 73.80, "west", "West",
               0.30, 6, 0.62, ("port709",)),
    PortRecord("NEW_MANGALORE", "INNML", "New Mangalore", "NML",
               "New Mangalore Port Authority", 12.92, 74.80, "west", "West",
               0.42, 7, 0.66, ("port811",)),
    PortRecord("COCHIN", "INCOK", "Cochin (Vallarpadam)", "COK",
               "Cochin Port Authority", 9.97, 76.27, "south", "South",
               0.45, 6, 0.78, ("port583",)),
    PortRecord("TUTICORIN", "INTUT", "V.O. Chidambaranar (Tuticorin)", "TUT",
               "V.O. Chidambaranar Port Authority", 8.75, 78.20, "south", "South",
               0.40, 8, 0.70, ("port1331",)),
    PortRecord("CHENNAI", "INMAA", "Chennai", "MAA",
               "Chennai Port Authority", 13.10, 80.30, "east", "East",
               0.55, 8, 0.80, ("port235",)),
    PortRecord("KAMARAJAR", "INENR", "Kamarajar (Ennore)", "ENR",
               "Kamarajar Port Limited", 13.25, 80.33, "east", "East",
               0.45, 7, 0.74, ("port534",)),
    PortRecord("VIZAG", "INVTZ", "Visakhapatnam", "VTZ",
               "Visakhapatnam Port Authority", 17.69, 83.22, "east", "East",
               0.72, 9, 0.72, ("port1367",)),
    PortRecord("PARADIP", "INPRT", "Paradip", "PRT",
               "Paradip Port Authority", 20.26, 86.67, "east", "East",
               0.85, 9, 0.64, ("port883",)),
    PortRecord("KOLKATA", "INCCU", "Kolkata / Haldia", "CCU",
               "Syama Prasad Mookerjee Port", 22.55, 88.31, "east", "East",
               0.50, 7, 0.65, ("port207", "port442")),
]

# Legacy UN/LOCODEs that older caches and bookmarks may still carry.
_ALIASES: Dict[str, str] = {
    "INHAL": "INCCU",     # Haldia is modelled together with Kolkata
    "ININM": "INNML",
    "INKAT": "INMAA",     # Kattupalli shares the Chennai roadstead
    "INKRI": "INVTZ",     # Krishnapatnam folded into the Vizag corridor
    "INHZR": "INMUN",     # Hazira folded into the Gujarat cluster
}

_BY_MODEL_ID: Dict[str, PortRecord] = {p.model_id: p for p in PORTS}
_BY_LOCODE: Dict[str, PortRecord] = {p.locode: p for p in PORTS}
_BY_PORTWATCH: Dict[str, PortRecord] = {
    pw: p for p in PORTS for pw in p.portwatch_ids
}


def _index() -> Dict[str, PortRecord]:
    index: Dict[str, PortRecord] = {}
    for port in PORTS:
        index[port.model_id] = port
        index[port.locode] = port
        index[port.short] = port
        index[port.name.upper()] = port
        for pw in port.portwatch_ids:
            index[pw.upper()] = port
    for alias, locode in _ALIASES.items():
        index[alias] = _BY_LOCODE[locode]
    return index


_INDEX = _index()


def resolve(identifier: str) -> Optional[PortRecord]:
    """Resolve any identifier (model id, LOCODE, short, name, PortWatch id)."""
    if not identifier:
        return None
    key = str(identifier).strip().upper()
    if key in _INDEX:
        return _INDEX[key]
    # Substring match on the display name, e.g. "NHAVA" or "KANDLA".
    for port in PORTS:
        if key in port.name.upper():
            return port
    return None


def require(identifier: str) -> PortRecord:
    port = resolve(identifier)
    if port is None:
        raise KeyError(f"Unknown port identifier: {identifier!r}")
    return port


def locode_for(identifier: str) -> str:
    return require(identifier).locode


def model_id_for(identifier: str) -> str:
    return require(identifier).model_id


def all_ports() -> List[PortRecord]:
    return list(PORTS)


def locodes() -> List[str]:
    return [p.locode for p in PORTS]


def model_ids() -> List[str]:
    return [p.model_id for p in PORTS]


def to_dicts(identifiers: Iterable[str] | None = None) -> List[dict]:
    ports = ([require(i) for i in identifiers] if identifiers is not None
             else list(PORTS))
    return [p.as_dict() for p in ports]
