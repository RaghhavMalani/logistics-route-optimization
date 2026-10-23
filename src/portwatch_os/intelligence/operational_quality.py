"""Read-only source-quality views over the existing public operational archives.

Nothing in this projection collects data, opens a visitor ledger, writes a cache,
or changes a source's numerical weight. Legacy CSVs are parsed derivatives, not
substitutes for missing original provider responses.
"""
from __future__ import annotations

import copy
import csv
import json
import math
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from src.portwatch_os.intelligence import operational_feed as feed
from src.portwatch_os.intelligence.public_ports import (
    CHENNAI_ETA, CHENNAI_POSITION, PORTS, PublicPilot, approved, digest, parse_pdf, stamp,
)
from src.utils import port_registry
from src.utils.config import DATA_DIR, STATE_DIR

VERSION = "operational-source-quality-v1"
IMF_PRODUCT = "imf-portwatch-data"
IMF_DERIVATION = "imf-portwatch-daily-aggregate-v1"
LEGACY_DERIVATION = "portwatch-source-csv-v1"
_PUBLIC = {
    ("INMAA", "expected"): ("Chennai published expected arrivals", "chennai-expected-arrivals"),
    ("INMAA", "position"): ("Chennai published vessel position", "chennai-vessel-position"),
    ("INPRT", "traffic"): ("Paradip published daily traffic", "paradip-daily-traffic"),
}
_HASH = re.compile(r"[0-9a-f]{64}")
_STATUS = {"LIVE", "CACHED_LIVE", "STALE", "SYNTHETIC", "UNAVAILABLE"}


def _now(now=None):
    value = now or datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Source quality requires an aware clock")
    return value.astimezone(timezone.utc)


def _instant(value):
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def _day(value):
    try:
        return date.fromisoformat(value).isoformat() if isinstance(value, str) else None
    except ValueError:
        return None


def _finite(value):
    try:
        return value is not None and str(value).strip() != "" and math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _base(status="UNAVAILABLE", *, provider=None, product=None, version=None):
    return {"schemaVersion": 1, "projectionVersion": VERSION, "temporalRole": "UNKNOWN",
        "valueKinds": ["UNKNOWN"], "operationalUse": "CONTEXT_ONLY",
        "receipt": {"lastFetchedAt": None, "lastCheckedAt": None,
            "status": status if status in _STATUS else "UNAVAILABLE", "fallback": None},
        "coverage": {"portCodes": [], "variables": [], "observedFrom": None,
            "observedThrough": None, "observationAgeSeconds": None,
            "observationFreshnessBudgetSeconds": None, "forecastOriginAt": None,
            "targetFrom": None, "targetThrough": None, "datePrecision": "UNKNOWN"},
        "provenance": {"provider": provider, "sourceProductId": product,
            "sourceReceiptId": None, "originalRef": None, "originalHash": None,
            "derivationVersion": version},
        "quality": {"rowCount": None, "confidence": None, "completeness": None,
            "missingFields": [], "issues": []}, "unknownReasons": [],
        "semantics": {"calibratedAccuracy": False,
            "confidenceMeaning": "No calibrated accuracy score is supplied; legacy status multipliers remain unchanged.",
            "calculationEffect": "NONE", "firstAvailableAt": None,
            "publishedAt": None, "sourceUnits": {}, "outputUnits": {}},
        "requestedCoverage": {"portCodes": None, "variables": None}}


def _source(name, quality, detail):
    receipt, coverage = quality["receipt"], quality["coverage"]
    status = quality["semantics"].get("productObservationStatus", receipt["status"])
    return {"source": name, "status": status,
        "provider": quality["provenance"]["provider"] or "", "detail": detail,
        "observed_at": coverage["observedThrough"], "fetched_at": receipt["lastFetchedAt"],
        "age_seconds": coverage["observationAgeSeconds"],
        "freshness_budget_hours": 36, "confidence": 0.0, "fallback": receipt["fallback"],
        "rows": quality["quality"]["rowCount"], "recorded_at": receipt["lastCheckedAt"],
        "isReal": status in ("LIVE", "CACHED_LIVE", "STALE"),
        "ageHours": None, "sourceQuality": quality}


