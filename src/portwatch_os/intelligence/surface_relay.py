"""Signed requests for the optional surface collector on a separate network."""

from datetime import timedelta
import hashlib
import hmac
import json
from urllib.parse import urlsplit

import requests

from src.portwatch_os.clock import wall_now
from src.portwatch_os.freshness.job import RetryAfterError
from src.portwatch_os.intelligence.surface_transport import SurfaceTransportError
from src.utils.settings import get_settings


CALLBACK_PATH = "/api/intelligence/internal/surface-relay"
MAX_SKEW_SECONDS = 120


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
    return url, secret


def signature(secret, direction, group, timestamp, body):
    envelope = f"{direction}\n{group}\n{timestamp}\n".encode() + body
    return hmac.new(secret.encode(), envelope, hashlib.sha256).hexdigest()


def collect(group, params, config):
    url, secret = config
    body = json.dumps(params, separators=(",", ":")).encode()
    sent_at = int(wall_now().timestamp())
    try:
        response = requests.post(url, data=body, timeout=(3, 20), allow_redirects=False,
                                 headers={"Content-Type": "application/octet-stream",
                                          "X-Weather-Group": str(group), "X-Weather-Timestamp": str(sent_at),
                                          "X-Weather-Signature": signature(secret, "request", group, sent_at, body)})
        if response.status_code != 200:
            raise SurfaceTransportError("relay_unconfirmed")
        receipt = response.json()
        outcome = receipt["outcome"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        raise SurfaceTransportError("relay_unconfirmed") from error

    if outcome == "ok" and isinstance(receipt.get("snapshots"), dict):
        return receipt["snapshots"]
    if outcome == "HTTP 429":
        wait = receipt.get("retryAfterSeconds")
        retry_at = wall_now() + timedelta(seconds=wait) if type(wait) is int and 0 <= wait <= 86400 else None
        raise RetryAfterError("Open-Meteo surface HTTP 429 via relay", retry_at)
    if outcome not in ("relay_provider_timeout", "relay_provider_http", "relay_invalid_response", "relay_callback_error"):
        outcome = "relay_unconfirmed"
    raise SurfaceTransportError(outcome)
