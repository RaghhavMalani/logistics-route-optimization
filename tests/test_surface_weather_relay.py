"""Authenticate every response and retain the provider's original bytes."""

import base64
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import Mock

import pytest

from src.portwatch_os.intelligence import current_environment as weather, surface_relay
from src.portwatch_os.intelligence.surface_transport import SurfaceTransportError
from src.utils.port_registry import PORTS

NOW = datetime(2026, 11, 19, 9, tzinfo=timezone.utc)
SECRET = "test" * 16


@pytest.mark.parametrize("fault", [None, "signature", "old", "nonce", "provider"])
def test_pull_response_signature_time_and_request_binding(monkeypatch, fault):
    config = surface_relay.RelaySettings("https://relay.vercel.app/api/weather", SECRET)
    monkeypatch.setattr(surface_relay, "wall_now", lambda: NOW)

    def request(url, **kwargs):
        nonce = kwargs["headers"]["X-Weather-Nonce"]
        stamp = int((NOW - timedelta(minutes=6) if fault == "old" else NOW).timestamp())
        content = json.dumps({"outcome": "ok",
                              "provider": "wrong" if fault == "provider" else weather.URLS["surface"],
                              "original": base64.b64encode(b"[]").decode()}).encode()
        headers = {"X-Weather-Nonce": "0" * 32 if fault == "nonce" else nonce,
                   "X-Weather-Timestamp": str(stamp),
                   "X-Weather-Signature": "0" * 64 if fault == "signature" else
                   surface_relay.signature(SECRET, "response", 0, nonce, stamp, content)}
        response = Mock(headers=headers)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_content.return_value = [content]
        return response

    monkeypatch.setattr(surface_relay.requests, "post", request)
    if fault:
        with pytest.raises(SurfaceTransportError):
            surface_relay.collect(0, {}, config)
    else:
        assert surface_relay.collect(0, {}, config) == (b"[]", int(NOW.timestamp()))


def test_pull_original_uses_existing_validation_and_preserves_provenance(tmp_path, monkeypatch):
    ports = PORTS[::4]
    original = json.dumps([
        {"latitude": port.lat, "longitude": port.lon, "hourly_units": weather.SURFACE_UNITS,
         "hourly": {"time": [NOW.isoformat()], **{name: [3] for name in weather.SURFACE_UNITS}}}
        for port in ports
    ]).encode()
    monkeypatch.setattr(weather, "ROOT", tmp_path)
    monkeypatch.setattr(weather, "world_now", lambda: NOW)
    monkeypatch.setattr(weather, "wall_now", lambda: NOW)
    monkeypatch.setattr(surface_relay, "collect", lambda *args: (original, int(NOW.timestamp())))
    rows = weather.refresh_surface_batch(ports, relay_group=0, relay_config=object())
    for snapshot in rows.values():
        assert snapshot["delivery"] == "via relay"
        assert snapshot["issuedAt"] is None
        assert snapshot["relayFetchedAt"] == snapshot["fetchedAt"] == NOW.isoformat()
        assert (tmp_path / "archive" / (snapshot["responseSha256"] + ".response")).read_bytes() == original
    monkeypatch.setattr(surface_relay, "collect", lambda *args: (b"[]", int(NOW.timestamp())))
    with pytest.raises(ValueError, match="number of locations"):
        weather.refresh_surface_batch(ports, relay_group=0, relay_config=object())