def _unverified(quality, reason):
    """Do not leave partly assigned identity/coverage after a malformed row."""
    quality["receipt"].update(status="UNAVAILABLE", lastFetchedAt=None)
    quality["coverage"].update(portCodes=[], variables=[], observedFrom=None,
        observedThrough=None, observationAgeSeconds=None, forecastOriginAt=None,
        targetFrom=None, targetThrough=None, datePrecision="UNKNOWN")
    quality["provenance"].update(sourceReceiptId=None, originalRef=None, originalHash=None)
    quality["quality"].update(rowCount=None, confidence=None, completeness=None)
    quality["quality"]["issues"].append("RETAINED_EVIDENCE_UNVERIFIED")
    quality["semantics"].update(firstAvailableAt=None, originalHashVerified=False)
    for field in ("receiptReference", "receiptHistory", "revisionLineage", "parserLineage", "eventPeriods", "productObservationStatus"):
        quality["semantics"].pop(field, None)
    quality["unknownReasons"].append(reason)
    return quality


def _pilot_root():
    return Path(STATE_DIR) / "public_port_pilot"


@contextmanager
def _public_archive():
    """Reuse the current reader methods without constructor DDL or mkdir."""
    root = _pilot_root()
    path = root / "public_ports.db"
    if not path.is_file():
        yield None
        return
    store = PublicPilot.__new__(PublicPilot)
    store.root, store.lock = root, threading.RLock()
    store.db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    store.db.row_factory = sqlite3.Row
    try:
        yield store
    finally:
        store.db.close()


def _aggregate_archive():
    """An absent archive remains absent on reads."""
    archive = feed.AggregateArchive.__new__(feed.AggregateArchive)
    archive.root, archive.lock = _pilot_root() / "aggregate_activity", threading.RLock()
    return archive


def _valid_aggregate_receipt(row, port):
    """Check the archive's immutable receipt tuple, including its legacy None."""
    if not isinstance(row, dict) or row.get("portCode") != port or not _instant(row.get("receivedAt")):
        return False
    sha = row.get("sha256")
    if not isinstance(sha, str) or not _HASH.fullmatch(sha):
        return False
    queries = [row.get("query")]
    if row.get("query") == {}:
        queries.append(None)
    expected = {digest(json.dumps([sha, row["receivedAt"], port, query], sort_keys=True)) for query in queries}
    return row.get("receiptId") in expected


