"""Public tariff ingestion: published scales of rates, transcribed and cited.

Indian major ports publish their Scale of Rates as Gazette notifications --
approved by the Tariff Authority for Major Ports and mirrored on each port
authority's own site. Those documents are public, dated, and state their
validity, which makes them usable as a *cost basis of last resort*: what the
port publishes it charges, not what any carrier has negotiated. The adapter
therefore labels every rate ``PUBLIC_TARIFF`` and never ``CUSTOMER_COST``.

Ingestion is deliberately not a scraper. A schedule is a structured file
(``data/tariffs/public_tariffs.json``) in which every rate carries the document
URL, the retrieval instant, the document's hash and page count, the section
heading and the verbatim text the number was read from, and the reuse finding
for the site it came from. Building that file is a reviewed act; the parser
here refuses a rate that arrives without its citation, so nothing can enter
the basis on the strength of a number alone.

Validity is honoured exactly. Chennai's indexed schedule lapsed on 30 April
2026 and its successor is a *proposed* revision; the adapter carries the
lapsed schedule with its dates and the basis reports it as lapsed rather than
using it -- which is the correct answer to "what does Chennai charge today":
the last approved figure is known, and it is no longer in force.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.portwatch_os.finance.basis import (
    CostBasis,
    CostRate,
    CostSchedule,
    PRIMITIVES,
    PUBLIC_TARIFF,
)

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "tariffs" / "public_tariffs.json"
ENV_PATH = "PORTWATCH_PUBLIC_TARIFFS"

#: What a rate row must carry to be accepted. A row without these is not a
#: transcription, it is a claim.
REQUIRED_CITATION = ("page", "section", "verbatim")


class TariffError(ValueError):
    """A schedule file that does not meet the citation standard."""


def parse_schedule(body: Dict[str, Any]) -> CostSchedule:
    """One schedule from its structured form, checked for citation."""
    schedule_id = str(body.get("scheduleId") or "").strip()
    if not schedule_id:
        raise TariffError("a schedule needs a scheduleId")
    provenance = dict(body.get("provenance") or {})
    for key in ("url", "retrievedAt", "sha256"):
        if not provenance.get(key):
            raise TariffError(f"schedule {schedule_id} lacks provenance.{key}")
    source_type = str(body.get("sourceType") or PUBLIC_TARIFF)
    if source_type != PUBLIC_TARIFF:
        raise TariffError(f"schedule {schedule_id} is {source_type}; this adapter ingests PUBLIC_TARIFF only")
    scope = str(body.get("scope") or "*")
    title = str(body.get("title") or schedule_id)
    valid_from = body.get("validFrom")
    valid_to = body.get("validTo")

    rates: List[CostRate] = []
    for index, row in enumerate(body.get("rates") or []):
        missing = [k for k in REQUIRED_CITATION if not row.get(k)]
        if missing:
            raise TariffError(
                f"schedule {schedule_id} rate {index} lacks {', '.join(missing)}; a tariff "
                "rate must cite the page, section and verbatim text it was read from"
            )
        primitive = str(row.get("primitive") or "")
        if primitive not in PRIMITIVES:
            raise TariffError(f"schedule {schedule_id} rate {index}: unknown primitive {primitive}")
        rates.append(CostRate(
            primitive=primitive,
            value=float(row["value"]),
            currency=str(row["currency"]),
            unit=PRIMITIVES[primitive].per,
            scope=scope,
            valid_from=valid_from,
            valid_to=valid_to,
            source=title,
            source_type=PUBLIC_TARIFF,
            confidence=0.9,
            provenance={
                "url": provenance["url"],
                "retrievedAt": provenance["retrievedAt"],
                "sha256": provenance["sha256"],
                "page": row["page"],
                "section": row["section"],
                "verbatim": row["verbatim"],
                "scheduleId": schedule_id,
            },
            vessel_status=row.get("vesselStatus"),
            vessel_type=row.get("vesselType"),
            tier_min_grt=row.get("tierMinGrt"),
            tier_max_grt=row.get("tierMaxGrt"),
            tier_base_amount=row.get("tierBaseAmount"),
            label=str(row.get("label") or PRIMITIVES[primitive].label),
        ))

    schedule = CostSchedule(
        schedule_id=schedule_id, title=title, source_type=PUBLIC_TARIFF, scope=scope,
        rates=rates,
        provenance={**provenance, "authority": body.get("authority"),
                    "reuseEvidence": body.get("reuseEvidence")},
        reuse=str(body.get("reuse") or "REQUIRES_REVIEW"),
    )
    if provenance.get("successor"):
        successor = provenance["successor"]
        schedule.notes.append(
            f"A successor document exists: {successor.get('title')} -- {successor.get('status')}"
        )
    if provenance.get("fxRule"):
        schedule.notes.append(f"FX rule stated by the document: {provenance['fxRule']}")
    else:
        schedule.notes.append("The document states no exchange-rate rule.")
    return schedule


def load_public_tariffs(path: Optional[Path] = None) -> List[CostSchedule]:
    """Every schedule in the evidence file. Missing file, empty list."""
    location = path or Path(os.getenv(ENV_PATH) or DEFAULT_PATH)
    if not location.exists():
        return []
    with location.open("r", encoding="utf-8") as handle:
        body = json.load(handle)
    return [parse_schedule(item) for item in body.get("schedules") or []]


def investigation(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The sources looked at, including the ones nothing was taken from."""
    location = path or Path(os.getenv(ENV_PATH) or DEFAULT_PATH)
    if not location.exists():
        return []
    with location.open("r", encoding="utf-8") as handle:
        body = json.load(handle)
    return list(body.get("investigated") or [])


def basis_with_public_tariffs(basis: Optional[CostBasis] = None, *, path: Optional[Path] = None) -> CostBasis:
    """A cost basis holding every public schedule, on top of an existing one."""
    target = basis if basis is not None else CostBasis()
    for schedule in load_public_tariffs(path):
        target.add_schedule(schedule)
    return target


__all__ = [
    "DEFAULT_PATH",
    "ENV_PATH",
    "REQUIRED_CITATION",
    "TariffError",
    "basis_with_public_tariffs",
    "investigation",
    "load_public_tariffs",
    "parse_schedule",
]
