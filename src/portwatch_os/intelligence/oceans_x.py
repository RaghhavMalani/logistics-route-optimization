"""Document-qualified OCEANS-X boundary; no active collector or outcome resolver.

The public OpenAPI describes request syntax and fields, but an authenticated
receipt, event definition, time zone and dataset entitlement remain unverified.
Validation preserves naive provider clocks and never promotes these candidates
to actual arrivals, all-fast, restrictions or numerically usable evidence.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
import re
from urllib.request import Request
from src.portwatch_os.clock import wall_now


VERSION = "oceans-x-document-qualified-v1"
TERMS_URL = "https://oceans-x.mpa.gov.sg/api-terms-of-service"
FAQ_URL = "https://oceans-x.mpa.gov.sg/faq"
MAX_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 2000
_SGT = timezone(timedelta(hours=8))
_PRODUCTS = {
    "arrivals": {
        "id": "MPA_OCEANS_X_ARRIVALS_CANDIDATE",
        "catalogueId": "48bf4958-5970-4d53-932d-10f552bda64e",
        "consoleId": "5c869260-a46c-4a39-accc-254e84077aad",
        "name": "Vessel Arrivals by Date",
        "gateway": "https://oceans-x.mpa.gov.sg/api/v1/vessel/arrivals/1.0.0",
        "rawClockField": "arrivedTime",
        "targetMeaning": "Provider-reported vessel arrival; exact operational boundary unverified",
    },
    "due": {
        "id": "MPA_OCEANS_X_DUE_CANDIDATE",
        "catalogueId": "2228f8a0-6184-4d2d-a293-01ec2941752e",
        "consoleId": "9abacbec-f8f8-48b6-bb11-3a0e9cd2e16a",
        "name": "Vessels Due to Arrive by Date",
        "gateway": "https://oceans-x.mpa.gov.sg/api/v1/vessel/duetoarrive/1.0.0",
        "rawClockField": "duetoArriveTime",
        "targetMeaning": "Provider-reported due-to-arrive time; origin, revisions and event boundary unverified",
    },
}


def _product(slug):
    if not isinstance(slug, str) or slug not in _PRODUCTS:
        raise ValueError("Unsupported OCEANS-X product")
    return _PRODUCTS[slug]


def qualification_status():
    """Safe public DTO. Never consult or disclose server credential configuration."""
    products = []
    for slug, item in _PRODUCTS.items():
        products.append({
            **deepcopy(item), "slug": slug,
            "catalogue": f"https://oceans-x.mpa.gov.sg/marketplace/apis/{item['catalogueId']}/overview",
            "documentation": f"https://oceans-x.mpa.gov.sg/marketplace/apis/{item['consoleId']}/api-console?sourceApiId={item['catalogueId']}",
            "operation": "GET /date/{date}", "version": "1.0.0",
            "updateCadence": "Hourly, advertised; successful authenticated collection unverified",
            "clockLimits": {"queryDateFormat": "yyyy-MM-dd", "queryDateTimezone": "SGT (UTC+08:00)",
                "queryDateWindowDays": [-3, 3], "responseClockFormat": "YYYY-MM-DD HH:mm:ss",
                "responseClockTimezone": None, "publicationAt": None, "providerFirstAvailabilityAt": None},
        })
    return {
        "schemaVersion": VERSION, "source": "MPA OCEANS-X", "enabled": False,
        "status": "DOCS_REVIEWED_AUTHENTICATED_RESPONSE_UNVERIFIED",
        "reviewedOn": "2026-10-16", "geographicScope": "Singapore arrival products; India voyage association requires verified vessel identity and explicit confirmation",
        "products": products,
        "access": {"status": "REGISTRATION_AND_PRODUCT_SUBSCRIPTION_REQUIRED", "scheme": "API key",
            "header": "apikey", "authenticatedResponseVerified": False,
            "requiredAction": "Account owner registers, reviews applicable terms, subscribes an application to the selected product, then configures its issued API key privately on the backend"},
        "terms": {"url": TERMS_URL, "faq": FAQ_URL,
            "datasetUse": "Use, adaptation and distribution permitted subject to API terms, applicable credentials and any additional product conditions",
            "attributionRequired": True, "publicFieldsApproved": False,
            "scope": "API datasets only; does not license unrelated MPA articles, notices or third-party material"},
        "unverified": ["Authenticated payload and account entitlement", "Response clock timezone",
            "Arrival event boundary and comparable due/actual target", "Stable port-call/event identifier",
            "Publication and revision clocks", "Quota and additional product conditions", "Permitted public fields"],
        "calculationSupported": False, "outcomeReconciliationEnabled": False,
        "restrictionFeed": False, "allFastEvidence": False,
    }


def backend_configuration():
    """Backend-only diagnostic, not part of the public qualification DTO.

    Presence is not proof of entitlement, acceptance or successful access. No key
    value, length, fingerprint, environment dump or provider error is returned.
    """
    return {"credentialConfigured": bool((os.getenv("OCEANS_X_API_KEY") or "").strip()),
        "enabled": False, "reason": "Authenticated response and semantic qualification required before collector activation"}


def build_request(product, requested_date, *, at=None):
    """Construct the documented HTTPS request with a server-only key header.

    This deliberately does not send it. No current runtime collector calls this
    boundary until account, payload, semantics and public-field review complete.
    """
    item = _product(product)
    if not isinstance(requested_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", requested_date):
        raise ValueError("OCEANS-X request requires an ISO calendar date")
    try:
        selected = date.fromisoformat(requested_date)
    except ValueError:
        raise ValueError("OCEANS-X request requires a valid calendar date") from None
    # wall-clock: the provider's live query-date entitlement follows real SGT,
    # independent of a visitor's paused/replayed scenario clock.
    now = at if at is not None else wall_now()
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("OCEANS-X request clock must be timezone-aware")
    if abs((selected - now.astimezone(_SGT).date()).days) > 3:
        raise ValueError("OCEANS-X query date must be within three days of current SGT date")
    key = (os.getenv("OCEANS_X_API_KEY") or "").strip()
    if not key:
        raise ValueError("OCEANS-X requires an issued backend API key and product subscription")
    if len(key) > 8192 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ValueError("OCEANS-X backend credential has an invalid header format")
    return Request(item["gateway"] + "/date/" + requested_date,
        headers={"apikey": key, "Accept": "application/json", "User-Agent": "PortWatch-research-qualification/1"},
        method="GET")


def _text(value):
    return isinstance(value, str) and 0 < len(value) <= 256 and not any(ord(c) < 32 for c in value)


def validate_documented_payload(payload, product):
    """Validate a bounded documented layout without assigning real-outcome meaning.

    Unexpected fields/layout/clock formats require review. This returns only the
    documented fields, plus explicit unknowns. It is not an ingestion endpoint.
    Public documentation examples and synthetic test inputs remain examples.
    """
    item = _product(product)
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_BYTES:
        raise ValueError("OCEANS-X response must be bounded nonempty bytes")
    try:
        rows = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError("OCEANS-X response is not UTF-8 JSON") from None
    if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
        raise ValueError("OCEANS-X response must be a bounded vessel array")
    records = []
    raw_clock_field = item["rawClockField"]
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"vesselParticulars", raw_clock_field, "locationFrom", "locationTo"}:
            raise ValueError("OCEANS-X documented response layout changed")
        vessel = row["vesselParticulars"]
        if not isinstance(vessel, dict) or set(vessel) != {"vesselName", "callSign", "imoNumber", "flag"}:
            raise ValueError("OCEANS-X documented vessel layout changed")
        if not all(_text(v) for v in vessel.values()) or not all(_text(row[k]) for k in (raw_clock_field, "locationFrom", "locationTo")):
            raise ValueError("OCEANS-X response contains invalid documented text fields")
        raw_clock = row[raw_clock_field]
        try:
            parsed = datetime.strptime(raw_clock, "%Y-%m-%d %H:%M:%S")
            if parsed.strftime("%Y-%m-%d %H:%M:%S") != raw_clock:
                raise ValueError
        except ValueError:
            raise ValueError("OCEANS-X response clock differs from reviewed naive format") from None
        flags = ["RESPONSE_TIMEZONE_UNVERIFIED", "ARRIVAL_EVENT_BOUNDARY_UNVERIFIED", "NO_PORT_CALL_ID",
            "AUTHENTICATED_PAYLOAD_AND_PUBLIC_FIELD_REVIEW_REQUIRED"]
        imo = vessel["imoNumber"]
        verified_format = bool(re.fullmatch(r"[0-9]{7}", imo))
        if not verified_format or sum(int(imo[i]) * (7-i) for i in range(6)) % 10 != int(imo[-1]):
            flags.append("IMO_CHECK_DIGIT_UNVERIFIED_OR_INVALID")
        records.append({"documentedFields": deepcopy(row), "rawEventTime": raw_clock,
            "rawEventTimeField": raw_clock_field, "eventAt": None, "timezone": None,
            "portCallId": None, "allFastAt": None, "sourcePublicationAt": None,
            "kind": "DOCUMENTED_SCHEMA_CANDIDATE", "eligibleForRealOutcome": False,
            "calculationSupported": False, "flags": flags})
    return {"schemaVersion": VERSION, "product": product, "sha256": hashlib.sha256(payload).hexdigest(),
        "status": "LAYOUT_VALIDATED_SEMANTICS_UNVERIFIED", "records": records,
        "calculationSupported": False, "outcomeReconciliationEnabled": False}