def _aggregate_quality(port, now):
    quality = _base(provider="IMF PortWatch", product=IMF_PRODUCT, version=IMF_DERIVATION)
    quality["temporalRole"], quality["valueKinds"] = "HISTORICAL", ["DERIVED"]
    quality["requestedCoverage"] = {"portCodes": [port], "variables": ["portcalls"],
        "physicalPortIds": [feed.IMF_PORTS[port]],
        "basis": "Approved collector/parser scope; actual supplied coverage is reported separately."}
    quality["coverage"]["datePrecision"] = "DATE_ONLY"
    quality["semantics"].update({"measurementKind": "AGGREGATE_AIS_DERIVED_PORT_ACTIVITY",
        "aggregation": "DAILY", "statistic": "COUNT", "sourceUnits": {"portcalls": "calls/day"},
        "outputUnits": {"portcalls": "calls/day"}, "originalHashVerified": False,
        "meaning": "Aggregate daily AIS-derived port activity, not an individual arrival, berth, all-fast or visitor vessel outcome.",
        "physicalPortMapping": [{"sourcePortId": feed.IMF_PORTS[port], "portCode": port}],
        "observationClockMeaning": "Provider daily date only; midnight is not a measured or publication instant."})
    quality["unknownReasons"] = ["Exact observation and provider publication instants are unavailable.",
        "Trade import/export units are not verified by this retained parser; no trade-value coverage is asserted."]
    try:
        archive = _aggregate_archive()
        receipts = archive.receipts(now, port)
        check = archive.last_check(port, now)
        latest = receipts[-1] if receipts else None
        checked = check.get("checkedAt") if check else (latest.get("receivedAt") if latest else None)
        quality["receipt"]["lastCheckedAt"] = checked if _instant(checked) else None
        # A failed latest attempt may coexist with an older, inspectable original.
        if (check and check.get("errors")) or (latest and latest.get("errors")):
            quality["quality"]["issues"].append("Latest collection attempt failed; retained successful evidence may be older.")
        selected = next((row for row in reversed(receipts) if row.get("records") and not row.get("errors")), None)
        if selected is None:
            quality["unknownReasons"].append("No usable retained IMF aggregate response is available.")
            return quality
        received, sha = selected["receivedAt"], selected["sha256"]
        if not _valid_aggregate_receipt(selected, port):
            raise ValueError("Receipt identity is inconsistent")
        archive.evidence(selected, now)
        dates = sorted({_day(row["date"]) for row in selected["records"]})
        if not dates or None in dates:
            raise ValueError("Invalid daily date")
        # Reconstruct first receipt of these exact bytes from actual receipt rows.
        valid_receipts = [row for row in receipts if _valid_aggregate_receipt(row, port)]
        first = min(row["receivedAt"] for row in valid_receipts if row["sha256"] == sha)
        quality["receipt"].update(lastFetchedAt=received, status="CACHED_LIVE")
        quality["provenance"].update(sourceReceiptId=selected["receiptId"],
            originalRef=feed.IMF_ENDPOINT, originalHash=sha)
        quality["coverage"].update(portCodes=[port], variables=["portcalls"],
            observedFrom=dates[0], observedThrough=dates[-1])
        quality["quality"]["rowCount"] = len(selected["records"])
        quality["semantics"].update(firstAvailableAt=first, originalHashVerified=True,
            receiptReference={"product": "IMF_PORTWATCH_DAILY", "portCode": port, "receiptId": selected["receiptId"]},
            receiptHistory=[{"sourceReceiptId": row["receiptId"], "originalHash": row["sha256"],
                "receivedAt": row["receivedAt"]} for row in valid_receipts if row["receivedAt"] <= received],
            revisionLineage=None,
            receiptHistoryMeaning="Retained response receipts, including identical repeats and changed query windows; not a claim-level revision adjudication.",
            firstAvailableAtMeaning="First application receipt of this exact original response; not provider publication or first availability of every daily observation.",
            sourceCheckStatus="FAILED" if quality["quality"]["issues"] else "AVAILABLE",
            receiptFreshnessBudgetSeconds=24*3600,
            observationFreshnessPolicy="Current or previous UTC daily source date; no exact daily observation instant.")
        if (now - _instant(received)).total_seconds() > 24*3600:
            quality["receipt"]["status"] = "STALE"
        quality["unknownReasons"].append("Date-only observations do not support an exact age in seconds; daily source age is reported separately.")
        quality["semantics"]["observationAgeDays"] = (now.date() - date.fromisoformat(dates[-1])).days
        quality["semantics"]["productObservationStatus"] = "STALE" if quality["semantics"]["observationAgeDays"] > 1 else "CACHED_LIVE"
        return quality
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error, OverflowError):
        return _unverified(quality, "Retained IMF aggregate metadata/original failed verification; no original receipt or coverage is asserted.")


