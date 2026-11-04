"""Additive, read-only diagnostics over existing public source stores.

Legacy readiness, model weights and the cached source register are unchanged.
Additional retained products appear separately so observing them cannot alter
the numerical readiness consumed by older callers. No collector runs here.
"""
from __future__ import annotations

from copy import deepcopy
import json


def _check_optional(row: dict) -> None:
    if row.get("sourceQuality") is None:
        return
    try:
        json.dumps(row["sourceQuality"], allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        row["sourceQuality"] = None
        row["sourceQualityError"] = "Retained source-quality metadata is not valid JSON."


def project(payload: dict) -> dict:
    from src.ingestion.weather_quality import (
        current_weather_products, quality_for_weather_source,
    )
    from src.portwatch_os.intelligence.operational_quality import (
        operational_source_rows, quality_for_activity_source,
    )

    result = deepcopy(payload)
    sources = result.get("sources")
    if not isinstance(sources, dict):
        sources = {}
    for name, row in sources.items():
        if not isinstance(row, dict):
            continue
        try:
            quality = quality_for_weather_source(name, row)
            if quality is None:
                quality = quality_for_activity_source(name, row)
            if quality is not None:
                row["sourceQuality"] = deepcopy(quality)
                row.pop("sourceQualityError", None)
        except Exception:
            # A damaged optional archive must not hide useful legacy fields or
            # disclose local paths/provider credentials through exception text.
            row["sourceQuality"] = None
            row["sourceQualityError"] = "Retained source-quality evidence could not be verified."
        _check_optional(row)
    products = {}
    unavailable = []
    for label, reader in (("weather", current_weather_products),
                          ("operational", operational_source_rows)):
        try:
            for row in reader():
                if isinstance(row, dict) and isinstance(row.get("source"), str):
                    row = deepcopy(row)
                    _check_optional(row)
                    products[row["source"]] = row
        except Exception:
            unavailable.append(label)
    result["sources"] = sources
    result["sourceQualityProducts"] = products
    result["sourceQualityProjection"] = {
        "version": "retained-public-source-quality-v1",
        "readOnly": True,
        "legacyReadinessMeaning": "Unchanged status-weight heuristic over legacy registered sources; not calibrated accuracy.",
        "unavailableProjections": unavailable,
    }
    return result
