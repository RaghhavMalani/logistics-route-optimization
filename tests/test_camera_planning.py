from datetime import timedelta
from types import SimpleNamespace

import pytest

from src.portwatch_os.clock import world_now
from src.portwatch_os.intelligence.camera_planning import CameraPlanningAssumption, apply_camera_hold
from src.portwatch_os.intelligence.cameras import Camera, CameraEvidence, CameraRegistry
from src.portwatch_os.twin.policies import FirstComeFirstServed
from src.portwatch_os.twin.rl import PortEnvironment, ScenarioSpec
from src.portwatch_os.twin.simulation import SimulationConfig, simulate


def setup_camera(tmp_path, *, reviewed=True, minutes=5):
    store = CameraRegistry(tmp_path / "camera.db")
    store.register(Camera(id="test-view", portCode="INNSA", name="Test-only berth",
                          lat=18.95, lon=72.95, coverage="Synthetic test viewpoint",
                          source="Test fixture", rightsBasis="Generated test evidence"), "test.operator")
    store.record_evidence(CameraEvidence(id="test-observation", cameraId="test-view",
        observedAt=(world_now() - timedelta(minutes=minutes)).isoformat(), kind="berth_occupied",
        confidence=.9, summary="Test fixture occupancy", source="Generated test evidence",
        reviewed=reviewed), "test.operator")
    state = PortEnvironment(ScenarioSpec(port_code="INNSA", berth_count=1, arrivals=6,
        horizon_hours=24, weather_range=(0, 0))).build_state(168)
    for berth in state.berths:
        berth.occupied_by = None
        berth.free_at_hour = None
    for call in state.calls:
        call.loa_m = 100
        call.draught_m = 5
        call.eta_hour = 0
        call.moves = 100
    who = SimpleNamespace(verified=True, role="PORT_AUTHORITY", port_codes=("INNSA",), actor="test.operator")
    request = CameraPlanningAssumption(evidenceId="test-observation",
        berthId=state.berths[0].berth_id, holdHours=6)
    return store, state, who, request


def test_reviewed_camera_hold_changes_existing_simulation_without_editing_observed_state(tmp_path):
    store, state, who, request = setup_camera(tmp_path)
    before = state.to_dict()
    changed, basis = apply_camera_hold(state, request, store, who)
    assert state.to_dict() == before
    assert changed.berths[0].occupied_by == "camera-hold:test-observation"
    assert basis["assumption"]["source"] == "OPERATOR_ASSUMPTION"
    baseline = simulate(state, FirstComeFirstServed(), SimulationConfig(horizon_hours=24))
    affected = simulate(changed, FirstComeFirstServed(), SimulationConfig(horizon_hours=24))
    assert not affected.violations
    assert affected.metrics["meanWaitHours"] > baseline.metrics["meanWaitHours"]


@pytest.mark.parametrize("reviewed,minutes", [(False, 5), (True, 31)])
def test_unreviewed_or_old_occupancy_cannot_enter_current_planning(tmp_path, reviewed, minutes):
    store, state, who, request = setup_camera(tmp_path, reviewed=reviewed, minutes=minutes)
    with pytest.raises(ValueError):
        apply_camera_hold(state, request, store, who)


def test_camera_hold_cannot_escape_ownership_or_berth_scope(tmp_path):
    store, state, who, request = setup_camera(tmp_path)
    for principal in (SimpleNamespace(verified=False, role=who.role, port_codes=who.port_codes),
                      SimpleNamespace(verified=True, role=who.role, port_codes=("INMAA",))):
        with pytest.raises(ValueError, match="verified authority"):
            apply_camera_hold(state, request, store, principal)
    with pytest.raises(ValueError, match="selected berth"):
        apply_camera_hold(state, request.model_copy(update={"berthId": "unrelated-berth"}), store, who)


def test_computer_vision_evidence_requires_frame_and_roi():
    base = dict(id="cv-test", cameraId="test-view", observedAt=world_now().isoformat(),
                kind="berth_occupied", confidence=.8, summary="Generated test", source="Test",
                method="computer_vision", modelVersion="test-v1")
    with pytest.raises(ValueError, match="frame hash and ROI"):
        CameraEvidence(**base)
    evidence = CameraEvidence(**base, frameSha256="a" * 64, roi=(0, 0, 20, 20))
    assert evidence.reviewed is False


def test_camera_scenario_uses_existing_decision_engine_and_preserves_evidence_in_ledger(tmp_path, monkeypatch):
    from backend.app.routes import decisions, intelligence, port_twin
    from backend.app import identity
    from src.portwatch_os.decision.engine import DecisionEngine
    from src.portwatch_os.decision.model import DecisionActor
    from src.portwatch_os.ledger.store import SqliteLedgerStore

    store, state, who, request = setup_camera(tmp_path)
    ledger = SqliteLedgerStore(tmp_path / "scenario-ledger.db")
    engine = DecisionEngine(ledger=ledger)
    observed = SimpleNamespace(state_id="test-world", summary=lambda: {"revision": {"mode": "DEMO"}})
    monkeypatch.setattr(identity, "require_verified", lambda: who)
    monkeypatch.setattr(intelligence, "require_verified", lambda: who)
    monkeypatch.setattr(intelligence, "registry", lambda: store)
    monkeypatch.setattr(port_twin, "build_state_for", lambda _: state)
    monkeypatch.setattr(decisions, "_observed_state", lambda *args: (None, [], observed))
    try:
        problem = decisions._port_problem(engine, {"portCode": "INNSA", "cameraPlanning": request.model_dump()},
            DecisionActor(role="PORT_AUTHORITY", port_code="INNSA"), world_now(), engine.basis, "DEMO", "INNSA")
        assert problem.evidence["cameraPlanning"]["observation"]["id"] == "test-observation"
        assert any("operator assumptions" in note for note in problem.notes)
        assert ledger.get_decision_problem(problem.decision_id).problem["evidence"]["cameraPlanning"] == problem.evidence["cameraPlanning"]
        assert state.berths[0].occupied_by is None
        assert problem.options and problem.baseline_option_id
    finally:
        ledger.close()