def _public_quality(store, port, kind, now):
    name, product = _PUBLIC[(port, kind)]
    quality = _base(provider="Chennai Port Authority" if port == "INMAA" else "Paradip Port Authority",
        product=product)
    quality["requestedCoverage"] = {"portCodes": [port], "variables": ["etaAt"] if kind == "expected" else ["arrivalAt", "berthAt", "berthRef"]}
    quality["semantics"].update(measurementKind="PUBLISHER_REPORTED_PORT_EVENTS",
        confirmedAllFast=False, originalHashVerified=False,
        meaning="Published ETA, reported arrival and reported berth are separate fields; no confirmed all-fast or visitor-vessel link is inferred.")
    quality["unknownReasons"] = ["Precise provider publication time and publisher definitions of arrival/berth are unavailable.",
        "Timezone Asia/Kolkata is a parser assumption; report dates remain date-only.",
        "Confirmed all-fast and individual visitor-vessel identity are unavailable."]
    if store is None:
        quality["unknownReasons"].append("No public-port retention store is available.")
        return quality
    try:
        checks = store.db.execute("SELECT at, body FROM checks WHERE port=? AND at<=? ORDER BY id DESC LIMIT 1", (port, stamp(now))).fetchone()
        if checks:
            quality["receipt"]["lastCheckedAt"] = checks["at"] if _instant(checks["at"]) else None
            check = json.loads(checks["body"])
            if check.get("errors"):
                quality["quality"]["issues"].append("Latest public-port collection check failed; retained original remains separate.")
        snapshots = [s for s in store.snapshots(port, now) if s["kind"] == kind]
        if not snapshots:
            quality["unknownReasons"].append("No retained original for this public-port product is available.")
            return quality
        selected = snapshots[-1]
        sha, key = selected["sha256"], selected["snapshotId"]
        source_url = selected["sourceUrl"]
        exact_chennai = CHENNAI_ETA if kind == "expected" else CHENNAI_POSITION
        if (not _HASH.fullmatch(sha) or key != digest(port + kind + sha) or not approved(source_url)
                or (port == "INMAA" and source_url != exact_chennai)
                or (port == "INPRT" and "paradipport.gov.in" not in source_url)):
            raise ValueError("Invalid public-port evidence identity")
        original = store.evidence(port, key, now)
        parsed = parse_pdf(original.read_bytes(), port, kind)
        retained_rows = [{k: v for k, v in row.items() if k != "recordAvailableAt"} for row in selected["records"]]
        if parsed["records"] != retained_rows or parsed["reportDate"] != selected["reportDate"]:
            raise ValueError("Retained public-port fields differ from the reviewed parser")
        report_day = _day(selected["reportDate"])
        if not report_day or date.fromisoformat(report_day) > now.date():
            raise ValueError("Invalid report day")
        fields = ["etaAt", "arrivalAt", "berthAt", "berthRef", "loa", "beam", "draft"]
        variables = [field for field in fields if any(row.get(field) is not None and row.get(field) != "" for row in retained_rows)]
        events = {field: sorted({_instant(row.get(field)).isoformat() for row in retained_rows
                if _instant(row.get(field)) and (field == "etaAt" or _instant(row.get(field)) <= now)})
            for field in ("etaAt", "arrivalAt", "berthAt")}
        if any(_instant(row.get(field)) and _instant(row[field]) > now
                for row in retained_rows for field in ("arrivalAt", "berthAt")):
            quality["quality"]["issues"].append("FUTURE_REPORTED_EVENT_WITHHELD: future arrival/berth clocks are not treated as observed outcomes.")
        observed_events = sorted(events["arrivalAt"] + events["berthAt"])
        check_failed = any("Latest public-port collection check failed" in issue for issue in quality["quality"]["issues"])
        checked_or_received = _instant(quality["receipt"]["lastCheckedAt"]) if not check_failed else None
        reference = checked_or_received or _instant(selected["firstSeenAt"])
        status = "STALE" if not reference or (now-reference).total_seconds() > 36*3600 else "CACHED_LIVE"
        quality["receipt"].update(status=status, lastFetchedAt=selected["firstSeenAt"])
        quality["provenance"].update(sourceReceiptId=key, originalRef=selected["sourceUrl"],
            originalHash=sha, derivationVersion=selected["parserVersion"])
        quality["coverage"].update(portCodes=[port] if retained_rows else [], variables=variables,
            datePrecision="INSTANT" if observed_events or events["etaAt"] else "UNKNOWN",
            observedFrom=observed_events[0] if observed_events else None,
            observedThrough=observed_events[-1] if observed_events else None,
            targetFrom=events["etaAt"][0] if events["etaAt"] else None,
            targetThrough=events["etaAt"][-1] if events["etaAt"] else None)
        quality["temporalRole"] = "FORECAST" if kind == "expected" else ("MIXED" if events["etaAt"] else "HISTORICAL")
        quality["valueKinds"] = ["FORECAST"] if kind == "expected" else (["OBSERVED", "FORECAST"] if events["etaAt"] else ["OBSERVED"])
        quality["quality"]["rowCount"] = len(retained_rows)
        quality["quality"]["missingFields"] = [field for field in fields if field not in variables]
        quality["quality"]["issues"] += ["Parser issue: " + str(issue.get("code", "UNSPECIFIED")) for issue in selected["issues"]]
        quality["semantics"].update(firstAvailableAt=selected["firstSeenAt"], originalHashVerified=True,
            firstAvailableAtMeaning="First application receipt of this exact original PDF; parser availability is separate.",
            reportDate=report_day, reportDatePrecision="DATE_ONLY", eventDatePrecision="INSTANT_ASSUMED_TIMEZONE",
            reportAgeDays=(now.date() - date.fromisoformat(report_day)).days,
            productObservationStatus="STALE" if (now.date()-date.fromisoformat(report_day)).days > 1 else "CACHED_LIVE",
            receiptFreshnessBudgetSeconds=36*3600, sourceCheckStatus="FAILED" if check_failed else "AVAILABLE",
            receiptReference={"product": "PUBLIC_PORT_PDF", "portCode": port, "snapshotId": key},
            sourceUnits={"loa": "m", "beam": "m", "draft": "m"}, outputUnits={"loa": "m", "beam": "m", "draft": "m"},
            parserAvailableAt=selected["parsedAt"], parserLineage=copy.deepcopy(selected["parseHistory"]),
            eventPeriods={field: {"from": values[0], "through": values[-1]} if values else None for field, values in events.items()},
            rawVersusDerived="Publisher-reported fields normalized by the reviewed PDF parser; event clocks converted under the stated timezone assumption.")
        return quality
    except Exception:
        # Optional diagnostics must also survive provider-specific PDF parser
        # exceptions. Never publish exception text, which may contain a path.
        return _unverified(quality, "Retained public-port metadata/original failed verification; source coverage and original identity remain unknown.")


