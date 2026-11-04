"""Read-only source-quality projection from weather producers and retained data.

No collection, ledger writes, confidence weighting, or weather-value changes
belong here. The daily training archive and current hourly forecast products
remain separate even when both were fetched on the same day.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

from src.ingestion import source_receipts as receipts
from src.utils import port_registry

VERSION = "weather-source-quality-v1"
PARSER = "open-meteo-daily-flatten-v1"
FIELDS = {
    "wind_speed_10m_max": ("wind_speed", "km/h", "kn", "MAX", "source × 0.539957"),
    "wind_gusts_10m_max": ("wind_gust", "km/h", "kn", "MAX", "source × 0.539957"),
    "precipitation_sum": ("rainfall", "mm", "mm/day", "SUM", "Daily UTC accumulation; value unchanged"),
    "visibility_mean": ("visibility", "m", "km", "MEAN", "source ÷ 1000"),
    "wave_height_max": ("wave_height", "m", "m", "MAX", "Daily maximum; value unchanged"),
}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _iso(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).isoformat() if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _receipt_clock(value):
    at = _iso(value)
    return at if at and datetime.fromisoformat(at) <= datetime.now(timezone.utc) else None


def _base(legacy, product, role, use):
    status = legacy.get("status")
    if status not in {"LIVE", "CACHED_LIVE", "STALE", "SYNTHETIC", "UNAVAILABLE"}:
        status = "UNAVAILABLE"
    return {"schemaVersion": 1, "metadataVersion": VERSION,
        "temporalRole": role, "valueKinds": ["DERIVED"], "operationalUse": use,
        "receipt": {"lastFetchedAt": None, "lastCheckedAt": None, "status": status,
                    "fallback": legacy.get("fallback") if isinstance(legacy.get("fallback"), str) else None},
        "coverage": {"portCodes": [], "variables": [], "observedFrom": None,
            "observedThrough": None, "observationAgeSeconds": None,
            "observationFreshnessBudgetSeconds": None, "forecastOriginAt": None,
            "targetFrom": None, "targetThrough": None, "datePrecision": "UNKNOWN"},
        "provenance": {"provider": "Open-Meteo", "sourceProductId": product,
            "sourceReceiptId": None, "originalRef": None, "originalHash": None,
            "derivationVersion": PARSER},
        "quality": {"rowCount": 0, "confidence": None, "completeness": None,
            "missingFields": [], "issues": []}, "unknownReasons": [
                "Confidence is unavailable: legacy status multipliers are readiness heuristics, not calibrated source accuracy.",
                "Field completeness is not a calibrated confidence score."],
        "sourceReceipts": [], "units": [],
        "semantics": {"providerPublicationAt": None, "providerIssueAt": None,
            "applicationReceiptMeaning": "First application receipt of exact retained response bytes; never filesystem modification time.",
            "stationObservation": False, "parserVersion": PARSER}}


def _payload(path):
    try:
        body = json.loads(Path(path).read_text(encoding="utf-8"))
        return body if isinstance(body, list) else [body] if isinstance(body, dict) else []
    except (OSError, ValueError, TypeError):
        return []


def _coverage(payload, fields, requested=None):
    """Project only finite supplied daily cells consumed by the legacy parser."""
    supplied = {}
    units = {}
    grid = []
    issues = []
    for block_index, (port, block) in enumerate(zip(port_registry.all_ports(), payload)):
        if not isinstance(block, dict) or not isinstance(block.get("daily"), dict):
            continue
        daily = block["daily"]
        dates = daily.get("time")
        if not isinstance(dates, list):
            continue
        block_units = block.get("daily_units") if isinstance(block.get("daily_units"), dict) else {}
        port_code = port.locode if requested is not None else None
        if requested is None:
            issues.append("Physical-port coverage is unknown without the original requested coordinate/order mapping; current registry position is not proof.")
        if requested is not None:
            try:
                latitudes = str(requested.get("latitude", "")).split(",")
                longitudes = str(requested.get("longitude", "")).split(",")
                if abs(float(latitudes[block_index]) - port.lat) > 1e-6 or abs(float(longitudes[block_index]) - port.lon) > 1e-6:
                    raise ValueError("Legacy positional mapping differs from request")
            except (ValueError, TypeError, IndexError):
                port_code = None
                issues.append(f"Daily response block {block_index}: retained request does not support the legacy positional physical-port mapping; port coverage is unknown for this block.")
        for source in fields:
            values = daily.get(source)
            if not isinstance(values, list):
                continue
            variable, expected, output, statistic, derivation = FIELDS[source]
            source_unit = block_units.get(source)
            if source_unit != expected:
                issues.append(f"{port.locode} {source}: source unit is missing or differs from expected {expected}; conversion is the existing parser contract, not verified units.")
            for index, date in enumerate(dates):
                if _day(date) and index < len(values) and finite(values[index]):
                    supplied.setdefault((port_code if port_code else ("unmapped-block", block_index), date), set()).add(variable)
                    units[(variable, source_unit if isinstance(source_unit, str) else None)] = {
                        "variable": variable, "sourceVariable": source, "sourceUnit": source_unit if isinstance(source_unit, str) else None,
                        "outputUnit": output, "statistic": statistic, "aggregation": "UTC daily provider statistic",
                        "aggregationWindow": "Calendar date in the requested UTC timezone; date-only source precision.",
                        "derivation": derivation, "parserVersion": PARSER, "rawOrDerived": "DERIVED",
                        "unitContractVerified": source_unit == expected}
            if finite(block.get("latitude")) and finite(block.get("longitude")):
                grid.append({"portCode": port_code, "latitude": block["latitude"], "longitude": block["longitude"]})
    return supplied, list(units.values()), list({json.dumps(g, sort_keys=True): g for g in grid}.values()), sorted(set(issues))


def _daily(cache, legacy, kind):
    archive = kind == "history"
    product = "open-meteo:era5:daily-history-v1" if archive else "open-meteo:surface:daily-v1" if kind == "surface" else "open-meteo:marine:daily-v1"
    quality = _base(legacy, product, "HISTORICAL" if archive else "MIXED", "CONTEXT_ONLY" if archive else "CALCULATION_INPUT")
    fields = list(FIELDS)[:3] if archive else list(FIELDS)[:4] if kind == "surface" else ["wave_height_max"]
    data = _payload(cache)
    receipt, sidecar, reason = receipts.retained(cache)
    supplied, units, grid, issues = _coverage(data, fields, receipt.get("request") if receipt else None)
    days = sorted({date for _, date in supplied})
    known_ports = sorted({port for port, _ in supplied if isinstance(port, str)})
    unknown_ports = any(not isinstance(port, str) for port, _ in supplied)
    quality["coverage"].update(portCodes=known_ports if known_ports or not unknown_ports else None,
        variables=sorted(set().union(*supplied.values()) if supplied else []), datePrecision="DATE_ONLY" if days else "UNKNOWN")
    quality["units"], quality["gridLocations"] = units, grid
    quality["quality"]["rowCount"] = len(supplied)
    quality["quality"]["rowCountMeaning"] = "Parsed response-block/date rows with at least one finite supplied variable; unknown physical mapping is explicit and NaN placeholders excluded."
    quality["quality"]["issues"] = issues
    quality["semantics"].update(
        dataKind="REANALYSIS" if archive else "FORECAST_AND_PROVIDER_BACKFILL",
        consumerRole="Training feature history; never current hourly approach weather or station outcomes." if archive else
            "Daily weather features for risk/model context; raw values remain operational and correction candidates stay shadow-only.",
        rawOrDerived="DERIVED", sourceTimePrecision="DATE_ONLY")
    quality["semantics"]["portMappingBasis"] = "Retained original requested coordinate/order mapping and legacy parser." if receipt else "UNKNOWN: original requested coordinate/order mapping is not retained."
    quality["semantics"]["currentRegistryPositionIsCoverage"] = False
    if unknown_ports:
        quality["unknownReasons"].append("Finite values/dates and returned grid coordinates are retained, but physical ports are unknown where the original request does not support a mapping.")
    quality["receipt"]["lastCheckedAt"] = _receipt_clock(sidecar.get("lastCheckedAt"))
    quality["receipt"]["lastFetchedAt"] = _receipt_clock(sidecar.get("lastFetchedAt"))
    quality["semantics"]["legacyDeclaredStatus"] = legacy.get("status") if isinstance(legacy.get("status"), str) else None
    if receipt:
        fetched = quality["receipt"]["lastFetchedAt"]
        fetched_age = (datetime.now(timezone.utc) - datetime.fromisoformat(fetched)).total_seconds() if fetched else None
        ttl = 7 * 24 * 3600 if archive else 3 * 3600
        quality["receipt"]["status"] = "CACHED_LIVE" if fetched_age is not None and fetched_age <= ttl else "STALE"
        quality["semantics"]["receiptStatusMeaning"] = "Availability of the retained exact response receipt/cache; independent of the age and historical/forecast role of its samples. Projection itself performs no network check."
        quality["provenance"].update(sourceReceiptId=receipt["sourceReceiptId"],
            originalRef=receipt["originalRef"], originalHash=receipt["responseSha256"])
        quality["sourceReceipts"] = [{"schemaVersion": 1, "sourceProductId": product,
            "sourceReceiptId": receipt["sourceReceiptId"], "provider": "Open-Meteo",
            "fetchedAt": receipt["fetchedAt"], "checkedAt": quality["receipt"]["lastCheckedAt"],
            "firstAvailableAt": receipt["firstAvailableAt"], "originalRef": receipt["originalRef"],
            "originalHash": receipt["responseSha256"], "parserVersion": PARSER,
            "parseStatus": "PARTIAL" if issues else "ACCEPTED", "issues": issues,
            "previousReceiptId": receipt.get("previousReceiptId"), "lineageRelation": receipt.get("lineageRelation")}]
        quality["firstAvailableAt"] = receipt["firstAvailableAt"]
        request = receipt.get("request") or {}
        requested_ports = []
        try:
            coords = zip(str(request.get("latitude", "")).split(","), str(request.get("longitude", "")).split(","))
            for lat, lon in coords:
                requested_ports.extend(p.locode for p in port_registry.all_ports() if abs(p.lat - float(lat)) < 1e-6 and abs(p.lon - float(lon)) < 1e-6)
        except (ValueError, TypeError):
            pass
        quality["requestedCoverage"] = {"portCodes": sorted(set(requested_ports)),
            "from": request.get("start_date"), "through": request.get("end_date"),
            "variables": request.get("daily", "").split(",") if isinstance(request.get("daily"), str) else None,
            "pastDays": request.get("past_days"), "forecastDays": request.get("forecast_days"),
            "meaning": "Configured requested coverage; not proof of returned values."}
    else:
        quality["receipt"]["status"] = "UNAVAILABLE"
        quality["semantics"]["receiptStatusMeaning"] = "Original receipt identity is unavailable or unverified. Parsed legacy daily cache remains available for supported coverage projection; outer legacy status and numerical weights are unchanged."
        quality["unknownReasons"].append(reason)
        quality["quality"]["missingFields"] += ["originalRef", "originalHash", "sourceReceiptId", "firstAvailableAt"]
        quality["requestedCoverage"] = {"portCodes": None, "variables": None, "from": None, "through": None,
            "meaning": "Original request not retained; configured current ports do not prove the old request."}
    if archive:
        quality["coverage"].update(observedFrom=days[0] if days else None, observedThrough=days[-1] if days else None)
        quality["unknownReasons"] += ["ERA5 is gridded reanalysis, not a station measurement or a forecast target.",
            "Provider observation/publication instant is not supplied; retained daily dates have date-only precision.",
            "Visibility and wave-height NaN placeholders are not supplied archive coverage."]
    else:
        # A forecast endpoint's past_days is provider backfill, never observed truth.
        receipt_day = receipt["firstAvailableAt"][:10] if receipt else None
        future_days = [day for day in days if receipt_day and day >= receipt_day]
        backfill_days = [day for day in days if receipt_day and day < receipt_day]
        quality["coverage"].update(targetFrom=future_days[0] if future_days else None,
            targetThrough=future_days[-1] if future_days else None)
        quality["samplePeriods"] = {"from": days[0] if days else None, "through": days[-1] if days else None,
            "kind": "FORECAST_AND_PROVIDER_BACKFILL", "backfillIsVerification": False,
            "backfillFrom": backfill_days[0] if backfill_days else None,
            "backfillThrough": backfill_days[-1] if backfill_days else None,
            "forecastFrom": future_days[0] if future_days else None,
            "forecastThrough": future_days[-1] if future_days else None,
            "partitionBasis": "Sample date relative to original application receipt UTC date; not provider model origin." if receipt else
                "Original application receipt unknown; forecast versus backfill date partition unavailable."}
        if not receipt:
            quality["unknownReasons"].append("Forecast/backfill target partition is unknown without an original receipt; sample-period dates remain inspectable.")
        elif future_days and not backfill_days:
            quality["temporalRole"] = "FORECAST"
        elif backfill_days and not future_days:
            quality["temporalRole"] = "HISTORICAL"
        quality["valueKinds"] = ["FORECAST", "DERIVED"]
        quality["unknownReasons"] += ["Provider model-run origin is not supplied; response receipt is availability, not forecast origin.",
            "Past-days forecast API backfill is not station observation or verification truth."]
    if not days:
        quality["unknownReasons"].append("No finite daily values were parsed from the selected cache; requested ports/variables are not coverage.")
    return quality


def quality_for_weather_source(source_name, legacy_record):
    """Project known registered daily sources without collection or side effects."""
    from src.ingestion.connectors import weather_live
    legacy_record = legacy_record if isinstance(legacy_record, dict) else {}
    if source_name == "Weather history (Open-Meteo ERA5 archive)":
        return _daily(weather_live.ARCHIVE_CACHE, legacy_record, "history")
    if source_name != "Marine weather (Open-Meteo)":
        return None
    surface = _daily(weather_live.FORECAST_CACHE, legacy_record, "surface")
    marine = _daily(weather_live.MARINE_CACHE, legacy_record, "marine")
    quality = _base(legacy_record, None, "MIXED", "CALCULATION_INPUT")
    quality["valueKinds"] = ["FORECAST", "DERIVED"]
    quality["components"] = [surface, marine]
    known_ports = sorted(set((surface["coverage"]["portCodes"] or []) + (marine["coverage"]["portCodes"] or [])))
    unknown_ports = surface["coverage"]["portCodes"] is None or marine["coverage"]["portCodes"] is None
    quality["coverage"].update(portCodes=known_ports if known_ports or not unknown_ports else None,
        variables=sorted(set(surface["coverage"]["variables"] + marine["coverage"]["variables"])),
        datePrecision="DATE_ONLY" if surface["coverage"]["datePrecision"] == "DATE_ONLY" or marine["coverage"]["datePrecision"] == "DATE_ONLY" else "UNKNOWN")
    quality["units"] = surface["units"] + marine["units"]
    quality["sourceReceipts"] = surface["sourceReceipts"] + marine["sourceReceipts"]
    quality["quality"]["rowCount"] = surface["quality"]["rowCount"]
    quality["quality"]["issues"] = surface["quality"]["issues"] + marine["quality"]["issues"]
    quality["receipt"].update(lastFetchedAt=max((q["receipt"]["lastFetchedAt"] for q in (surface, marine) if q["receipt"]["lastFetchedAt"]), default=None),
        lastCheckedAt=max((q["receipt"]["lastCheckedAt"] for q in (surface, marine) if q["receipt"]["lastCheckedAt"]), default=None))
    statuses = {q["receipt"]["status"] for q in (surface, marine)}
    quality["receipt"]["status"] = "UNAVAILABLE" if statuses == {"UNAVAILABLE"} else "STALE" if "STALE" in statuses or "UNAVAILABLE" in statuses else "CACHED_LIVE"
    quality["unknownReasons"] += sorted(set(surface["unknownReasons"] + marine["unknownReasons"])) + [
        "This legacy aggregate combines distinct surface and marine products; inspect components/sourceReceipts for each original.",
        "Any ERA5 training segment concatenated into the legacy frame remains separately identified by the Weather history source; no one original covers the entire aggregate."]
    quality["semantics"].update(dataKind="MIXED_FORECAST_AND_PROVIDER_BACKFILL", consumerRole="Daily raw weather features for WeatherExpert/TFT calculations; not the independent hourly approach gate.",
        legacyDeclaredStatus=legacy_record.get("status"), receiptStatusMeaning="Aggregate of component receipt availability; parsed data and original receipt identity are distinct. Inspect each component for partial availability.")
    quality["unknownReasons"] = sorted(set(quality["unknownReasons"]))
    return quality


def current_weather_products():
    """Current hourly surface/marine rows from retained snapshots; never fetch.

    A multi-port product retains per-port receipts rather than claiming a
    single original or application receipt covers the whole product.
    """
    result = []
    now = datetime.now(timezone.utc)
    # Existing immutable archive receipts establish when an exact port/product
    # response was first seen, even if a later refresh returned identical bytes.
    first_versions = {}
    for path in (receipts.archive_root() / "archive").glob("*.json"):
        body = receipts.read_json(path)
        if not body or not isinstance(body.get("kind"), str) or body["kind"] not in {"surface", "marine"}:
            continue
        at = _iso(body.get("availableAt"))
        identity = body.get("snapshotId")
        if not at or datetime.fromisoformat(at) > now or not isinstance(identity, str):
            continue
        canonical = {key: value for key, value in body.items() if key != "snapshotId"}
        if hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest() != identity:
            continue
        port_code, digest = body.get("portCode"), body.get("responseSha256")
        expected_url = "https://api.open-meteo.com/v1/forecast" if body["kind"] == "surface" else "https://marine-api.open-meteo.com/v1/marine"
        if not isinstance(port_code, str) or not port_registry.resolve(port_code) or not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest) or body.get("source") != expected_url:
            continue
        key = (body["kind"], port_code, digest)
        if key not in first_versions or at < first_versions[key]:
            first_versions[key] = at
    for kind, title in (("surface", "Current surface weather (Open-Meteo)"), ("marine", "Current marine weather (Open-Meteo)")):
        snapshots = []
        for path in sorted(receipts.archive_root().glob(kind + "-*.json")):
            snapshot = receipts.read_json(path)
            if not snapshot or snapshot.get("kind") != kind:
                continue
            port_code = snapshot.get("portCode")
            port = port_registry.resolve(port_code) if isinstance(port_code, str) else None
            if not port or path.name != f"{kind}-{port.locode}.json":
                continue
            snapshots.append((port, snapshot))
        if not snapshots:
            continue
        product = f"open-meteo:{kind}:hourly-v1"
        quality = _base({}, product, "FORECAST", "CALCULATION_INPUT" if kind == "surface" else "CONTEXT_ONLY")
        quality["provenance"]["derivationVersion"] = "current-environment-hourly-v1"
        quality["valueKinds"] = ["FORECAST"]
        quality["coverage"]["datePrecision"] = "INSTANT"
        variables, ports, times, supplied_count = set(), set(), [], 0
        units_by_field = {}
        ages = []
        for port, snapshot in snapshots:
            fields = {"wind_speed_10m", "wind_gusts_10m", "wind_direction_10m", "precipitation", "visibility"} if kind == "surface" else {"wave_height"}
            rows = snapshot.get("rows") if isinstance(snapshot.get("rows"), list) else []
            expected_url = "https://api.open-meteo.com/v1/forecast" if kind == "surface" else "https://marine-api.open-meteo.com/v1/marine"
            identity = snapshot.get("snapshotId")
            canonical = {k: v for k, v in snapshot.items() if k != "snapshotId"}
            declared_at = _iso(snapshot.get("availableAt"))
            identity_valid = (isinstance(identity, str) and identity == hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
                and snapshot.get("source") == expected_url and declared_at is not None
                and datetime.fromisoformat(declared_at) <= now)
            if not identity_valid:
                quality["quality"]["issues"].append(f"{port.locode}: snapshot identity, provider product, or application receipt clock is invalid; parsed coverage quarantined.")
                quality["sourceReceipts"].append({"schemaVersion": 1, "sourceProductId": product,
                    "sourceReceiptId": None, "declaredPortCode": port.locode, "portCode": None,
                    "provider": "Open-Meteo", "fetchedAt": None, "checkedAt": None, "firstAvailableAt": None,
                    "originalRef": None, "originalHash": None, "parserVersion": "current-environment-hourly-v1",
                    "parseStatus": "REJECTED", "issues": ["Invalid receipt identity/provider/clock; no physical or product coverage asserted."]})
                continue
            port_supplied = False
            port_variables = set()
            for row in rows:
                if not isinstance(row, dict) or not _iso(row.get("validAt")):
                    continue
                supplied = {f for f in fields if finite(row.get(f))}
                if supplied:
                    port_supplied = True
                    variables.update(supplied)
                    port_variables.update(supplied)
                    times.append(row["validAt"])
                    supplied_count += 1
            if port_supplied:
                ports.add(port.locode)
            source_units = snapshot.get("units") if isinstance(snapshot.get("units"), dict) else {}
            for field in fields & port_variables:
                unit = source_units.get(field)
                if isinstance(unit, str):
                    expected_unit = {"wind_speed_10m": "kn", "wind_gusts_10m": "kn", "wind_direction_10m": "°",
                        "precipitation": "mm", "visibility": "m", "wave_height": "m"}[field]
                    units_by_field[(field, unit)] = {"variable": field, "sourceVariable": field,
                        "sourceUnit": unit, "outputUnit": unit, "statistic": "HOURLY_FORECAST_SAMPLE",
                        "aggregation": "Hourly provider sample", "aggregationWindow":
                            "Preceding-hour accumulation at UTC label." if field == "precipitation" else "Hourly UTC label; provider variable definition applies.",
                        "derivation": "Identity: retained forecast sample; no unit conversion in this product projection.",
                        "parserVersion": "current-environment-hourly-v1", "rawOrDerived": "RAW",
                        "unitContractVerified": unit == expected_unit}
                    if unit != expected_unit:
                        quality["quality"]["issues"].append(f"{port.locode} {field}: expected {expected_unit}, retained unit is {unit}.")
            at = declared_at
            if at:
                ages.append(max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(at)).total_seconds()))
            digest = snapshot.get("responseSha256")
            original = None
            if isinstance(digest, str) and re.fullmatch("[a-f0-9]{64}", digest):
                try:
                    raw = (receipts.archive_root() / "archive" / (digest + ".response")).read_bytes()
                    source = json.loads(raw)
                    if not isinstance(source, dict):
                        raise ValueError("Hourly source must be an object")
                    hourly = source.get("hourly")
                    units = source.get("hourly_units")
                    if not isinstance(hourly, dict) or not isinstance(units, dict):
                        raise ValueError("Missing original sample blocks")
                    raw_times = hourly.get("time")
                    if not isinstance(raw_times, list):
                        raise ValueError("Missing original sample times")
                    raw_rows = {str(value): i for i, value in enumerate(raw_times)}
                    samples_match = True
                    for row in rows:
                        label = row.get("validAt", "")[:16]
                        index = raw_rows.get(label)
                        for field in fields:
                            values = hourly.get(field)
                            value = values[index] if index is not None and isinstance(values, list) and index < len(values) else None
                            expected = value if finite(value) else None
                            if row.get(field) != expected or snapshot.get("units", {}).get(field) != units.get(field):
                                samples_match = False
                    if identity_valid and samples_match and hashlib.sha256(raw).hexdigest() == digest:
                        original = "sha256:" + digest
                except (OSError, ValueError, TypeError, AttributeError):
                    pass
            if not original:
                quality["unknownReasons"].append(f"{port.locode}: exact original missing or hash check failed; parsed snapshot remains inspectable.")
            first_at = first_versions.get((kind, port.locode, digest), at) if identity_valid else None
            quality["sourceReceipts"].append({"schemaVersion": 1, "sourceProductId": product,
                "sourceReceiptId": identity if identity_valid else None,
                "portCode": port.locode, "provider": "Open-Meteo", "fetchedAt": at, "checkedAt": None,
                "firstAvailableAt": first_at, "originalRef": original, "originalHash": digest if original else None,
                "parserVersion": "current-environment-hourly-v1", "parseStatus": "ACCEPTED" if port_supplied else "REJECTED",
                "issues": [] if port_supplied else ["No finite hourly values supplied."],
                "requestedLocation": {"latitude": snapshot["request"].get("latitude"), "longitude": snapshot["request"].get("longitude")}
                    if isinstance(snapshot.get("request"), dict) and finite(snapshot["request"].get("latitude")) and finite(snapshot["request"].get("longitude")) else None})
        quality["coverage"].update(portCodes=sorted(ports), variables=sorted(variables),
            targetFrom=min(times) if times else None, targetThrough=max(times) if times else None)
        quality["quality"]["rowCount"] = supplied_count
        quality["units"] = list(units_by_field.values())
        ats = [r["fetchedAt"] for r in quality["sourceReceipts"] if r["fetchedAt"]]
        quality["receipt"].update(lastFetchedAt=max(ats) if ats else None,
            status=("CACHED_LIVE" if max(ages) <= 3600 else "STALE") if ages else "UNAVAILABLE")
        quality["semantics"].update(dataKind="MODEL_FORECAST", sourceTimePrecision="INSTANT",
            consumerRole="Hourly gust/visibility thresholds are calculation inputs; other hourly surface fields are context." if kind == "surface" else
                "Offshore wave forecast is context; it does not enter the current gust/visibility gate.",
            rawOrDerived="RAW_FORECAST_SAMPLES")
        quality["unknownReasons"] += ["Forecast issue/publication time is not supplied; receipt is first application availability.",
            "Last check is unknown: the existing hourly archive retains receipt time but does not record read checks.",
            "Multi-port product has separate per-port originals in sourceReceipts; aggregate original/receipt identity remains null.",
            "Forecasts are gridded model values, not station measurements or provider backfill used as truth."]
        result.append({"source": title, "provider": "Open-Meteo", "status": quality["receipt"]["status"],
            "detail": "Retained hourly forecast product; source-quality projection performs no collection.",
            "fetched_at": quality["receipt"]["lastFetchedAt"], "observed_at": None,
            "rows": supplied_count, "confidence": 0.0, "ageHours": None, "age_seconds": None,
            "isReal": quality["receipt"]["status"] in {"CACHED_LIVE", "STALE"}, "freshness_budget_hours": 1.0,
            "recorded_at": quality["receipt"]["lastFetchedAt"],
            "fallback": "retained public forecast snapshot", "sourceQuality": quality})
    return result
