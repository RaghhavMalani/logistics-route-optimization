"""Retain public connector originals beside the existing weather archive.

This is a receipt sidecar, not a catalogue or a new ledger. Only bytes from a
genuine HTTP response establish an original. A parsed legacy cache can never
manufacture one. Readers do not write, fetch, or infer clocks from file mtime.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time

from src.utils.config import DATA_DIR

VERSION = "public-source-receipt-v1"
_LOCK = threading.RLock()
_SAFE_PARAMS = {"latitude", "longitude", "daily", "hourly", "start_date", "end_date",
                "models", "wind_speed_unit", "precipitation_unit", "timezone", "past_days", "forecast_days"}
PRODUCTS = {
    "https://archive-api.open-meteo.com/v1/archive": ("open-meteo:era5:daily-history-v1", "daily_reanalysis"),
    "https://api.open-meteo.com/v1/forecast": ("open-meteo:surface:daily-v1", "daily_surface"),
    "https://marine-api.open-meteo.com/v1/marine": ("open-meteo:marine:daily-v1", "daily_marine"),
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def archive_root():
    return Path(os.getenv("PORTWATCH_CURRENT_ENVIRONMENT_DIR") or DATA_DIR / "cache/current_environment")


def sidecar_path(cache):
    return Path(cache).with_suffix(".source-receipt.json")


def read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def atomic_json(path, body):
    """One replace avoids exposing a partially written JSON cache/sidecar."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(body, stream)
            stream.flush()
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