def _legacy_activity_rows(now):
    """Parse supplied non-null values only, without pipeline fill/zero operations."""
    folder = Path(DATA_DIR) / "portwatch"
    files = [(path, path.stem) for path in sorted((folder / "history").glob("*.csv"))]
    files.append((folder / "port_activity.csv", None))
    result = {}
    for path, physical in files:
        if not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8-sig", newline="") as stream:
                for raw in csv.DictReader(stream):
                    source_id, day = physical or raw.get("portid"), _day(raw.get("date"))
                    mapped = next((port for port in port_registry.PORTS if source_id in port.portwatch_ids), None)
                    if not day or not mapped or date.fromisoformat(day) > now.date():
                        continue
                    values = {field: float(raw[field]) for field in ("portcalls", "import", "export") if _finite(raw.get(field))}
                    if values:
                        result.setdefault((source_id, day), {"sourcePortId": source_id, "portCode": mapped.locode,
                            "date": day, "values": values})
        except (OSError, UnicodeError, csv.Error):
            continue
    return list(result.values())


def _legacy_quality(now, *, port=None, legacy=None):
    rows = [row for row in _legacy_activity_rows(now) if port is None or row["portCode"] == port]
    status = (legacy or {}).get("status", "CACHED_LIVE")
    quality = _base(status if rows else "UNAVAILABLE", provider="IMF PortWatch", product=IMF_PRODUCT,
        version=LEGACY_DERIVATION)
    quality["temporalRole"], quality["valueKinds"] = "HISTORICAL", ["DERIVED"]
    quality["operationalUse"] = "CALCULATION_INPUT"
    dates = sorted({row["date"] for row in rows})
    variables = sorted({field for row in rows for field in row["values"]})
    quality["coverage"].update(portCodes=sorted({row["portCode"] for row in rows}), variables=variables,
        observedFrom=dates[0] if dates else None, observedThrough=dates[-1] if dates else None,
        datePrecision="DATE_ONLY" if dates else "UNKNOWN")
    quality["quality"].update(rowCount=len(rows), missingFields=[field for field in ("portcalls", "import", "export") if field not in variables])
    quality["semantics"].update(measurementKind="AGGREGATE_AIS_DERIVED_PORT_ACTIVITY",
        aggregation="DAILY", calculationEffect="UNCHANGED_LEGACY_PIPELINE",
        operationalRole="Legacy daily activity feeds the port-ops expert and derived training targets; it does not enter the hourly weather approach gate.",
        sourceUnits={"portcalls": "calls/day", "import": None, "export": None},
        outputUnits={"portcalls": "calls/day", "import": None, "export": None},
        originalHashVerified=False, retainedArtifactKind="PARSED_LEGACY_CSV",
        suppliedValueCounts={field: sum(field in row["values"] for row in rows) for field in variables},
        physicalPortMapping=[{"sourcePortId": source_id, "portCode": code} for source_id, code in sorted({(row["sourcePortId"], row["portCode"]) for row in rows})],
        meaning="Daily aggregate port activity. Legacy pipeline congestion, utilization and berth-wait hours are derived proxies, not measured vessel waiting or confirmed all-fast.",
        parserRule="History precedes overlapping snapshot rows per physical port/date; coverage counts supplied finite values, before dense-grid/zero filling.",
        derivations={"congestion_index": "50 * trailing-seven-day calls / shifted expanding baseline, clipped 0..100",
            "delay_hours": "4 + 18 * clipped excess call-pressure ratio (0..2); assumed hours proxy",
            "throughput": "Trailing-seven-day import+export sum mean; raw trade units require provider verification",
            "utilization": "Trailing calls / shifted historical peak; derived ratio"})
    quality["unknownReasons"] = ["Only parsed legacy CSV values are retained here; the original historical provider response, receipt ID, byte hash and actual first application receipt are unknown.",
        "Legacy fetched_at/recorded_at and file modification times cannot establish an original response receipt or publication instant.",
        "Provider observation dates are date-only; exact observation time and second-level age are unknown.",
        "Raw import/export units and provider revision lineage are not established by the CSV alone.",
        "Legacy status-confidence multipliers are heuristic readiness values, not calibrated source accuracy."]
    quality["receipt"]["fallback"] = "Parsed legacy CSV; original response unavailable"
    if dates:
        age = (now.date() - date.fromisoformat(dates[-1])).days
        quality["semantics"]["observationAgeDays"] = age
        if age > 1 and quality["receipt"]["status"] in ("LIVE", "CACHED_LIVE"):
            quality["receipt"]["status"] = "STALE"
    return quality


