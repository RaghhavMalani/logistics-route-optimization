from datetime import datetime, timezone

import pytest

from src.portwatch_os.clock import get_clock, set_clock
from src.portwatch_os.panel_runtime import restrict_network
from tests.test_demo_terminal import resources, setup


def test_panel_replay_keeps_clock_and_world_pinned(tmp_path, monkeypatch):
    anchor = datetime(2026, 10, 23, tzinfo=timezone.utc)
    monkeypatch.setenv("PORTWATCH_PANEL_SNAPSHOT_AT", anchor.isoformat())
    set_clock(None)
    store, client = setup(tmp_path, monkeypatch)
    try:
        assert get_clock().describe()["mode"] == "REPLAY"
        assert get_clock().now() == anchor
        token = store.create("NATIONAL_ADMIN")["accessToken"]
        headers = {"Authorization": "Bearer " + token}
        initial = store.read(token)
        clock = "/api/demo/terminal/world/clock"
        assert client.get(clock, headers=headers).json()["mode"] == "REPLAY"
        assert client.post(clock, headers=headers, json={"mode": "LIVE"}).status_code == 409
        assert client.post(clock, headers=headers, json={"mode": "REPLAY", "at": anchor.isoformat()}).status_code == 200
        assert client.post("/api/demo/reset", headers=headers).status_code == 200
        restored = store.read(token)
        assert initial["epoch"] == restored["epoch"] == anchor.isoformat()
        assert initial["generation"] != restored["generation"]
        resources.cache_clear()
        assert client.get(clock, headers=headers).json()["mode"] == "REPLAY"
    finally:
        client.close()
        set_clock(None)


def test_only_the_server_selected_s10_fixture_can_use_panel_replay(tmp_path, monkeypatch):
    anchor = datetime(2026, 10, 23, tzinfo=timezone.utc)
    monkeypatch.setenv("PORTWATCH_PANEL_SNAPSHOT_AT", anchor.isoformat())
    set_clock(None)
    store, client = setup(tmp_path, monkeypatch)
    base = "/api/demo/terminal"
    token = store.create("SHIPPING_COMPANY")["accessToken"]
    headers = {"Authorization": "Bearer " + token}
    fixture = {"scenarioId": "S10", "requestId": "panel-s10-test", "acknowledged": True}
    try:
        catalogue = client.get(base + "/demonstrations/scenarios", headers=headers).json()
        assert [item["id"] for item in catalogue["scenarios"]] == ["S10"]
        assert client.post(base + "/demonstrations/select", headers=headers, json={
            **fixture, "scenarioId": "S01",
        }).status_code == 409
        provider = {"domain": "vessel", "vesselId": "PWD-001",
                    "currentArrival": {"inputView": "provider"}}
        assert client.post(base + "/decisions/problems", headers=headers, json=provider).status_code == 409
        response = client.post(base + "/demonstrations/select", headers=headers, json=fixture)
        assert response.status_code == 200, response.text
        body = response.json()
        frozen = body["problem"]["evidence"]["currentEnvironment"]
        assert frozen["scenario"]["panelReplay"] is True
        assert datetime.fromisoformat(frozen["availableAt"]) == anchor
        assert client.post(base + "/decisions/problems", headers=headers, json=body["inputs"]).status_code == 409
        store.switch(token, "VESSEL_OPERATOR")
        assert client.post(base + "/demonstrations/select", headers=headers, json=fixture).status_code == 403
    finally:
        client.close()
        set_clock(None)


@pytest.mark.parametrize(("event", "args"), [
    ("socket.connect", (None, ("192.0.2.1", 443))),
    ("socket.getaddrinfo", ("example.invalid", 443, 0, 0, 0)),
    ("socket.sendto", (None, ("192.0.2.1", 53))),
])
def test_panel_blocks_provider_socket_calls(event, args):
    with pytest.raises(OSError, match="Panel mode blocks"):
        restrict_network(event, args)
    restrict_network("socket.connect", (None, ("127.0.0.1", 9294)))
