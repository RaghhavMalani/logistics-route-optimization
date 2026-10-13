import json
import hashlib
import numpy as np
import pandas as pd
import pytest
from src.forecasting.neural_fusion import features, hide_source_inputs, fit
from src.portwatch_os.twin.constrained_rl import MaskedQLearningPolicy, save_evaluated_policy, load_candidate


def test_training_outage_matches_missing_provider_inference_inputs():
    base = pd.DataFrame({"port_id": ["A"], "horizon_day": [5]})
    values = np.array([[[1., 3., 7.], [4., 6., 12.], [8., 10., 18.]]])
    x, mask = features(base, values, ["A"])
    dropped = mask.copy(); dropped[:, 1] = False
    hidden = hide_source_inputs(x, dropped)
    missing = values.copy(); missing[:, 1, :] = np.nan
    inference, inference_mask = features(base, missing, ["A"])
    assert np.array_equal(hidden, inference) and np.array_equal(dropped, inference_mask)
    assert not np.array_equal(x, hidden)
    assert np.array_equal(x, features(base, values, ["A"])[0])


def test_already_missing_specialist_cannot_leak_its_interval_width():
    base = pd.DataFrame({"port_id": ["A"], "horizon_day": [5]})
    values = np.array([[[1., 3., 7.], [4., np.nan, 99.], [8., 10., 18.]]])
    x, mask = features(base, values, ["A"])
    assert x[0, [2, 5, 8]].tolist() == [0., 0., 0.]


def test_rejected_experiment_serializes_status_identity_and_preserves_table(tmp_path):
    policy = MaskedQLearningPolicy({"context": [1., 2., 3., 4.]})
    report = save_evaluated_policy(tmp_path, policy, {"status": "REJECTED", "test": [{"meanReward": -5.}]})
    artifact = json.loads((tmp_path/"constrained_rl.json").read_text())
    assert artifact["status"] == report["status"] == "REJECTED"
    assert artifact["experimentId"] == report["experimentId"]
    assert artifact["table"] == policy.table
    assert artifact["evaluationReportSha256"] == hashlib.sha256((tmp_path/"constrained_rl_report.json").read_bytes()).hexdigest()
    assert load_candidate(tmp_path/"constrained_rl.json").experiment_status == "REJECTED"
    (tmp_path/"constrained_rl_report.json").unlink()
    assert load_candidate(tmp_path/"constrained_rl.json").experiment_status == "REJECTED"


def test_mismatched_policy_report_is_refused(tmp_path):
    save_evaluated_policy(tmp_path, MaskedQLearningPolicy(), {"status": "REJECTED"})
    report = tmp_path/"constrained_rl_report.json"
    data = json.loads(report.read_text()); data["experimentId"] = "another-run"
    report.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="identities"):
        load_candidate(tmp_path/"constrained_rl.json")