def quality_for_activity_source(source_name, legacy_record):
    """Known pipeline IMF activity only; never relabel observed/simulated AIS."""
    record = legacy_record if isinstance(legacy_record, dict) else {}
    provider = str(record.get("provider", "")).lower()
    name = str(source_name or "").lower()
    if "imf" not in provider and "portwatch" not in provider:
        return None
    if not any(word in name for word in ("activity", "ais", "port calls", "port-call")):
        return None
    if record.get("status") not in ("LIVE", "CACHED_LIVE", "STALE"):
        return None
    return _legacy_quality(_now(), legacy=record)


def operational_source_rows(now=None):
    """Legacy-compatible rows with additive quality, never collection-on-read."""
    now = _now(now)
    result = [_source("IMF PortWatch daily aggregate / " + port, _aggregate_quality(port, now),
        "Retained daily aggregate response; context only, independent of current weather.") for port in feed.IMF_PORTS]
    try:
        with _public_archive() as store:
            result.extend(_source(name, _public_quality(store, port, kind, now),
                "Publisher port-report context; ETA, arrival and berth are separate from confirmed all-fast.")
                for (port, kind), (name, _) in _PUBLIC.items())
    except (OSError, sqlite3.Error):
        result.extend(_source(name, _public_quality(None, port, kind, now), "Public-port archive unavailable.")
            for (port, kind), (name, _) in _PUBLIC.items())
    return result


def freeze_activity_context(port_code, now=None):
    """Freeze only the selected port's actual activity identity, with zero effect.

    Last-check time, wall-clock age and unrelated sources are intentionally absent
    so metadata/check refreshes cannot alter an existing comparison's dependency.
    Existing frozen records are never opened or rewritten by this helper.
    """
    now = _now(now)
    port = port_registry.resolve(port_code)
    code = port.locode if port else str(port_code or "")
    quality = _aggregate_quality(code, now) if code in feed.IMF_PORTS else None
    if not quality or not quality["provenance"]["originalHash"]:
        quality = _legacy_quality(now, port=code)
    coverage, provenance, semantics = quality["coverage"], quality["provenance"], quality["semantics"]
    reason = None if provenance["originalHash"] and coverage["observedThrough"] else (
        "Actual parsed daily activity is available, but original provider response/receipt/hash/first availability are unknown."
        if coverage["observedThrough"] else "No supported activity snapshot is available for this physical port.")
    return {"schemaVersion": 1, "projectionVersion": VERSION, "operationalUse": "CONTEXT_ONLY",
        "calculationEffect": "NONE", "portCode": code, "provider": provenance["provider"],
        "sourceProductId": provenance["sourceProductId"], "sourceVersion": provenance["derivationVersion"],
        "observationDate": coverage["observedThrough"], "observedFrom": coverage["observedFrom"],
        "observedThrough": coverage["observedThrough"], "datePrecision": coverage["datePrecision"],
        "sourceReceiptId": provenance["sourceReceiptId"], "originalRef": provenance["originalRef"],
        "originalHash": provenance["originalHash"], "firstAvailableAt": semantics["firstAvailableAt"],
        "firstAvailableAtMeaning": "First receipt of this exact original response, not provider publication or each observation's first release.",
        "unknownReason": reason,
        "meaning": "Aggregate port activity context only; not an input to the hourly gust/visibility approach gate or a vessel's actual waiting outcome."}
