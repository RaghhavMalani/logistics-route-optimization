"""Signed requests for the optional surface collector on a separate network."""

from datetime import timedelta
from dataclasses import dataclass
import base64
import hashlib
import hmac
import json
import secrets
from urllib.parse import urlsplit

import requests

from src.portwatch_os.clock import wall_now
from src.portwatch_os.freshness.job import RetryAfterError
from src.portwatch_os.intelligence.surface_transport import SurfaceTransportError
from src.utils.settings import get_settings


MAX_SKEW_SECONDS = 300
MAX_ENVELOPE_BYTES = 1500000


@dataclass(frozen=True, repr=False)
class RelaySettings:
    url: str
    secret: str
    bypass: str | None = None


def relay_settings():
    settings = get_settings()
    url, secret = settings.PORTWATCH_WEATHER_RELAY_URL, settings.PORTWATCH_WEATHER_RELAY_SECRET
    if not url or not secret or len(secret) < 32:
        return None
    origin = urlsplit(url)
    if (origin.scheme != "https" or not (origin.hostname or "").endswith(".vercel.app")
            or origin.username or origin.password or origin.port is not None
            or origin.path != "/api/weather" or origin.query or origin.fragment):
        return None
    return RelaySettings(url, secret, settings.PORTWATCH_WEATHER_RELAY_BYPASS)


def signature(secret, direction, group, nonce, timestamp, body):
    envelope = f"{direction}\n{group}\n{nonce}\n{timestamp}\n".encode() + body
    return hmac.new(secret.encode(), envelope, hashlib.sha256).hexdigest()


def collect(group, params, config):
    body = json.dumps(params, separators=(",", ":")).encode()
    sent_at = int(wall_now().timestamp())
    nonce = secrets.token_hex(16)
    headers = {"Content-Type": "application/octet-stream",
               "X-Weather-Group": str(group), "X-Weather-Timestamp": str(sent_at),
               "X-Weather-Nonce": nonce,
               "X-Weather-Signature": signature(config.secret, "request", group, nonce, sent_at, body)}
    if config.bypass:
        headers["x-vercel-protection-bypass"] = config.bypass
    try:
        with requests.post(config.url, data=body, timeout=(3, 12), allow_redirects=False,
                           headers=headers, stream=True) as response:
            original = bytearray()
            for chunk in response.iter_content(65536):
                if len(original) + len(chunk) > MAX_ENVELOPE_BYTES:
                    raise SurfaceTransportError("relay_invalid_response")
                original.extend(chunk)
            original = bytes(original)
            timestamp = response.headers.get("X-Weather-Timestamp", "")
            received_nonce = response.headers.get("X-Weather-Nonce")
            provided = response.headers.get("X-Weather-Signature", "")
            now = wall_now()
            if (not timestamp.isascii() or not timestamp.isdecimal() or len(timestamp) != 10
                    or received_nonce != nonce or len(provided) != 64 or not provided.isascii()):
                raise SurfaceTransportError("relay_signature")
            if not -30 <= now.timestamp() - int(timestamp) <= MAX_SKEW_SECONDS:
                raise SurfaceTransportError("relay_replay")
            expected = signature(config.secret, "response", group, nonce, timestamp, original)
            if not hmac.compare_digest(provided, expected):
                raise SurfaceTransportError("relay_signature")
        receipt = json.loads(original)
        outcome = receipt["outcome"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        raise SurfaceTransportError("relay_unconfirmed") from error

    if outcome == "ok" and receipt.get("provider") == "https://api.open-meteo.com/v1/forecast":
        try:
            payload = base64.b64decode(receipt["original"], validate=True)
        except (ValueError, TypeError, KeyError) as error:
            raise SurfaceTransportError("relay_invalid_response") from error
        return payload, int(timestamp)
    if outcome == "HTTP 429":
        wait = receipt.get("retryAfterSeconds")
        retry_at = wall_now() + timedelta(seconds=wait) if type(wait) is int and 0 <= wait <= 86400 else None
        raise RetryAfterError("Open-Meteo surface HTTP 429 via relay", retry_at)
    if outcome not in ("relay_provider_timeout", "relay_provider_http", "relay_invalid_response", "HTTP 429"):
        outcome = "relay_unconfirmed"
    raise SurfaceTransportError(outcome)
