from unittest.mock import Mock

import pytest

from backend.app.routes import screens
from src.portwatch_os.clock import ClockState, SCENARIO, world_now
from test_demo_terminal import setup


@pytest.fixture
def home_client(tmp_path, monkeypatch):
    store, client = setup(tmp_path, monkeypatch)
    now = world_now()
    clock = Mock()
    clock.now.return_value = now
    clock.state = ClockState(mode=SCENARIO, anchor=now, set_at=now, rate=0)
    monkeypatch.setattr(screens, "get_clock", lambda: clock)
    monkeypatch.setattr("requests.sessions.Session.request", Mock(side_effect=AssertionError("Screen read contacted a provider")))
    yield store, client
    client.close()


@pytest.mark.parametrize(("screen", "role", "role_section"), [
    ("company-home", "SHIPPING_COMPANY", "/company/fleet?company_id=portwatch-demo-shipping"),
    ("port-home", "PORT_AUTHORITY", "/model/INNSA/decision"),
    ("vessel-home", "VESSEL_OPERATOR", "/model/INNSA/forecast"),
    ("admin-home", "NATIONAL_ADMIN", "/fabric/health?mode=DEMO"),
])
def test_screen_preserves_role_contracts(home_client, screen, role, role_section):
    store, client = home_client
    session = store.create(role)
    headers = {"Authorization": "Bearer " + session["accessToken"], "Accept-Encoding": "br"}
    base = "/api/demo/terminal"
    path = base + "/screens/" + screen
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text[:1000]
    assert response.headers["content-encoding"] == "br"
    assert response.headers["cache-control"] == "private, no-cache"
    assert response.headers["x-portwatch-cache"] == "MISS"
    packet = response.json()
    assert packet["session"]["user"]["role"] == role
    assert "accessToken" not in packet["session"]
    assert packet["sections"][role_section]["status"] == 200
    expected = client.get(base + "/ports/registry", headers=headers)
    assert packet["sections"]["/ports/registry"]["data"] == expected.json()
    match = client.get(path, headers={**headers, "If-None-Match": response.headers["etag"]})
    assert match.status_code == 304
    assert match.headers["x-portwatch-cache"] == "HIT"
    assert match.content == b""

    another = store.create(role)
    other = client.get(path, headers={**headers, "Authorization": "Bearer " + another["accessToken"],
                                      "If-None-Match": response.headers["etag"]})
    assert other.status_code == 200
    assert other.headers["x-portwatch-cache"] == "MISS"
    assert other.json()["session"]["demoId"] != packet["session"]["demoId"]


def test_role_prefetch_stays_in_visitor_and_requires_explicit_opt_in(home_client):
    store, client = home_client
    session = store.create("SHIPPING_COMPANY")
    headers = {"Authorization": "Bearer " + session["accessToken"]}
    target = "/api/demo/terminal/screens/port-home"
    assert client.get(target).status_code == 401
    assert client.get(target, headers=headers).status_code == 403
    projected = client.get(target + "?prefetch=true", headers=headers)
    assert projected.status_code == 200, projected.text[:1000]
    assert projected.json()["session"]["demoId"] == session["demoId"]
    assert projected.json()["session"]["user"]["role"] == "PORT_AUTHORITY"
    assert store.session(session["accessToken"])["user"]["role"] == "SHIPPING_COMPANY"
    assert client.get("/api/screens/port-home?prefetch=true", headers=headers).status_code == 401


@pytest.mark.parametrize(("actor", "screen", "status"), [
    ("NATIONAL_ADMIN", "port-home", 200),
    ("SHIPPING_COMPANY", "vessel-home", 200),
    ("PORT_AUTHORITY", "admin-home", 403),
    ("VESSEL_OPERATOR", "company-home", 403),
])
def test_direct_workspace_entry_preserves_actor_scope(home_client, actor, screen, status):
    store, client = home_client
    session = store.create(actor)
    token = session["accessToken"]
    response = client.get(
        "/api/demo/terminal/screens/" + screen,
        headers={"Authorization": "Bearer " + token},
    )
    assert response.status_code == status, response.text[:1000]
    if status == 200:
        assert response.json()["session"]["user"]["role"] == actor
        assert response.json()["session"]["demoId"] == session["demoId"]
    assert store.session(token)["user"]["role"] == actor
