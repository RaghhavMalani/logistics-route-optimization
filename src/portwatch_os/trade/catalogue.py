"""Which commodity classes each Indian port structurally handles, and who says so.

This is a catalogue of *presence*, not of volume. A port is linked to a
class when a cited source states the port handles it; the link carries the
source and nothing else. No tonnage, no trade value and no share appears
here or anywhere downstream, because none of that is held by this
deployment and estimating it would be inventing it. The word the product
uses for what follows from these links is STRUCTURAL EXPOSURE.

Two kinds of source:

*   **the Ministry's own table.** Basic Port Statistics of India 2023-24,
    Table 2.1.3 "Traffic Handled - Port-wise and Principal Commodity-wise",
    lists every major port's tonnage by principal commodity. A class is
    present at a major port when the table shows a non-zero 2023-24 total for
    a commodity in that class. The tonnages were read to decide presence and
    are deliberately not copied.
*   **a terminal operator's or port's own statement** for what the table
    does not distinguish: LNG terminals, ro-ro automobile terminals, and the
    one non-major port in the registry (Mundra).

Classes and the table rows that map to them:

    CRUDE         POL Crude
    POL_PRODUCTS  POL Products
    LNG           (terminal operator statements only)
    DRY_BULK      Coking Coal, Thermal Coal, Iron Ore/Pellets, Other Ore,
                  Fertiliser, FRM - Dry, Food Grains, Cement
    LIQUID_BULK   FRM - Liquid, Veg. Oil, Chemicals
    CONTAINER     Container
    AUTOMOTIVE    (ro-ro terminal statements only)
    GENERAL_CARGO Iron & Steel, Iron Scrap, Sugar, Salt, Tea and Coffee, Others
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

CRUDE = "CRUDE"
POL_PRODUCTS = "POL_PRODUCTS"
LNG = "LNG"
DRY_BULK = "DRY_BULK"
LIQUID_BULK = "LIQUID_BULK"
CONTAINER = "CONTAINER"
AUTOMOTIVE = "AUTOMOTIVE"
GENERAL_CARGO = "GENERAL_CARGO"

CLASSES: Tuple[str, ...] = (CONTAINER, CRUDE, POL_PRODUCTS, LNG, DRY_BULK, LIQUID_BULK, AUTOMOTIVE, GENERAL_CARGO)

LABELS: Dict[str, str] = {
    CONTAINER: "Containers",
    CRUDE: "Crude oil",
    POL_PRODUCTS: "Petroleum products",
    LNG: "LNG",
    DRY_BULK: "Dry bulk (coal, ore, fertiliser, grain, cement)",
    LIQUID_BULK: "Liquid bulk (vegetable oil, chemicals, liquid fertiliser)",
    AUTOMOTIVE: "Automobiles (ro-ro)",
    GENERAL_CARGO: "General and break-bulk cargo",
}

#: The Ministry's table, read for presence only.
BPS_2324 = {
    "sourceId": "bps-2023-24-table-2.1.3",
    "name": "Basic Port Statistics of India 2023-24, Table 2.1.3: Traffic Handled - Port-wise and Principal Commodity-wise",
    "publisher": "Ministry of Ports, Shipping and Waterways, Government of India",
    "url": "https://shipmin.gov.in/sites/default/files/Revised%20Basic%20Port%20Statistics%20of%20India%202023-24%20%281%29.pdf",
    "retrievedAt": "2026-09-15T04:40:00Z",
    "basis": "a class is present when the 2023-24 overseas plus coastal total for a commodity in that class is non-zero; "
             "the tonnages are not reproduced",
}

#: Table rows to classes.
ROW_CLASS: Dict[str, str] = {
    "POL Crude": CRUDE, "POL Products": POL_PRODUCTS,
    "Coking Coal": DRY_BULK, "Thermal Coal": DRY_BULK, "Iron Ore/Pellets": DRY_BULK, "Other Ore": DRY_BULK,
    "Fertiliser": DRY_BULK, "FRM - Dry": DRY_BULK, "Food Grains": DRY_BULK, "Cement": DRY_BULK,
    "FRM - Liquid": LIQUID_BULK, "Veg. Oil": LIQUID_BULK, "Chemicals": LIQUID_BULK,
    "Container": CONTAINER,
    "Iron & Steel": GENERAL_CARGO, "Iron Scrap": GENERAL_CARGO, "Sugar": GENERAL_CARGO, "Salt": GENERAL_CARGO,
    "Tea and Coffee": GENERAL_CARGO, "Others": GENERAL_CARGO,
}

#: Rows with a non-zero 2023-24 total per major port, as read from Table 2.1.3
#: (pages 73-86 of the document). Kolkata and Haldia are one registry port.
BPS_ROWS_PRESENT: Dict[str, Tuple[str, ...]] = {
    "INCCU": ("POL Crude", "POL Products", "Fertiliser", "FRM - Dry", "FRM - Liquid", "Iron & Steel", "Iron Scrap",
              "Sugar", "Veg. Oil", "Coking Coal", "Iron Ore/Pellets", "Other Ore", "Container", "Others"),
    "INPRT": ("POL Crude", "POL Products", "Fertiliser", "FRM - Dry", "FRM - Liquid", "Iron & Steel", "Iron Scrap",
              "Veg. Oil", "Coking Coal", "Thermal Coal", "Iron Ore/Pellets", "Other Ore", "Container", "Others"),
    "INVTZ": ("POL Crude", "POL Products", "Fertiliser", "FRM - Dry", "FRM - Liquid", "Food Grains", "Iron & Steel",
              "Coking Coal", "Thermal Coal", "Iron Ore/Pellets", "Other Ore", "Container", "Others"),
    "INENR": ("POL Products", "Iron & Steel", "Coking Coal", "Thermal Coal", "Other Ore", "Container", "Others"),
    "INMAA": ("POL Crude", "POL Products", "FRM - Dry", "Iron & Steel", "Iron Scrap", "Veg. Oil", "Salt", "Other Ore",
              "Container", "Others"),
    "INTUT": ("POL Products", "Fertiliser", "FRM - Dry", "FRM - Liquid", "Food Grains", "Iron & Steel", "Veg. Oil",
              "Salt", "Thermal Coal", "Cement", "Other Ore", "Container", "Others"),
    "INCOK": ("POL Crude", "POL Products", "FRM - Dry", "FRM - Liquid", "Iron & Steel", "Veg. Oil", "Salt", "Cement",
              "Container", "Others"),
    "INNML": ("POL Crude", "POL Products", "Fertiliser", "FRM - Dry", "FRM - Liquid", "Iron & Steel", "Veg. Oil",
              "Coking Coal", "Thermal Coal", "Cement", "Iron Ore/Pellets", "Container", "Others"),
    "INMRM": ("POL Products", "Fertiliser", "FRM - Liquid", "Iron & Steel", "Veg. Oil", "Coking Coal", "Thermal Coal",
              "Iron Ore/Pellets", "Others"),
    "INNSA": ("POL Crude", "POL Products", "FRM - Liquid", "Veg. Oil", "Chemicals", "Container", "Others"),
    "INBOM": ("POL Crude", "POL Products", "Fertiliser", "FRM - Dry", "Food Grains", "Iron & Steel", "Veg. Oil",
              "Thermal Coal", "Iron Ore/Pellets", "Container", "Others"),
    "INIXY": ("POL Crude", "POL Products", "Fertiliser", "FRM - Dry", "FRM - Liquid", "Food Grains", "Iron & Steel",
              "Iron Scrap", "Sugar", "Veg. Oil", "Salt", "Coking Coal", "Thermal Coal", "Iron Ore/Pellets", "Other Ore",
              "Container", "Others"),
}


@dataclass(frozen=True)
class ClassSource:
    source_id: str
    name: str
    url: str
    retrieved_at: str
    statement: str

    def to_dict(self) -> Dict[str, str]:
        return {"sourceId": self.source_id, "name": self.name, "url": self.url, "retrievedAt": self.retrieved_at,
                "statement": self.statement}


#: Operator and port statements for what the table does not distinguish, and
#: for the non-major port. Each carries the statement it rests on.
STATEMENTS: Dict[Tuple[str, str], ClassSource] = {
    ("INCOK", LNG): ClassSource(
        "cochin-port-lng", "Cochin Port Authority: LNG Terminal", "https://cochinport.gov.in/lng-terminal",
        "2026-09-15T04:50:00Z",
        "Cochin Port has an LNG terminal and re-gasification plant at Puthuvypeen run by Petronet LNG Ltd, "
        "commissioned in August 2013."),
    ("INENR", LNG): ClassSource(
        "kpl-iocl-lng", "Kamarajar Port: Indian Oil LNG Terminal",
        "https://www.ennoreport.gov.in/content/innerpage/indian-oil-lng-terminal.php", "2026-09-15T04:50:00Z",
        "IndianOil's LNG import and regasification terminal at Kamarajar Port, Ennore, commissioned in "
        "February 2019; the first on the east coast."),
    ("INMAA", AUTOMOTIVE): ClassSource(
        "chennai-port-roro", "India Shipping News: Chennai Port achieves landmark milestone in automotive exports",
        "https://indiashippingnews.com/export/chennai-port-achieves-landmark-milestone-in-automotive-exports/",
        "2026-09-15T04:50:00Z",
        "Chennai Port Authority handles vehicle exports through its ro-ro gateway."),
    ("INENR", AUTOMOTIVE): ClassSource(
        "kpl-roro", "Kamarajar Port (Wikipedia, citing the port authority)", "https://en.wikipedia.org/wiki/Kamarajar_Port",
        "2026-09-15T04:50:00Z",
        "A car-cum-general cargo berth was developed and commissioned by Kamarajar Port for handling automobile units; "
        "the ro-ro terminal is used for automobile exports and imports."),
    ("INBOM", AUTOMOTIVE): ClassSource(
        "mumbai-port-roro", "Automotive Logistics: Indian exports seek the perfect port",
        "https://www.automotivelogistics.media/ports-and-processors/indian-exports-seek-the-perfect-port/199307",
        "2026-09-15T04:50:00Z",
        "Mumbai Port is used by Maruti Suzuki and other automakers for overseas vehicle shipments."),
    ("INMUN", CONTAINER): ClassSource(
        "apsez-mundra", "Adani Ports & SEZ: Mundra Port", "https://www.adaniports.com/ports-and-terminals/mundra-port",
        "2026-09-15T04:45:00Z", "Four container terminals."),
    ("INMUN", CRUDE): ClassSource(
        "apsez-mundra", "Adani Ports & SEZ: Mundra Port", "https://www.adaniports.com/ports-and-terminals/mundra-port",
        "2026-09-15T04:45:00Z", "Two single point moorings to evacuate imported crude oil; VLCC and ULCC capable."),
    ("INMUN", LNG): ClassSource(
        "apsez-mundra", "Adani Ports & SEZ: Mundra Port", "https://www.adaniports.com/ports-and-terminals/mundra-port",
        "2026-09-15T04:45:00Z", "Marine services handle LNG, crude, ro-ro and bulk vessels."),
    ("INMUN", DRY_BULK): ClassSource(
        "apsez-mundra", "Adani Ports & SEZ: Mundra Port", "https://www.adaniports.com/ports-and-terminals/mundra-port",
        "2026-09-15T04:45:00Z", "Largest coal import terminal; bulk and break-bulk: fertiliser, agri, mines and minerals."),
    ("INMUN", LIQUID_BULK): ClassSource(
        "apsez-mundra", "Adani Ports & SEZ: Mundra Port", "https://www.adaniports.com/ports-and-terminals/mundra-port",
        "2026-09-15T04:45:00Z", "Tank farm storing vegetable oil, chemicals and POL products."),
    ("INMUN", POL_PRODUCTS): ClassSource(
        "apsez-mundra", "Adani Ports & SEZ: Mundra Port", "https://www.adaniports.com/ports-and-terminals/mundra-port",
        "2026-09-15T04:45:00Z", "Tank farm storing petroleum, oil and lubricant (POL) products."),
    ("INMUN", AUTOMOTIVE): ClassSource(
        "apsez-mundra", "Adani Ports & SEZ: Mundra Port", "https://www.adaniports.com/ports-and-terminals/mundra-port",
        "2026-09-15T04:45:00Z", "Automobile roll-on roll-off terminal handling cars, buses and trucks."),
    ("INMUN", GENERAL_CARGO): ClassSource(
        "apsez-mundra", "Adani Ports & SEZ: Mundra Port", "https://www.adaniports.com/ports-and-terminals/mundra-port",
        "2026-09-15T04:45:00Z", "Break-bulk: steel and project cargo."),
}


@dataclass(frozen=True)
class PortClass:
    """One port handles one class, and here is who says so."""

    port_code: str
    commodity_class: str
    sources: Tuple[Dict[str, str], ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, object]:
        return {"portCode": self.port_code, "commodityClass": self.commodity_class,
                "label": LABELS[self.commodity_class], "sources": list(self.sources)}


def port_classes() -> List[PortClass]:
    """Every (port, class) link the catalogue can defend, with its sources."""
    links: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
    for port, rows in BPS_ROWS_PRESENT.items():
        for row in rows:
            cls = ROW_CLASS.get(row)
            if cls is None:
                continue
            sources = links.setdefault((port, cls), [])
            if not any(s["sourceId"] == BPS_2324["sourceId"] for s in sources):
                sources.append({**BPS_2324, "rows": [row]})
            else:
                for s in sources:
                    if s["sourceId"] == BPS_2324["sourceId"] and row not in s["rows"]:
                        s["rows"].append(row)
    for (port, cls), statement in STATEMENTS.items():
        links.setdefault((port, cls), []).append(statement.to_dict())
    return [PortClass(port, cls, tuple(sources)) for (port, cls), sources in sorted(links.items())]


def classes_for(port_code: str) -> List[PortClass]:
    return [link for link in port_classes() if link.port_code == port_code]


__all__ = [
    "AUTOMOTIVE", "BPS_2324", "CLASSES", "CONTAINER", "CRUDE", "DRY_BULK", "GENERAL_CARGO", "LABELS", "LIQUID_BULK",
    "LNG", "POL_PRODUCTS", "PortClass", "STATEMENTS", "classes_for", "port_classes",
]
