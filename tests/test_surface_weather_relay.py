"""Authenticate every response and retain the provider's original bytes."""

import base64
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import Mock

import pytest

from src.portwatch_os.intelligence import current_environment as weather, surface_relay
from src.portwatch_os.intelligence.surface_transport import SurfaceTransportError
from src.utils.port_registry import PORTS
from src.utils.settings import Settings

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


@pytest.mark.parametrize("recovered", [True, False])
def test_one_direct_fallback_per_failed_relay_cycle(monkeypatch, recovered):
    calls = []
    def fetch(ports, **kwargs):
        calls.append((len(ports), bool(kwargs.get("relay_config"))))
        if kwargs or not recovered:
            raise SurfaceTransportError("relay_provider_timeout")
        return {port.locode: {} for port in ports}
    monkeypatch.setattr(weather, "refresh_surface_batch", fetch)
    rows, failures, counts = weather.collect_surface_groups(PORTS, NOW, force=True, relay_config=object())
    assert calls == [(4, True), (3, True), (3, True), (3, True), (13, False)]
    assert bool(failures) != recovered
    assert set(rows) == ({port.locode for port in PORTS} if recovered else set())
    assert counts["relay_provider_timeout"] == 4
    assert counts.get("direct_fallback_failed", 0) == (0 if recovered else 1)


def test_flag_off_restores_direct_collection_and_on_requires_credentials(monkeypatch):
    monkeypatch.setattr(surface_relay, "get_settings", lambda: Settings(_env_file=None))
    assert surface_relay.relay_settings() is None
    monkeypatch.setattr(surface_relay, "get_settings",
                        lambda: Settings(_env_file=None, PORTWATCH_WEATHER_RELAY_ENABLED="1"))
    with pytest.raises(SurfaceTransportError, match="relay_configuration"):
        surface_relay.relay_settings()