@contextmanager
def cache_lock(cache):
    """Serialize writers across threads and connector processes.

    A bounded OS byte-range lock is released by the OS if a writer exits. No
    stale lock-file deletion or filesystem clock is used as source evidence.
    """
    lock_path = Path(cache).with_suffix(".source-lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, open(lock_path, "a+b") as stream:
        stream.seek(0)
        if not stream.read(1):
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + 60
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Public source cache is busy")
                    time.sleep(.025)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _immutable(path, raw):
    """Never overwrite already retained bytes, even on a hash/name collision."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "xb") as stream:
            stream.write(raw)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError("Retained source evidence differs from its identity")


def checked(cache, signature, at=None):
    """A cache access records a check only; its receipt clocks stay frozen."""
    path = sidecar_path(cache)
    previous = read_json(path)
    at = at or now_iso()
    if previous and previous.get("requestSignature") == signature:
        atomic_json(path, {**previous, "lastCheckedAt": at})
    else:
        atomic_json(path, {"schemaVersion": 1, "version": VERSION,
            "requestSignature": signature, "lastCheckedAt": at,
            "lastFetchedAt": None, "sourceReceiptId": None,
            "unknownReason": "Legacy parsed cache has no retained original or application receipt."})


def atomic_text(path, value):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(value)
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def retain(cache, url, params, signature, response, at=None):
    """Called only after a successful network response, inside cache_lock."""
    at = at or now_iso()
    previous = read_json(sidecar_path(cache)) or {}
    base = {"schemaVersion": 1, "version": VERSION, "requestSignature": signature,
            "lastCheckedAt": at, "lastFetchedAt": at, "sourceReceiptId": None}
    raw = getattr(response, "content", None)
    if url not in PRODUCTS or not isinstance(raw, bytes):
        atomic_json(sidecar_path(cache), {**base, "unknownReason":
            "Exact HTTP response bytes were not retained; parsed cache is not an original."})
        return
    product, kind = PRODUCTS[url]
    digest = hashlib.sha256(raw).hexdigest()
    receipt_id = "source-receipt-" + hashlib.sha256((product + ":" + signature + ":" + digest).encode()).hexdigest()
    folder = archive_root() / "archive"
    receipt_file = folder / (receipt_id + ".json")
    existing = read_json(receipt_file)
    receipt = existing or {"schemaVersion": 1, "version": VERSION, "kind": kind,
        "sourceProductId": product, "sourceReceiptId": receipt_id, "provider": "Open-Meteo",
        "source": url, "request": {k: v for k, v in params.items() if k in _SAFE_PARAMS},
        "requestSignature": signature, "responseSha256": digest, "originalRef": "sha256:" + digest,
        "firstAvailableAt": at, "fetchedAt": at, "providerPublishedAt": None,
        "providerIssueAt": None, "clockBasis": "First application receipt of exact response bytes; not provider publication or issue time.",
        "previousReceiptId": previous.get("sourceReceiptId"),
        "lineageRelation": ("RESPONSE_REVISION" if previous.get("requestSignature") == signature else "REQUEST_VARIANT")
            if previous.get("sourceReceiptId") and previous.get("sourceReceiptId") != receipt_id else None}
    if not existing:
        receipt["metadataSha256"] = hashlib.sha256(json.dumps(receipt, sort_keys=True, allow_nan=False).encode()).hexdigest()
    _immutable(folder / (digest + ".response"), raw)
    if not existing:
        _immutable(receipt_file, json.dumps(receipt, sort_keys=True, allow_nan=False).encode())
    atomic_json(sidecar_path(cache), {**base, "sourceReceiptId": receipt_id})


def retained(cache):
    """Return validated receipt + check metadata, or an explicit unknown reason."""
    sidecar = read_json(sidecar_path(cache)) or {}
    receipt_id = sidecar.get("sourceReceiptId")
    unknown = "Legacy parsed cache has no retained original or application receipt."
    if not isinstance(receipt_id, str) or not re.fullmatch(r"source-receipt-[a-f0-9]{64}", receipt_id):
        return None, sidecar, sidecar.get("unknownReason") or unknown
    receipt = read_json(archive_root() / "archive" / (receipt_id + ".json"))
    if not receipt or receipt.get("sourceReceiptId") != receipt_id or receipt.get("requestSignature") != sidecar.get("requestSignature"):
        return None, sidecar, "Retained receipt metadata is missing or inconsistent."
    metadata = {key: value for key, value in receipt.items() if key != "metadataSha256"}
    if receipt.get("metadataSha256") != hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest():
        return None, sidecar, "Retained receipt metadata fails its integrity check."
    digest = receipt.get("responseSha256")
    if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest):
        return None, sidecar, "Retained original hash is missing or malformed."
    try:
        raw = (archive_root() / "archive" / (digest + ".response")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            return None, sidecar, "Retained original bytes fail their SHA-256 integrity check."
        expected_id = "source-receipt-" + hashlib.sha256((receipt["sourceProductId"] + ":" + receipt["requestSignature"] + ":" + digest).encode()).hexdigest()
        if expected_id != receipt_id:
            raise ValueError("Receipt identity mismatch")
        if PRODUCTS.get(receipt.get("source")) != (receipt.get("sourceProductId"), receipt.get("kind")):
            raise ValueError("Product identity mismatch")
        signature = hashlib.sha256(json.dumps({"url": receipt["source"], "params": receipt["request"]}, sort_keys=True).encode()).hexdigest()
        if signature != receipt["requestSignature"]:
            raise ValueError("Request identity mismatch")
        first = datetime.fromisoformat(receipt["firstAvailableAt"])
        fetched = datetime.fromisoformat(receipt["fetchedAt"])
        now = datetime.now(timezone.utc)
        if first.tzinfo is None or fetched.tzinfo is None or first > fetched or first > now or fetched > now:
            raise ValueError("Invalid receipt clocks")
        for key in ("lastFetchedAt", "lastCheckedAt"):
            if sidecar.get(key) is not None:
                clock = datetime.fromisoformat(sidecar[key])
                if clock.tzinfo is None or clock > now or clock < first:
                    raise ValueError("Invalid check/fetch clocks")
        original_payload = json.loads(raw)
        original_payload = original_payload if isinstance(original_payload, list) else [original_payload]
        cached_payload = json.loads(Path(cache).read_text(encoding="utf-8"))
        if cached_payload != original_payload:
            return None, sidecar, "Parsed cache differs from the retained original; original linkage is unverified."
    except (OSError, ValueError, TypeError, KeyError):
        return None, sidecar, "Retained original or receipt clocks are missing, malformed or inconsistent."
    return receipt, sidecar, None
