"""Wall receipts and pinned domain queries stay independent; no real footage/model run."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from PIL import Image

from src.portwatch_os.clock import WorldClock, ClockState, REPLAY, SCENARIO, HISTORICAL_MISSION, set_clock, reset_clock, world_now
from tests.test_world_clock import ScriptedWall, WALL, T0


@pytest.fixture
def clocks():
    wall = ScriptedWall(WALL)
    clock = WorldClock(wall=wall)
    set_clock(clock)
    try:
        yield clock, wall
    finally:
        reset_clock()


@pytest.mark.parametrize("mode", [REPLAY, SCENARIO, HISTORICAL_MISSION])
def test_real_demo_expiry_and_receipts_ignore_pinned_seek(tmp_path, clocks, mode):
    from backend.app.services.demo_store import DemoStore, utc_now
    clock, wall = clocks
    store = DemoStore(tmp_path / "sessions.sqlite3")
    with clock.pinned(ClockState(mode=mode, anchor=T0)):
        session = store.create("SHIPPING_COMPANY")
        assert session["issuedAt"] == WALL.isoformat()
        assert session["expiresAt"] == (WALL + timedelta(hours=12)).isoformat()
        assert utc_now() == WALL and world_now() == T0
        wall.advance(13 * 3600)
        with pytest.raises(HTTPException) as error:
            store.session(session["accessToken"])
        assert error.value.status_code == 401
        assert world_now() == T0
    assert world_now() == WALL + timedelta(hours=13)


def test_quality_and_source_age_use_query_instant_without_future_receipt_leak(clocks):
    from src.portwatch_os.intelligence.operational_quality import _now
    from src.portwatch_os.intelligence.current_environment import dated
    clock, _ = clocks
    snapshot = {"kind": "surface", "availableAt": (T0 - timedelta(minutes=30)).isoformat(), "rows": [{"value": 12}]}
    with clock.pinned(ClockState(mode=SCENARIO, anchor=T0)):
        assert _now() == T0
        assert dated(snapshot)["ageHours"] == .5
        offset = T0.astimezone(timezone(timedelta(hours=5, minutes=30)))
        assert _now(offset) == T0
        future = dated({**snapshot, "availableAt": (T0 + timedelta(seconds=1)).isoformat()})
        assert future["status"] == "UNAVAILABLE" and future["rows"] == [] and future["ageHours"] is None
        with pytest.raises(ValueError):
            _now(datetime(2021, 3, 23))
        with pytest.raises(ValueError):
            dated(snapshot, datetime(2021, 3, 23))


def test_feedback_inspection_follows_pin_and_explicit_aware_query(clocks):
    from backend.app.routes.shared_feedback import inspection_time
    clock, _ = clocks
    with clock.pinned(ClockState(mode=HISTORICAL_MISSION, anchor=T0)):
        assert inspection_time() == T0.isoformat()
        assert inspection_time((T0 - timedelta(hours=1)).isoformat()) == (T0 - timedelta(hours=1)).isoformat()
        for invalid in ((T0 + timedelta(seconds=1)).isoformat(), "2021-03-23T08:00:00"):
            with pytest.raises(HTTPException):
                inspection_time(invalid)


def test_camera_frame_bounds_are_single_aware_query_and_reference_is_unchanged(tmp_path, clocks):
    from src.portwatch_os.intelligence.camera_cv import analyse
    clock, _ = clocks
    Image.new("L", (2, 2), 0).save(tmp_path / "empty.png")
    frames = []
    for number in range(1, 17):
        path = f"frame-{number}.png"
        Image.new("L", (2, 2), 255 if number % 2 else 0).save(tmp_path / path)
        frames.append({"path": path, "observedAt": (T0 + timedelta(hours=number)).isoformat(), "berthOccupied": bool(number % 2)})
    manifest = {"rightsBasis": "SYNTHETIC QA pixels only; no actual camera feed or permission claimed", "cameraId": "SYNTHETIC_QA", "coverage": "2x2 TEST ROI", "roi": [0, 0, 2, 2], "emptyReference": "empty.png", "referenceAt": T0.isoformat(), "validationFrom": (T0 + timedelta(hours=9)).isoformat(), "frames": list(reversed(frames))}
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps(manifest))
    with clock.pinned(ClockState(mode=REPLAY, anchor=T0 + timedelta(hours=16))):
        result = analyse(source)
        assert [row["observedAt"] for row in result["observations"]] == [row["observedAt"] for row in frames]
        with pytest.raises(ValueError, match="past"):
            analyse(source, now=T0 + timedelta(hours=15))
        with pytest.raises(ValueError, match="timezone"):
            analyse(source, now=datetime(2021, 3, 24))
    assert json.loads(source.read_text()) == manifest


def test_public_seed_import_receipt_does_not_retimestamp_original_availability(tmp_path, clocks):
    from tests.test_public_evidence_seed import make_seed, AT
    from src.portwatch_os.learning.public_evidence_seed import import_public_seed
    clock, wall = clocks
    wall.at = datetime.fromisoformat(AT) + timedelta(days=1)
    import_receipt = wall.at.isoformat()
    manifest = make_seed(tmp_path / "fixture-seed")
    state = tmp_path / "isolated-import"
    with clock.pinned(ClockState(mode=SCENARIO, anchor=T0)):
        result = import_public_seed(manifest, state_dir=state, current_environment_dir=state / "current_environment", weather_db=state / "weather.sqlite3", feedback_db=state / "feedback.sqlite3")
    assert result["importedAt"] == import_receipt
    import sqlite3
    with sqlite3.connect(state / "feedback.sqlite3") as connection:
        claim = json.loads(connection.execute("SELECT body FROM shared_feedback WHERE kind='claim'").fetchone()[0])
    assert claim["firstAvailableAt"] == AT


def test_historical_shipping_inspection_uses_retained_knowledge_without_fetch(tmp_path, clocks, monkeypatch):
    from src.portwatch_os.intelligence import shipping_signals
    clock, _ = clocks
    monkeypatch.setattr(shipping_signals, "ROOT", tmp_path)
    monkeypatch.setattr(shipping_signals.requests, "get", Mock(side_effect=AssertionError("Historical inspection must not fetch")))
    monkeypatch.setattr(shipping_signals, "refresh", Mock(side_effect=AssertionError("Historical inspection must not refresh")))
    root = tmp_path / "shipping_intelligence"
    root.mkdir()
    for key, available in (("earlier", T0 - timedelta(hours=1)), ("later", T0 + timedelta(seconds=1))):
        (root / f"{key}.json").write_text(json.dumps({"id": key, "availableAt": available.isoformat(), "category": "news", "title": key, "status": "CACHED", "portCodes": []}))
    with clock.pinned(ClockState(mode=SCENARIO, anchor=T0)):
        result = shipping_signals.signals_for({"fleet": []})
    assert result["asOf"] == T0.isoformat()
    assert [row["id"] for row in result["signals"]] == ["earlier"]
