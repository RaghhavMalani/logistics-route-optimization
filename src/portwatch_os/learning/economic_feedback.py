"""Evidence-qualified DEXINUS reconciliation and read-only, complete-dataset audit.

The CSV's observation date is a date, not an invented UTC measurement instant.
Forecast issue and receipt clocks remain aware instants. These functions neither
fetch providers nor mutate the existing ledger; the shared Outcome Agent owns
resolution and preserves its first-retained scoring vintage.
"""
from __future__ import annotations

import calendar
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path


SERIES = "DEXINUS"
PRODUCT = "FRED_DEXINUS_DAILY"
UNIT = "INR/USD"
STATISTIC = "NEW_YORK_NOON_BUYING_RATE"
SOURCE = "Federal Reserve H.10 via FRED DEXINUS"
SELECTION_POLICY = "DEXINUS_FIRST_RETAINED_COMPATIBLE_DATE_OUTCOME_V2"
INDEPENDENT_POLICY = "EARLIEST_PROSPECTIVE_FORECAST_PER_SERIES_DATE_V1"
METADATA = {
    "series": SERIES, "productId": PRODUCT, "unit": UNIT,
    "baseCurrency": "USD", "quoteCurrency": "INR", "statistic": STATISTIC,
    "observationPrecision": "DATE_ONLY", "frequency": "DAILY",
    "releaseFrequency": "WEEKLY", "seasonalAdjustment": "NOT_SEASONALLY_ADJUSTED",
    "releaseRule": "Normally Monday 16:15 America/New_York for the preceding business week; a federal holiday defers release to the next business day. Expected timing is not a publication guarantee.",
    "sourceUrls": ["https://fred.stlouisfed.org/series/DEXINUS",
                   "https://www.federalreserve.gov/releases/h10/default.htm",
                   "https://www.federalreserve.gov/releases/h10/about.htm"],
    "meaning": "New York noon buying reference rate; neither a closing price nor an executable FX quote. Historical releases may differ from later revised data.",
}


