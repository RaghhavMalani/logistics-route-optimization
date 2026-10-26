"""Non-secret server release binding, independent of request headers/stores."""
import pytest

from backend.app.routes.health import release_identity


NAMES = (
    "PORTWATCH_RELEASE_SHA", "PORTWATCH_RELEASE_ENVIRONMENT", "RAILWAY_SERVICE_ID",
    "RAILWAY_ENVIRONMENT_ID", "RAILWAY_DEPLOYMENT_ID",
)
SHA = "0cbfbb465d8fbfece67de238b49b63b5694cb992"
SERVICE = "76d04c0a-a772-4e31-a16c-82fc69d18b15"


@pytest.fixture(autouse=True)
def release_env(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)


def test_unconfigured_release_is_explicitly_unknown():
    result = release_identity()
    assert result["sha"] == result["environment"] == "UNKNOWN"
    assert set(result["provider"].values()) == {"UNKNOWN"}


def test_exact_server_sha_and_provider_ids_are_projected_without_extra_environment(monkeypatch):
    monkeypatch.setenv("PORTWATCH_RELEASE_SHA", SHA.upper())
    monkeypatch.setenv("PORTWATCH_RELEASE_ENVIRONMENT", "restored-preview")
    for name in NAMES[2:]:
        monkeypatch.setenv(name, SERVICE)
    monkeypatch.setenv("RAILWAY_TOKEN", "synthetic-do-not-expose")
    monkeypatch.setenv("PORTWATCH_STATE_DIR", "/private/volume/path")
    result = release_identity()
    assert result["sha"] == SHA
    assert result["environment"] == "restored-preview"
    assert set(result["provider"].values()) == {SERVICE}
    assert "synthetic-do-not-expose" not in str(result) and "/private" not in str(result)


@pytest.mark.parametrize("value", ["short-sha", SHA + "\n", "../../.env", "pw_demo_testcredential"])
def test_malformed_release_does_not_become_a_claimed_revision(monkeypatch, value):
    monkeypatch.setenv("PORTWATCH_RELEASE_SHA", value)
    assert release_identity()["sha"] == "UNKNOWN"


def test_invalid_environment_and_provider_identifiers_are_not_echoed(monkeypatch):
    monkeypatch.setenv("PORTWATCH_RELEASE_ENVIRONMENT", "preview\nAuthorization: secret")
    monkeypatch.setenv("RAILWAY_SERVICE_ID", "https://private.example/token")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "secret=value")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "../../identity.db")
    result = release_identity()
    assert result["environment"] == "UNKNOWN"
    assert set(result["provider"].values()) == {"UNKNOWN"}


def test_client_like_headers_cannot_supply_a_release_binding(monkeypatch):
    monkeypatch.setenv("HTTP_X_PORTWATCH_RELEASE_SHA", SHA)
    monkeypatch.setenv("HTTP_X_PORTWATCH_ENVIRONMENT", "restored-preview")
    result = release_identity()
    assert result["sha"] == result["environment"] == "UNKNOWN"
