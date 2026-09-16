"""Resolving an AIS destination field to a port, with the confidence it earns.

The AIS destination is free text typed on the bridge. It is "INNSA" on a good
day, "NHAVA SHEVA" on an ordinary one, "IN NSA", "JNPT VIA COLOMBO", "FOR
ORDERS" or "" on the rest. Treating that field as a port code is how a world
model ends up routing a ship to a port it never mentioned.

So resolution here is graded, and the grade travels with the answer:

    LOCODE    the text is, or contains, a UN/LOCODE in the registry     0.90
    NAME      the text contains a port's name or short code              0.70
    COUNTRY   the text names India and nothing this registry knows       0.20
    FOREIGN   the text is a LOCODE outside India; a real destination,
              just not one the model covers                              0.00
    NONE      nothing usable                                             --

A downstream consumer that wants a port gets one only at LOCODE or NAME, and
gets the confidence alongside so a cascade built on it is discounted rather
than trusted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.utils import port_registry

LOCODE = "LOCODE"
NAME = "NAME"
COUNTRY = "COUNTRY"
FOREIGN = "FOREIGN"
NONE = "NONE"

CONFIDENCE: Dict[str, float] = {LOCODE: 0.90, NAME: 0.70, COUNTRY: 0.20, FOREIGN: 0.0, NONE: 0.0}

#: Phrases crews type that mean "no destination" rather than a place.
_NON_DESTINATIONS = ("FOR ORDERS", "FOR ORDER", "ORDERS", "UNKNOWN", "NIL", "N/A", "NONE", "---")
_LOCODE = re.compile(r"\b([A-Z]{2})\s?([A-Z0-9]{3})\b")

#: Spellings that appear in real AIS destination fields for the modelled
#: ports and are not the registry's display name. Mapped to LOCODEs; still
#: graded as NAME, because the field is free text however it is spelt.
_AIS_SPELLINGS: Dict[str, str] = {
    "JNPT": "INNSA", "JNPA": "INNSA", "NHAVA": "INNSA", "NAVA SHEVA": "INNSA",
    "NHAVASHEVA": "INNSA", "MUMBAI": "INBOM", "BOMBAY": "INBOM",
    "VIZAG": "INVTZ", "VISAKHAPATNAM": "INVTZ", "VISHAKHAPATNAM": "INVTZ",
    "TUTICORIN": "INTUT", "THOOTHUKUDI": "INTUT", "ENNORE": "INENR",
    "KANDLA": "INIXY", "DEENDAYAL": "INIXY", "HALDIA": "INCCU", "KOLKATA": "INCCU",
    "CALCUTTA": "INCCU", "COCHIN": "INCOK", "KOCHI": "INCOK", "VALLARPADAM": "INCOK",
    "MANGALORE": "INNML", "MANGALURU": "INNML", "MORMUGAO": "INMRM", "MARMAGAO": "INMRM",
    "GOA": "INMRM", "PARADIP": "INPRT", "PARADEEP": "INPRT", "CHENNAI": "INMAA",
    "MADRAS": "INMAA", "MUNDRA": "INMUN",
}


@dataclass(frozen=True)
class DestinationResolution:
    text: Optional[str]
    port_code: Optional[str]
    port_name: Optional[str]
    method: str
    confidence: float
    reason: str

    @property
    def resolved(self) -> bool:
        return self.port_code is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "portCode": self.port_code,
            "portName": self.port_name,
            "method": self.method,
            "confidence": self.confidence,
            "resolved": self.resolved,
            "reason": self.reason,
        }


def resolve_destination(text: Optional[str]) -> DestinationResolution:
    """Grade one destination string. Never raises; never guesses past the grade."""
    raw = (text or "").strip()
    upper = " ".join(raw.upper().replace(">", " > ").split())
    if not upper or upper in _NON_DESTINATIONS:
        reason = "no destination was stated" if not upper else f"{raw!r} is not a place"
        return DestinationResolution(text or None, None, None, NONE, 0.0, reason)

    # Route notation: "COLOMBO > INNSA" or "INMAA VIA COLOMBO" -- the final
    # destination is what matters; the other tokens are calls on the way.
    tail = upper.split(" VIA ")[0] if " VIA " in upper else upper
    if " > " in tail:
        tail = tail.split(" > ")[-1].strip()

    # 1. A LOCODE the registry knows, anywhere in the tail.
    for match in _LOCODE.finditer(tail):
        code = match.group(1) + match.group(2)
        port = port_registry.resolve(code)
        if port is not None and (port.locode == code or code in port_registry._ALIASES):
            return DestinationResolution(raw, port.locode, port.name, LOCODE, CONFIDENCE[LOCODE],
                                         f"{code} is the UN/LOCODE of {port.name}")

    # 2. A name or short code the registry knows, or a spelling crews use.
    for spelling, locode in sorted(_AIS_SPELLINGS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(spelling)}\b", tail):
            port = port_registry.require(locode)
            return DestinationResolution(raw, port.locode, port.name, NAME, CONFIDENCE[NAME],
                                         f"{spelling!r} names {port.name}; free text, not a code")
    for port in port_registry.all_ports():
        names = {port.short, port.name.upper()}
        names.update(part.strip() for part in re.split(r"[/()]", port.name.upper()) if part.strip())
        for candidate in sorted(names, key=len, reverse=True):
            if len(candidate) >= 3 and re.search(rf"\b{re.escape(candidate)}\b", tail):
                return DestinationResolution(raw, port.locode, port.name, NAME, CONFIDENCE[NAME],
                                             f"{candidate!r} names {port.name}; free text, not a code")

    # 3. A LOCODE outside India: a real destination the model does not cover.
    for match in _LOCODE.finditer(tail):
        country = match.group(1)
        if country != "IN" and " " not in match.group(0):
            return DestinationResolution(raw, None, None, FOREIGN, CONFIDENCE[FOREIGN],
                                         f"{match.group(0)} looks like a {country} LOCODE, outside the modelled ports")

    # 4. India, but nowhere this registry knows.
    if tail.startswith("IN ") or "INDIA" in tail or (tail.startswith("IN") and _LOCODE.match(tail)):
        return DestinationResolution(raw, None, None, COUNTRY, CONFIDENCE[COUNTRY],
                                     f"{raw!r} names India but no port in the registry")

    return DestinationResolution(raw, None, None, NONE, 0.0, f"{raw!r} could not be read as a port")


__all__ = ["COUNTRY", "DestinationResolution", "FOREIGN", "LOCODE", "NAME", "NONE", "resolve_destination"]
