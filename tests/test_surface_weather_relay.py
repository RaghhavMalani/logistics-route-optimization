"""The machine callback shares the direct collector's validation and receipt clocks."""

from datetime import datetime, timedelta, timezone
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.domains.intelligence import weather_relay
from src.portwatch_os.intelligence import current_environment as weather, surface_relay
from src.utils.port_registry import PORTS


def test_relay_authentication_provenance_and_idempotence(tmp_path, monkeypatch):
    now = datetime(2026, 11, 18, 10, 12, tzinfo=timezone.utc)
    key = "test" * 16
    group = 0
    expected_ports = PORTS[group::weather.SURFACE_GROUPS]
    current_hour = now.replace(minute=0).isoformat()
    original = json.dumps([
        {"latitude": port.lat, "longitude": port.lon, "hourly_units": weather.SURFACE_UNITS,
         "hourly": {"time": [current_hour], **{name: [3] for name in weather.SURFACE_UNITS}}}
        for port in expected_ports
    ]).encode()
    monkeypatch.setattr(weather, "ROOT", tmp_path)
    monkeypatch.setattr(weather, "world_now", lambda: now)
    monkeypatch.setattr(weather_relay, "wall_now", lambda: now)
    monkeypatch.setattr(weather_relay, "current_weather_eligibility", lambda: None)
    monkeypatch.setattr(surface_relay, "relay_settings", lambda: ("https://relay.vercel.app/api/weather", key))
    app = FastAPI()
    app.include_router(weather_relay.router, prefix="/api")
    client = TestClient(app)

    def post(body, *, signed_body=None, signed_at=now, direction="receipt"):
        stamp = int(signed_at.timestamp())
        return client.post(surface_relay.CALLBACK_PATH, content=body, headers={
            "X-Weather-Group": str(group), "X-Weather-Timestamp": str(stamp),
            "X-Weather-Signature": surface_relay.signature(key, direction, group, stamp,
                                                           signed_body if signed_body is not None else body),
        })

    assert post(original, signed_body=b"tampered").status_code == 401
    assert post(original, direction="request").status_code == 401
    assert post(original, signed_at=now - timedelta(minutes=5)).status_code == 401
    assert post(original, signed_at=now + timedelta(minutes=5)).status_code == 401
    assert post(b"[]").status_code == 422
    assert post(b"x" * (weather_relay.MAX_RESPONSE_BYTES + 1)).status_code == 413
    assert not list(tmp_path.iterdir())

    result = post(original)
    assert result.status_code == 200
    assert post(original).json() == result.json()
    assert post(original, signed_at=now - timedelta(seconds=1)).status_code == 409
    snapshots = result.json()["snapshots"]
    assert set(snapshots) == {port.locode for port in expected_ports}
    assert len(list((tmp_path / "archive").glob("*.json"))) == len(expected_ports)
    for port in expected_ports:
        snapshot = weather.read("surface", port, at=now)
        assert snapshot["snapshotId"] == snapshots[port.locode]
        assert snapshot["delivery"] == "via relay"
        assert snapshot["relayFetchedAt"] == snapshot["fetchedAt"] == now.isoformat()
        assert snapshot["issuedAt"] is None
        assert (tmp_path / "archive" / (snapshot["responseSha256"] + ".response")).read_bytes() == original
