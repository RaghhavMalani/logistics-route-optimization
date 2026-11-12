"""Cargo API exercises the owned projection, canonical retention and privacy boundary."""

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response

from backend.app.domains.voyages import cargo_risk_inputs, commercial
from src.portwatch_os.cargo.demo_consignments import demo_consignments
from src.portwatch_os.decision.actions import KEEP_PLAN, SLOW_STEAM
from src.portwatch_os.decision.model import (
    FEASIBLE, SHIPPING_COMPANY, DecisionActor, DecisionEvaluation, DecisionOption, DecisionProblem, known,
)
from src.portwatch_os.ledger.store import SqliteLedgerStore


def test_cargo_report_retains_exact_seeded_bytes_and_privacy(tmp_path, monkeypatch):
    at = datetime(2026, 11, 6, tzinfo=timezone.utc)
    port = "INPRT"
    options = [
        DecisionOption(
            option_id=id_, action=action, label=id_, actor=SHIPPING_COMPANY, status=FEASIBLE,
            is_baseline=id_ == "keep",
            evaluation=DecisionEvaluation(
                objectives={"fuel": known(fuel, "tonne", basis="Fictional S10 test")},
                derived={"approachClearAt": (at + timedelta(hours=27)).isoformat(), "destinationPort": port},
            ),
        )
        for id_, action, fuel in (("keep", KEEP_PLAN, 22), ("slow", SLOW_STEAM, 19))
    ]
    problem = DecisionProblem(
        decision_id="s10-comparison", created_at=at.isoformat(), at=at.isoformat(), domain="vessel",
        world_revision={}, world_state_id="sim", subject_type="vessel", subject_id="PWD-001",
        subject_label="PW Meridian", actor=DecisionActor(SHIPPING_COMPANY),
        baseline_option_id="keep", options=options,
        evidence={"currentEnvironment": {"passageComparison": {"options": []}}},
    )
    scoped = SimpleNamespace(root=tmp_path, world={"cargoRiskConsignments": demo_consignments(at)})
    ledger = SqliteLedgerStore(tmp_path / "private.sqlite3")
    engine = SimpleNamespace(ledger=ledger)
    actor = SimpleNamespace(actor="private-company")
    request = commercial.CargoRiskRequest(rule="R1", seed=19, jobId=uuid4())
    selection = commercial.CargoRiskPortfolio(
        selections=[{"decisionId": problem.decision_id, "optionId": "slow"}], seed=19,
    )
    monkeypatch.setattr(cargo_risk_inputs, "configured_store", lambda: None)
    try:
        with pytest.raises(HTTPException) as denied:
            commercial.cargo_risk_study(problem.decision_id, request, Response())
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as denied:
            commercial.cargo_risk_portfolio(selection, Response())
        assert denied.value.status_code == 403

        monkeypatch.setattr(commercial, "owned", lambda *_: (scoped, actor, engine, problem))
        first = commercial.cargo_risk_study(problem.decision_id, request, Response())
        assert first.status_code == 200
        assert first.headers["cache-control"] == "private, no-store"
        report = json.loads(first.body)
        assert report["status"] == "SHADOW"
        assert report["decision"]["optionId"] == "slow"
        assert len(report["cargo"]) == 3
        assert report["seed"] == 19 and len(report["inputHash"]) == 64
        assert report["sourceBasis"]["options"]["keep"]["weather"].startswith("Frozen approach gate")
        assert report["options"][0]["cost"]["expected"] is None
        assert any(key.endswith("general_average") for key in report["options"][0]["cost"]["unknown"])
        second = commercial.cargo_risk_study(problem.decision_id, request.model_copy(update={"jobId": uuid4()}), Response())
        assert second.body == first.body
        assert ledger.get_decision(report["recordId"]).kind == "cargo_risk_shadow"
        portfolio = json.loads(commercial.cargo_risk_portfolio(selection, Response()).body)
        assert portfolio["status"] == "SHADOW"
        assert portfolio["cost"]["expected"] is None
        assert len(portfolio["missByVoyage"]["PWD-001"]) == 3
        assert portfolio["seed"] == 19 and len(portfolio["inputHash"]) == 64
    finally:
        ledger.close()