def _instant(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Aware availability/issue time required")
    return parsed.astimezone(timezone.utc)


def _date(value):
    # Accept only a real calendar date, not a timestamp silently truncated.
    return date.fromisoformat(str(value))


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _id(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def observation_date(record):
    """The old midnight `observedAt` was an eligibility label; never use its hour."""
    value = record.get("observationDate") or record.get("target", {}).get("date")
    return _date(value).isoformat() if value else None


def parse_fx_csv(raw):
    """Validate the entire received product before ingesting any of its rows."""
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if reader.fieldnames not in (["observation_date", SERIES], ["DATE", SERIES]):
            raise ValueError("Unexpected DEXINUS CSV schema")
        key = reader.fieldnames[0]
        parsed = {}
        for row in reader:
            if None in row or row.get(SERIES) is None or row.get(key) is None:
                raise ValueError("Malformed DEXINUS CSV row")
            day = _date(row[key]).isoformat()
            text = row[SERIES].strip()
            value = None if text in (".", "", "NA", "ND") else float(text)
            if value is not None and (not _finite(value) or value <= 0):
                raise ValueError("Invalid DEXINUS observation")
            if day in parsed and parsed[day] != value:
                raise ValueError("Conflicting DEXINUS values for one observation date")
            parsed[day] = value
        if not parsed:
            raise ValueError("Empty DEXINUS CSV product")
        return parsed
    except (UnicodeError, csv.Error, TypeError, OverflowError) as exc:
        raise ValueError("Malformed DEXINUS CSV response") from exc


def _raw_status(store, record, root=None):
    digest = record.get("responseSha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        return "MISSING_ORIGINAL", "Retained original hash is missing or invalid"
    receipts = [row for row in store.feedback("receipt") if row.get("responseSha256") == digest
                and row.get("source") == "https://fred.stlouisfed.org/graph/fredgraph.csv"]
    if not receipts:
        return "UNBOUND_SOURCE_PRODUCT", "No retained receipt binds this original to the reviewed FRED DEXINUS product"
    try:
        first_receipt = min(_instant(row.get("firstAvailableAt") or row["receivedAt"]) for row in receipts)
        available = _instant(record["firstAvailableAt"])
        if first_receipt > available:
            return "UNVERIFIED_FIRST_AVAILABILITY", "Observation availability precedes its earliest retained original receipt"
        if record.get("providerPublishedAt") and _instant(record["providerPublishedAt"]) > available:
            return "INVALID_PUBLICATION_AVAILABILITY", "Known provider publication follows the claimed application availability"
    except (ValueError, TypeError, KeyError):
        return "INVALID_RECEIPT_TIME", "Original receipt or observation availability lacks an aware clock"
    for receipt in receipts:
        request = receipt.get("requestMetadata") or {}
        params = request.get("requestParameters") or {}
        if request.get("series", SERIES) != SERIES or params.get("id", SERIES) != SERIES:
            return "INCOMPATIBLE_PRODUCT", "Retained request identifies a different source series"
    if record.get("sourceVersion") != digest:
        return "SOURCE_VERSION_MISMATCH", "The observation's source version does not identify its retained original bytes"
    paths = []
    if root is not None:
        paths.append(Path(root) / "shared_feedback" / (digest + ".response"))
    else:
        from src.portwatch_os.intelligence.current_environment import ROOT
        paths.append(Path(ROOT) / "shared_feedback" / (digest + ".response"))
    # A collector-supplied internal archive path supports separately configured
    # public stores and isolated fixtures. Never expose these paths in the DTO.
    for receipt in receipts:
        if receipt.get("responseSha256") == digest and receipt.get("archivePath"):
            path = Path(receipt["archivePath"])
            if path.name == digest + ".response" and path.parent.name == "shared_feedback":
                paths.append(path)
    if getattr(store, "path", None) and str(store.path) != ":memory:":
        paths.append(Path(store.path).parent / "shared_feedback" / (digest + ".response"))
    existing = [path for path in dict.fromkeys(paths) if path.is_file()]
    if not existing:
        return "MISSING_ORIGINAL", "Hash-identified original response is unavailable"
    valid = [path.read_bytes() for path in existing if hashlib.sha256(path.read_bytes()).hexdigest() == digest]
    if not valid:
        return "CORRUPT_ORIGINAL", "Retained original response failed its SHA-256 check"
    try:
        rows = parse_fx_csv(valid[0])
    except ValueError:
        return "MALFORMED_RESPONSE", "Original is retained but does not parse as the reviewed DEXINUS product"
    day = observation_date(record)
    if day not in rows or rows[day] is None or not _finite(record.get("value")) or rows[day] != record["value"]:
        return "ORIGINAL_ROW_MISMATCH", "Retained date/value does not agree with the original DEXINUS CSV row"
    return None, None


def _nth_weekday(year, month, weekday, nth):
    first = date(year, month, 1)
    return first + timedelta(days=(weekday-first.weekday()) % 7 + 7*(nth-1))


def _observed(day):
    return day - timedelta(days=1) if day.weekday() == 5 else day + timedelta(days=1) if day.weekday() == 6 else day


def _federal_holidays(year):
    holidays = {_observed(date(y, month, day)) for y in (year-1, year, year+1)
                for month, day in ((1, 1), (6, 19), (7, 4), (11, 11), (12, 25))
                if not (month == 6 and y < 2021)}
    holidays.update((_nth_weekday(year, 1, 0, 3), _nth_weekday(year, 2, 0, 3),
                     _nth_weekday(year, 9, 0, 1), _nth_weekday(year, 10, 0, 2),
                     _nth_weekday(year, 11, 3, 4)))
    last_may = date(year, 5, calendar.monthrange(year, 5)[1])
    holidays.add(last_may-timedelta(days=last_may.weekday()))
    return holidays


def expected_release(target_date):
    """Derived check window from the documented rule, not an actual release clock."""
    target = _date(target_date)
    release = target + timedelta(days=7-target.weekday())
    while release.weekday() >= 5 or release in _federal_holidays(release.year):
        release += timedelta(days=1)
    # Current targets are after 2007. Do not pretend this calendar rule covers
    # historical changes to US DST or periods when weekly H.10 ceased publishing.
    if release.year < 2010:
        return {"expectedDate": release.isoformat(), "expectedAt": None, "status": "HISTORICAL_SCHEDULE_NOT_QUALIFIED"}
    dst = _nth_weekday(release.year, 3, 6, 2) <= release < _nth_weekday(release.year, 11, 6, 1)
    hour = 20 if dst else 21
    expected = datetime(release.year, release.month, release.day, hour, 15, tzinfo=timezone.utc)
    return {"expectedDate": release.isoformat(), "expectedAt": expected.isoformat(),
            "localTime": "16:15", "timeZone": "America/New_York",
            "status": "DERIVED_EXPECTED_CHECK_WINDOW", "actualProviderPublishedAt": None,
            "policy": "H10_WEEKLY_PRIOR_BUSINESS_WEEK_US_FEDERAL_HOLIDAY_V1",
            "meaning": "Expected release timing only; provider availability is not guaranteed. Observation dates retain date-only precision."}


def _semantics(record):
    target = record.get("target", {})
    if target.get("kind") != "ECONOMIC_OBSERVATION" or target.get("series") != SERIES:
        return "UNSUPPORTED_SEMANTICS", "Only the reviewed DEXINUS daily observation target is supported"
    if record.get("unit") != UNIT or record.get("baseCurrency", "USD") != "USD" or record.get("quoteCurrency", "INR") != "INR":
        return "INCOMPATIBLE_UNIT_OR_CURRENCY", "DEXINUS requires INR per one USD; inversion is not a matching observation"
    if record.get("aggregation") != STATISTIC or record.get("statistic", STATISTIC) != STATISTIC:
        return "INCOMPATIBLE_STATISTIC", "A closing/average/other fixing cannot settle a New York noon buying-rate target"
    if record.get("productId", PRODUCT) != PRODUCT:
        return "INCOMPATIBLE_PRODUCT", "Source product is not the reviewed FRED DEXINUS daily product"
    if record.get("entity") != "USD/INR" or record.get("geography") != "India / New York reference rate":
        return "INCOMPATIBLE_SCOPE", "Entity or geographic reference-rate scope differs"
    if record.get("recordKind") == "ECONOMIC_OBSERVATION" and record.get("source") != SOURCE:
        return "UNSUPPORTED_SOURCE_SEMANTICS", "No reviewed mapping establishes this observation's source product"
    return None, None


def select_outcome(store, item, now, root=None):
    """Select one first-retained compatible observation without writing a match."""
    as_of = _instant(now)
    target = item.get("target", {})
    target_day = target.get("date")
    result = {"eligible": False, "status": "EXCLUDED", "reason": None, "targetDate": target_day,
              "targetKey": None, "matchPolicy": SELECTION_POLICY, "selectionPolicy": SELECTION_POLICY,
              "evidence": None, "candidates": [], "exclusions": [], "revisionState": "NO_OUTCOME",
              "expectedRelease": None, "quoteDate": None, "quoteAgeDays": None}
    def exclude(code, reason, evidence_id=None):
        result["exclusions"].append({"code": code, "reason": reason, **({"evidenceId": evidence_id} if evidence_id else {})})
        return code, reason
    try:
        target_date = _date(target_day)
        origin = _instant(item["originAt"])
        first_available = _instant(item["firstAvailableAt"])
        result["targetKey"] = _id([SERIES, target_day, UNIT, STATISTIC, PRODUCT])
        result["expectedRelease"] = expected_release(target_day)
    except (ValueError, KeyError, TypeError):
        result["reason"] = "Missing or malformed forecast target/aware origin"
        exclude("INVALID_TARGET_OR_TIME", result["reason"])
        return result
    semantic_error = _semantics(item)
    if semantic_error[0]:
        exclude(*semantic_error)
    if item.get("kind") != "FORECAST" or not _finite(item.get("value")):
        exclude("NOT_NUMERICAL_FORECAST", "An observation or nonfinite value is not a prospective numerical forecast")
    if item.get("source") != "PortWatch persistence baseline" or item.get("sourceVersion") != "persistence-v1":
        exclude("UNSUPPORTED_FORECAST_POLICY", "Only the frozen persistence-v1 baseline is qualified by this economic evaluation")
    if origin > as_of or first_available > as_of:
        exclude("FORECAST_NOT_AVAILABLE_AS_OF", "Forecast was unavailable at the selected as-of time")
    if first_available > origin or origin.date() >= target_date:
        exclude("NON_PROSPECTIVE_ISSUE", "Issue and first availability must precede the target observation date; intraday date-only outcomes cannot establish a future cutoff")
    inputs = item.get("inputs", [])
    quote = inputs[0] if len(inputs) == 1 and isinstance(inputs[0], dict) else None
    if not quote:
        exclude("INPUT_QUOTE_MISSING", "One frozen original input quote is required")
    else:
        try:
            if quote.get("recordKind") != "ECONOMIC_OBSERVATION":
                exclude("INPUT_QUOTE_NOT_OBSERVATION", "An operator assumption or forecast cannot replace the retained input observation")
            quote_day = observation_date(quote)
            result["quoteDate"] = quote_day
            result["quoteAgeDays"] = (origin.date()-_date(quote_day)).days
            if _instant(quote["firstAvailableAt"]) > origin or _date(quote_day) > origin.date():
                exclude("INPUT_UNAVAILABLE_AT_ISSUE", "Consumed quote was unavailable or from a later observation date")
            error = _semantics(quote)
            if error[0]:
                exclude(*error)
            raw_error = _raw_status(store, quote, root)
            if raw_error[0]:
                exclude(*raw_error)
            if item.get("sourceVersion") in ("persistence-v1", "persistence-v2") and item.get("value") != quote.get("value"):
                exclude("PERSISTENCE_INPUT_MISMATCH", "Frozen persistence prediction differs from its retained input quote")
        except (ValueError, TypeError, KeyError, OSError):
            exclude("INPUT_QUOTE_INVALID", "Frozen quote date, availability or original is invalid")
    if result["exclusions"]:
        result["reason"] = result["exclusions"][0]["reason"]
        return result
    candidates = []
    for record in store.feedback("evidence"):
        if record.get("recordKind") != "ECONOMIC_OBSERVATION":
            continue
        try:
            related = record.get("eventKey") == item.get("eventKey") or observation_date(record) == target_day
            if not related:
                continue
            record_time = _instant(record["firstAvailableAt"])
            if record_time > as_of:
                continue  # As-of views do not disclose future evidence.
            error = _semantics(record)
            if error[0]:
                exclude(*error, evidence_id=record.get("id")); continue
            if observation_date(record) != target_day or record.get("target", {}).get("date") != target_day:
                exclude("INCOMPATIBLE_OBSERVATION_DATE", "Outcome addresses a different observation date", record.get("id")); continue
            if record.get("source") != SOURCE:
                exclude("UNSUPPORTED_SOURCE_SEMANTICS", "No reviewed mapping establishes this outcome's source product", record.get("id")); continue
            if record_time <= origin or record_time.date() < target_date:
                exclude("INVALID_OUTCOME_AVAILABILITY", "Outcome receipt must follow issue and cannot precede its observation date", record.get("id")); continue
            error = _raw_status(store, record, root)
            if error[0]:
                exclude(*error, evidence_id=record.get("id")); continue
            candidates.append(record)
        except (ValueError, KeyError, TypeError, OSError):
            exclude("MALFORMED_OUTCOME", "Outcome date, value, availability or original is malformed", record.get("id"))
    candidates.sort(key=lambda row: (_instant(row["firstAvailableAt"]), row["id"]))
    result["candidates"] = candidates
    if candidates:
        first_time = candidates[0]["firstAvailableAt"]
        first = [row for row in candidates if _instant(row["firstAvailableAt"]) == _instant(first_time)]
        if len({row["value"] for row in first}) > 1:
            result.update(status="CONFLICTING_OUTCOMES", reason="Conflicting values at the first retained availability; no scoring vintage can be selected", revisionState="CONFLICTED")
            exclude("CONFLICTING_VALUES", result["reason"])
            return result
        revised = len({row["value"] for row in candidates}) > 1
        result.update(eligible=True, status="MATCHABLE", reason="Compatible prospective target matched to its first retained original observation",
                      evidence=candidates[0], revisionState="REVISED_EXCLUDED_FROM_RELIABILITY" if revised else "FIRST_RETAINED_UNREVISED")
        return result
    missing = [row for row in store.feedback("missing-date") + store.feedback("economic-missing-observation")
               if row.get("date") == target_day and row.get("firstAvailableAt") and _instant(row["firstAvailableAt"]) <= as_of]
    checks = [row for row in store.feedback("economic-source-check") if row.get("checkedAt") and _instant(row["checkedAt"]) <= as_of]
    latest_check = max(checks, key=lambda row: (_instant(row["checkedAt"]), row["id"])) if checks else None
    if result["exclusions"]:
        result.update(status="EXCLUDED", reason=result["exclusions"][0]["reason"])
    elif missing or target_date.weekday() >= 5:
        result.update(status="MISSING_OBSERVATION", reason="Publisher reports no value for this observation date, or the target is a non-business day. A missing row is not zero and does not prove provider failure.")
    elif as_of.date() <= target_date or (result["expectedRelease"].get("expectedAt") and as_of < _instant(result["expectedRelease"]["expectedAt"])):
        result.update(status="UNRELEASED_TARGET", reason="Target is not yet in its expected weekly H.10 release window; actual provider availability remains unknown")
    elif latest_check and latest_check.get("status") in ("PROVIDER_UNAVAILABLE", "MALFORMED_RESPONSE"):
        result.update(status=latest_check["status"], reason=latest_check.get("reason") or "Latest source check failed; no outcome is synthesized")
    else:
        result.update(status="DELAYED_OR_MISSING_RELEASE", reason="Expected release window has passed but a matching retained value is absent; delayed release and missing observation cannot yet be distinguished")
    return result


def inspect_economics(store, now, root=None):
    """Complete, explicitly declared dataset. No visible-page cap enters counts."""
    as_of = _instant(now)
    claims = [item for item in store.feedback("claim") if item.get("kind") == "FORECAST"
              and item.get("target", {}).get("series") == SERIES and _instant(item["firstAvailableAt"]) <= as_of]
    targets = []
    for item in sorted(claims, key=lambda row: (_instant(row["originAt"]), row["id"])):
        selection = select_outcome(store, item, now, root)
        evidence = selection["evidence"]
        record = store.get_prediction(item["id"])
        matches = store.feedback("match", item["id"])
        match = matches[0] if matches else None
        qualifications = [row for row in store.feedback("economic-qualification")
                          if row.get("claimId") == item["id"] and row.get("selectionPolicy") == SELECTION_POLICY
                          and row.get("assessedAt") and _instant(row["assessedAt"]) <= as_of
                          and evidence and row.get("evidenceId") == evidence["id"]]
        qualification = min(qualifications, key=lambda row: (_instant(row["assessedAt"]), row["id"])) if qualifications else None
        assessed_at = qualification.get("assessedAt") if qualification else match.get("assessedAt") if match else None
        visible_score = bool(selection["eligible"] and record and record.status == "resolved" and evidence and match
                             and assessed_at and _instant(assessed_at) <= as_of
                             and match.get("evidenceId") == evidence["id"]
                             and record.observed_value == evidence["value"])
        error = evidence["value"]-item["value"] if visible_score else None
        quote = item.get("inputs", [{}])[0] if item.get("inputs") else {}
        targets.append({"claimId": item["id"], "targetKey": selection["targetKey"], "status": "MATCHED" if visible_score else selection["status"],
                        "reason": selection["reason"], "predicted": item.get("value"), "unit": UNIT,
                        "inputQuote": {"value": quote.get("value"), "observationDate": selection["quoteDate"],
                            "ageDays": selection["quoteAgeDays"], "firstAvailableAt": quote.get("firstAvailableAt"), "responseSha256": quote.get("responseSha256")},
                        "targetDate": selection["targetDate"], "issuedAt": item.get("originAt"), "firstAvailableAt": item.get("firstAvailableAt"),
                        "matchedObservation": {"value": evidence["value"], "observationDate": observation_date(evidence),
                            "firstAvailableAt": evidence["firstAvailableAt"], "providerPublishedAt": evidence.get("providerPublishedAt"),
                            "evidenceId": evidence["id"], "responseSha256": evidence["responseSha256"]} if evidence else None,
                        "assessmentAvailableAt": assessed_at if visible_score else None, "error": error,
                        "absoluteError": abs(error) if error is not None else None, "errorConvention": "observed minus predicted",
                        "scoringVintage": match.get("scoringVintage") if visible_score else None,
                        "revisionState": selection["revisionState"], "outcomeVintages": [{"evidenceId": row["id"], "value": row["value"],
                            "firstAvailableAt": row["firstAvailableAt"], "responseSha256": row["responseSha256"]} for row in selection["candidates"]],
                        "exclusions": selection["exclusions"], "selectionPolicy": SELECTION_POLICY,
                        "eligibleForReliability": visible_score and selection["revisionState"] == "FIRST_RETAINED_UNREVISED",
                        "expectedRelease": selection["expectedRelease"],
                        "qualification": qualification,
                        "legacyStoredScore": {"status": record.status, "observed": record.observed_value, "error": record.error,
                            "absoluteError": record.absolute_error, "availableAt": record.observed_at,
                            "qualification": "Legacy stored score retained; assessment-time provenance or current original qualification is unavailable"}
                            if record and record.status == "resolved" and record.observed_at and _instant(record.observed_at) <= as_of and not visible_score else None})
    groups = {}
    for row in targets:
        groups.setdefault(row["targetKey"] or row["claimId"], []).append(row)
    independent = []
    for key, rows in sorted(groups.items()):
        pool = [row for row in rows if row["eligibleForReliability"]] or rows
        first_issue = min(_instant(row["issuedAt"]) for row in pool)
        earliest = [row for row in pool if _instant(row["issuedAt"]) == first_issue]
        selected = min(earliest, key=lambda row: row["claimId"])
        if len({row["predicted"] for row in earliest}) != 1:
            selected = {**selected, "eligibleForReliability": False, "status": "CONFLICTING_FORECAST_VINTAGES"}
        independent.append(selected)
    eligible = [row for row in independent if row["eligibleForReliability"]]
    observations = [row for row in store.feedback("evidence") if row.get("recordKind") == "ECONOMIC_OBSERVATION"
                    and row.get("target", {}).get("series") == SERIES and _instant(row["firstAvailableAt"]) <= as_of]
    counts = {"retainedObservations": len(observations), "independentObservationDates": len({observation_date(row) for row in observations}),
              "independentForecastTargets": len(groups), "forecastVintages": len(targets),
              "eligibleMatches": sum(row["status"] == "MATCHED" for row in independent),
              "matchableTargets": sum(row["matchedObservation"] is not None for row in independent),
              "eligibleIndependentTargets": len(eligible), "unresolvedTargets": sum(row["status"] != "MATCHED" for row in independent),
              "excludedTargets": sum(bool(row["exclusions"]) or row["status"].startswith("CONFLICTING")
                                     or row["revisionState"] == "REVISED_EXCLUDED_FROM_RELIABILITY" for row in independent),
              "revisedTargets": sum(row["revisionState"] == "REVISED_EXCLUDED_FROM_RELIABILITY" for row in independent),
              "legacyStoredScores": sum(row["legacyStoredScore"] is not None for row in targets)}
    forecast_dates = {row["targetDate"] for row in targets}
    counts["historyOnlyObservationDates"] = len({observation_date(row) for row in observations}-forecast_dates)
    contexts = {}
    for row in eligible:
        horizon = (_date(row["targetDate"])-_instant(row["issuedAt"]).date()).days
        contexts.setdefault(horizon, []).append(row)
    slices = [{"series": SERIES, "unit": UNIT, "statistic": STATISTIC, "forecastPolicy": "persistence-v1",
               "horizonCalendarDays": horizon, "independentTargets": len(rows),
               "targetDateFrom": min(row["targetDate"] for row in rows), "targetDateThrough": max(row["targetDate"] for row in rows),
               "bias": sum(row["error"] for row in rows)/len(rows), "meanAbsoluteError": sum(row["absoluteError"] for row in rows)/len(rows),
               "status": "COLLECTING", "consumedWeight": 1, "comparison": "Persistence baseline only; no improvement over itself is claimed"}
              for horizon, rows in sorted(contexts.items())]
    checks = [row for row in store.feedback("economic-source-check") if _instant(row["checkedAt"]) <= as_of]
    checks.sort(key=lambda row: (_instant(row["checkedAt"]), row["id"]))
    receipts = [row for row in store.feedback("receipt") if row.get("productId") == PRODUCT or row.get("source", "").startswith("https://fred.stlouisfed.org/graph/fredgraph.csv")]
    receipts = [row for row in receipts if _instant(row.get("firstAvailableAt") or row.get("receivedAt")) <= as_of]
    original_receipts = {}
    for receipt in receipts:
        key = (receipt.get("source"), receipt.get("responseSha256"))
        first = receipt.get("firstAvailableAt") or receipt.get("receivedAt")
        if key not in original_receipts or _instant(first) < _instant(original_receipts[key]):
            original_receipts[key] = first
    successful_checks = [row for row in checks if row.get("status") == "CURRENT"]
    return {"contractVersion": "economic-feedback-inspection-v2", "asOf": now, "series": SERIES, "metadata": METADATA,
            "dataset": {"scope": "ALL_RETAINED_DEXINUS_FORECAST_CLAIMS_AVAILABLE_AS_OF", "claimCount": len(claims),
                        "complete": True, "selectionPolicy": INDEPENDENT_POLICY, "errorConvention": "observed minus predicted",
                        "countDefinitions": {"historyOnlyObservationDates": "Retained observation dates that are not any prospective forecast target date in the selected as-of dataset; these are history/context, not retrospectively created forecasts",
                            "retainedObservations": "All retained economic observation vintages, not an independent sample count",
                            "eligibleMatches": "Independent matched targets with visible evidence-qualified scoring assessment; revised targets remain separately excluded from reliability",
                            "unresolvedTargets": "Independent targets without a visible qualified scoring assessment, including pending and excluded contexts; counts are not disjoint",
                            "excludedTargets": "Targets with unsupported/conflicting/missing evidence or revised outcomes excluded from reliability; an existing score is preserved"}},
            "counts": counts, "targets": targets, "slices": slices,
            "selectedClaimIds": sorted(row["claimId"] for row in eligible),
            "independentSelection": [{"targetKey": row["targetKey"], "selectedClaimId": row["claimId"],
                "eligibleForReliability": row["eligibleForReliability"], "policy": INDEPENDENT_POLICY} for row in independent],
            "collector": {"lastCheck": checks[-1] if checks else None,
                          "lastSuccessfulReceiptAt": max(original_receipts.values(), default=None),
                          "lastSuccessfulFetchAt": successful_checks[-1]["checkedAt"] if successful_checks else None,
                          "latestObservationDate": max((observation_date(row) for row in observations), default=None),
                          "observationAgeCalendarDays": (as_of.date()-_date(max(observation_date(row) for row in observations))).days if observations else None},
            "status": "COLLECTING", "consumedWeight": 1,
            "note": "Source verification, prospective economic forecast error and actual shipping effects are separate. No FX valuation, vessel hold, learned correction or measured saving is inferred."}
