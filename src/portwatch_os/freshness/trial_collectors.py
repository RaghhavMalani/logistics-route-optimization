"""Opt-in, unpublished collectors with bounded requests."""

from datetime import date, datetime, time, timezone
import json
import math
from urllib.parse import urlsplit

import requests

from src.portwatch_os.freshness.source_snapshots import Snapshot
from src.portwatch_os.clock import wall_now

MAX_RESPONSE_BYTES = 1_000_000


def fetch_json(url: str, params: dict) -> object:
    with requests.get(url, params=params, timeout=(5, 15), stream=True, allow_redirects=False,
                      headers={"User-Agent": "PortWatch-Source-Trial/1.0"}) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError("Expected an HTTP 200 provider response")
        body = bytearray()
        for chunk in response.iter_content(8192):
            body.extend(chunk)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError("Provider response exceeds the trial size limit")
    return json.loads(body)


def ecb_rates(url: str) -> Snapshot:
    rates = fetch_json(url, {"base": "EUR", "quotes": "INR,USD"})
    if not isinstance(rates, list) or len(rates) != 2:
        raise ValueError("ECB coverage requires both EUR reference rates")
    checked = {}
    for row in rates:
        quote = row["quote"]
        value = row["rate"]
        if (row["base"] != "EUR" or quote not in {"INR", "USD"} or quote in checked
                or type(value) not in (int, float) or not math.isfinite(value) or value <= 0):
            raise ValueError("Unexpected ECB reference series")
        checked[quote] = date.fromisoformat(row["date"])
    # Use the older leg to avoid making partially current coverage appear fresh.
    # The response supplies reference dates only. Midnight UTC is a date anchor.
    if max(checked.values()) > wall_now().date():  # wall-clock: no future ECB reference dates.
        raise ValueError("Future ECB reference date")
    reference = datetime.combine(min(checked.values()), time.min, timezone.utc)
    return Snapshot({
        "attribution": "Source: ECB statistics via Frankfurter",
        "precision": "DATE_ONLY", "rates": rates,
        "coverage": {f"EUR/{key}": value.isoformat() for key, value in checked.items()},
    }, reference)


def gdelt_discovery() -> Snapshot:
    from src.portwatch_os.intelligence.free_sources import PRODUCTS, _request

    url, params = _request("gdelt")
    response = fetch_json(url, {**params, "timespan": "24h", "maxrecords": 30})
    if not isinstance(response, dict) or not isinstance(response.get("articles"), list):
        raise ValueError("Expected a GDELT article list")
    # wall-clock: an index timestamp cannot lead the actual response receipt.
    now = wall_now()
    documents = {}
    for row in response["articles"][:30]:
        try:
            link = urlsplit(row["url"])
            seen = datetime.strptime(row["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            if link.scheme in ("https", "http") and link.hostname and not link.username and seen <= now:
                documents[link.geturl()] = seen
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    if response["articles"] and not documents:
        raise ValueError("GDELT returned articles without qualifying dates or links")
    return Snapshot({
        "attribution": "GDELT Project, https://www.gdeltproject.org/",
        "precision": "INDEX_SEEN_TIME",
        "scope": PRODUCTS["gdelt"]["geography"],
        "coverage": {url: seen.isoformat() for url, seen in documents.items()},
    }, max(documents.values(), default=None))


def nho_warning_metadata() -> Snapshot:
    from src.portwatch_os.intelligence import indian_notices as nho

    page, _ = nho._fetch(nho.CATALOGUE)
    products = []
    for link in nho.discover_links(page)[:2]:
        raw, final = nho._fetch(link, document=True)
        products.append((nho.parse(raw), final))
    product, link = max(products, key=lambda pair: pair[0]["productAsOfDate"])
    # wall-clock: the trial samples today's authority coverage independently of app replay.
    now = wall_now()
    cancelled = {ref for row in product["notices"] for ref in row["cancellationRefs"]}
    warnings = {}
    for row in product["notices"]:
        issued = row["providerIssueAt"]
        valid = nho.public_notice(row, as_of=now)
        if (issued and nho.aware(issued) <= now and row["status"] == "REVIEW_CONTEXT"
                and valid["sourceStatus"] == "CURRENT_PRODUCT_DATE" and row["noticeId"] not in cancelled):
            warnings[row["noticeRef"]] = issued
    return Snapshot({
        "attribution": nho.SOURCE_USE["attribution"], "source": link,
        "precision": "DATE_ONLY", "coverage": warnings,
    }, nho.aware(product["productAsOfDate"] + "T00:00:00+00:00"))
