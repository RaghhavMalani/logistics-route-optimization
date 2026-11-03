"""Reviewed, single-document Paradip pre-entry decision pilot."""

import hashlib
from datetime import timedelta

import requests

from src.portwatch_os.clock import wall_now
from .indian_notices import LOCK, _original
from .timestamps import instant

KIND = "PARADIP_ENTRY_RESTRICTION"
NOTICE = "TD/TM/GEN-244/1803"
SHA = "d38aef79fc102488d5172049ed82a25428d79c972034d8193314a74500d60ce2"
URL = "https://www.paradipport.gov.in/uploads/2026/10/Unseaworthy-Vessels.pdf"
CATALOGUE = "https://paradipport.gov.in/circulars-notices/"
ACTION = "Hold entry request, disclose the defect and seek Marine Department review"
MEANING = "The simulated referral records the accepted plan. Entry, pilotage, clearance, waiting, schedule shift, fuel, cost and actual execution remain unknown."


def _download(url, limit):
    with requests.get(url, timeout=(4, 10), stream=True, allow_redirects=False) as response:
        if response.status_code != 200:
            raise ValueError("Paradip issuer response unavailable")
        raw = bytearray()
        for chunk in response.iter_content(65536):
            raw.extend(chunk)
            if len(raw) > limit:
                raise ValueError("Paradip issuer response exceeds its reviewed bounds")
        return bytes(raw)


def evidence(root):
    try:
        index = _download(CATALOGUE, 4_000_000)
        raw = _download(URL, 1_000_000)
    except requests.RequestException as exc:
        raise ValueError("Could not verify the Paradip notice with the issuer") from exc
    if URL.encode() not in index or hashlib.sha256(raw).hexdigest() != SHA:
        raise ValueError("The reviewed Paradip notice is absent or its original changed; fresh source review is required")
    at = wall_now().isoformat()
    directory = root / "paradip_entry"
    directory.mkdir(parents=True, exist_ok=True)
    with LOCK:
        original = _original(directory, raw, at)
        catalogue = _original(directory, index, at)
    return {"title": "Paradip pre-entry defect declaration", "noticeRef": NOTICE,
            "fact": "Agents must disclose known defects before entering Paradip port limits. The port reserves the right to deny entry or suspend pilotage for undisclosed critical defects.",
            "status": "LISTED_REVIEWED_REVISION", "source": URL, "catalogue": CATALOGUE,
            "publishedDate": "2026-10-13", "documentPages": [1], "availableAt": original[1],
            "checkedAt": at, "responseSha256": SHA, "revisionId": SHA, "catalogueSha256": catalogue[0]}


def require_originals(root, fact, now):
    if fact["revisionId"] != SHA or now - instant(fact["checkedAt"]) > timedelta(hours=1):
        raise ValueError("Paradip review evidence has expired or the reviewed revision changed")
    for digest in (SHA, fact["catalogueSha256"]):
        try:
            valid = hashlib.sha256((root / "paradip_entry" / (digest + ".response")).read_bytes()).hexdigest() == digest
        except OSError:
            valid = False
        if not valid:
            raise ValueError("A frozen Paradip source original is unavailable or corrupt")
