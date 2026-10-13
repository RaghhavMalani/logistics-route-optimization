import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.error import URLError

import pytest

from src.portwatch_os.intelligence.vesselfinder import VesselStore, eligibility, fetch_json, parse_json, vessel_jobs

NOW = datetime(2026, 10, 7, 10, tzinfo=timezone.utc)
AIS = {"MMSI": 212333444, "IMO": 9876543, "NAME": "QA VESSEL", "TIMESTAMP": "2026-10-07 09:00:00 UTC", "ETA": "2026-10-08 12:00:00", "A": 160, "B": 30, "C": 16, "D": 16}
PARAMS = {"locode": "INMAA", "interval": 1440, "limit": 50, "format": "json"}


def payload(kind):
    row = {"AIS": AIS}
    if kind == "portcalls":
        row["PORTCALL"] = {"MMSI": 212333444, "IMO": 9876543, "LOCODE": "INMAA", "EVENT": "ARRIVAL", "TIMESTAMP": "2026-10-07 09:30:00 UTC"}
    return json.dumps([row]).encode()


def test_json_evidence_identity_idempotency_replay_hash_and_limits(tmp_path):
    store = VesselStore(tmp_path)
    try:
        body = payload("portcalls")
        key = store.import_json("INMAA", "portcalls", body, NOW, PARAMS)
        store.import_json("INMAA", "portcalls", body, NOW+timedelta(hours=1), PARAMS)
        state = store.workspace("INMAA", NOW+timedelta(hours=1))
        assert len(state["snapshots"]) == 1 and state["snapshots"][0]["firstSeenAt"].startswith("2026-10-07T10:00")
        record = state["records"][0]
        assert record["mmsi"] == "212333444" and record["imo"] == "9876543"
        assert record["berthAt"] is None and record["allFastAt"] is None
        assert store.workspace("INMAA", NOW-timedelta(seconds=1))["records"] == []
        with pytest.raises(ValueError, match="unavailable"):
            store.evidence("INPRT", key, NOW)
        path = store.evidence("INMAA", key, NOW)
        assert path.read_bytes() == body
        path.write_bytes(b"modified")
        with pytest.raises(ValueError, match="hash mismatch"):
            store.evidence("INMAA", key, NOW)
        with pytest.raises(ValueError):
            store.import_json("INMAA", "portcalls", body, NOW, {**PARAMS, "userkey": "secret"})
        with pytest.raises(ValueError, match="layout"):
            parse_json(b'[{"ERROR":"no credits"}]', "INMAA", "portcalls")
        with pytest.raises(ValueError, match="bounded"):
            parse_json(json.dumps([{"AIS": AIS}]*51).encode(), "INMAA", "expectedarrivals")
    finally:
        store.close()


def test_optional_disabled_no_network_and_secret_safe_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTWATCH_VESSELFINDER_ENABLED", "0")
    assert eligibility() and all(job.eligibility() for job in vessel_jobs())
    with patch("src.portwatch_os.intelligence.vesselfinder.build_opener") as opener:
        with pytest.raises(ValueError, match="disabled"):
            fetch_json("INMAA", "expectedarrivals")
        opener.assert_not_called()
    monkeypatch.setenv("PORTWATCH_VESSELFINDER_ENABLED", "1")
    monkeypatch.setenv("VESSELFINDER_API_KEY", "qa-private-key")
    with patch("src.portwatch_os.intelligence.vesselfinder.build_opener") as opener:
        opener.return_value.open.side_effect = URLError("url contains qa-private-key")
        with pytest.raises(ValueError) as error:
            fetch_json("INMAA", "portcalls")
        assert "qa-private-key" not in str(error.value)
        request = opener.return_value.open.call_args.args[0]
        assert request.full_url.startswith("https://api.vesselfinder.com/portcalls?")
        assert "limit=50" in request.full_url and "locode=INMAA" in request.full_url
    store = VesselStore(tmp_path)
    try:
        def fetch(port, kind):
            if kind == "expectedarrivals":
                raise ValueError("qa-private-key must be scrubbed")
            return payload(kind), PARAMS
        with patch("src.portwatch_os.intelligence.vesselfinder.fetch_json", side_effect=fetch):
            result = store.refresh("INMAA")
        assert result["errors"] and "qa-private-key" not in json.dumps(store.workspace("INMAA", datetime.now(timezone.utc)))
    finally:
        store.close()
