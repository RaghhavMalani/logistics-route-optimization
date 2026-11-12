from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.portwatch_os.cargo.demo_consignments import demo_consignments
from src.portwatch_os.decision.commercial import CargoRiskTerms, Consignment, insured_value_for_risk

AT = datetime(2026, 11, 12, tzinfo=timezone.utc)


def test_optional_risk_terms_preserve_legacy_serialization():
    row = demo_consignments(AT)["PWD-001"][0]
    del row["riskTerms"]
    cargo = Consignment.model_validate(row)
    assert cargo.riskTerms is None
    assert cargo.model_dump(mode="json") == row
    assert insured_value_for_risk(cargo) is None


def test_cif_default_and_declared_override_keep_their_own_basis():
    demo = demo_consignments(AT)["PWD-001"]
    derived = insured_value_for_risk(Consignment.model_validate(demo[0]))
    assert derived.value.amount == Decimal("92400")
    assert derived.value.currency == "USD"
    assert derived.basis == "assumption"
    assert derived.source.startswith("CIF × 1.10")
    explicit = insured_value_for_risk(Consignment.model_validate(demo[2]))
    assert explicit.value.amount == Decimal("8500")
    assert explicit.source.startswith("DEMO ASSUMPTION")


def test_seeded_terms_cover_all_demo_hulls_and_require_provenance():
    cargo = demo_consignments(AT)
    assert cargo == demo_consignments(AT)
    assert {key: len(rows) for key, rows in cargo.items()} == {
        "PWD-001": 3, "PWD-002": 3, "PWD-003": 3,
    }
    terms = [shipment["riskTerms"] for rows in cargo.values() for shipment in rows]
    assert {row["handlingClass"]["value"] for row in terms} == {"dry", "reefer", "DG"}
    assert all(term["source"].startswith("DEMO ASSUMPTION") and term["basis"] == "assumption"
               for row in terms for term in row.values() if term is not None)
    with pytest.raises(ValidationError):
        CargoRiskTerms(priority={"value": 1})
    with pytest.raises(ValidationError):
        CargoRiskTerms(deliveryDeadline={"value": "2026-11-12T12:00:00", "basis": "contract", "source": "Example contract"})


def test_component_formulas_by_hand():
    from datetime import timedelta
    import numpy as np
    from src.portwatch_os.cargo.demo_consignments import assumption, usd
    from src.portwatch_os.decision.cargo_risk import CostState, evaluate_consignment

    row = demo_consignments(AT)["PWD-001"][0]
    row["riskTerms"].update(
        deliveryDeadline=assumption(AT + timedelta(hours=15)),
        remainingShelfLifeHours=assumption(30),
        generalAverageContribution=assumption(usd(1_400)),
        generalAverageEventProbability=assumption("0.1"),
    )
    state = CostState(np.array([15.0, 39.0]), 15, np.array([24.0, 48.0]),
                      np.array([48.0, 72.0]), np.array([6.0, 0.0]), ("RED_SEA",),
                      np.array([0.001, 0.5]), np.array([0.5, 0.05]))
    result = evaluate_consignment(Consignment.model_validate(row), state, AT, "USD")
    assert not result.costs.unknown
    assert result.on_time.tolist() == [True, False]
    assert result.spoilage.tolist() == [True, True]
    amounts = result.costs.components
    expected = {
        "late_penalty": [0, 960],
        "demurrage": [0, 75],
        "detention": [0, 45],
        "inventory_carrying": [0, 84_000 * .11 * 24 / 8760],
        "spoilage": [84_000, 84_000],
        "cargo_premium": [92_400 * .0018] * 2,
        "war_risk_premium": [92_400 * .003] * 2,
        "deductible_exposure": [500, 0],
        "general_average": [0, 1_400],
    }
    assert set(amounts) == set(expected)
    for component, values in expected.items():
        np.testing.assert_allclose(amounts[component], values)
    np.testing.assert_allclose(result.costs.total, np.sum(list(expected.values()), axis=0))


def test_flat_penalty_unknown_losses_and_route_exclusions():
    from datetime import timedelta
    import numpy as np
    from src.portwatch_os.cargo.demo_consignments import assumption
    from src.portwatch_os.decision.cargo_risk import CostState, evaluate_consignment, summarize_cost

    row = demo_consignments(AT)["PWD-001"][2]
    row["riskTerms"].update(
        deliveryDeadline=assumption(AT + timedelta(hours=20)),
        excludedAreas=assumption(["RED_SEA"]),
    )
    state = CostState(np.array([20.0, 20.01, 100.0]), 20, np.zeros(3), np.zeros(3),
                      route_areas=("red_sea",), deductible_uniform=np.zeros(3))
    result = evaluate_consignment(Consignment.model_validate(row), state, AT, "USD")
    assert result.costs.components["late_penalty"].tolist() == [0, 25, 25]
    assert result.costs.components["spoilage"].tolist() == [0, 0, 0]
    assert result.excluded_areas == ("RED_SEA",)
    assert set(result.costs.unknown) == {"deductible_exposure", "general_average"}
    assert result.costs.total is None
    assert summarize_cost(result.costs)["expected"] is None
    assert summarize_cost(result.costs)["knownSubtotal"]["expected"] > 0

    foreign = evaluate_consignment(Consignment.model_validate(row), state, AT, "EUR")
    assert "FX basis" in foreign.costs.unknown["late_penalty"]
    from dataclasses import replace
    with_fx = evaluate_consignment(Consignment.model_validate(row), replace(state, fx_to_reporting={"USD": .8}), AT, "EUR")
    assert with_fx.costs.components["late_penalty"].tolist() == [0, 20, 20]


def test_rollup_prices_correlated_losses_and_cvar_boundary_mass():
    import numpy as np
    from src.portwatch_os.decision.cargo_risk import CostBreakdown, combine_costs, cvar, summarize_cost

    a = CostBreakdown(2, {"loss": np.array([100.0, 0.0])}, {}, {})
    b = CostBreakdown(2, {"loss": np.array([0.0, 100.0])}, {}, {})
    voyage = combine_costs({"A": a, "B": b}, 2)
    assert summarize_cost(voyage)["cvar95"] == 100
    assert cvar(np.array([0.0] * 96 + [100.0] * 4)) == pytest.approx(80)
    with pytest.raises(ValueError, match="aligned futures"):
        combine_costs({"A": a}, 3)


def risk_study(**changes):
    from src.portwatch_os.decision.cargo_sampling import RiskStudy
    options = [
        {"id": "keep", "label": "Keep", "action": "proceed", "cleanDeliveryHours": 175,
         "reachClosureHour": 26, "areas": ["RED_SEA"], "dwellHours": 12, "detentionHours": 14,
         "unpoweredHours": 2, "fuelTonnes": 50, "source": "ASSUMPTION · test passage"},
        {"id": "slow", "label": "Slow steam", "action": "slow_steam", "cleanDeliveryHours": 188,
         "reachClosureHour": 39, "areas": ["RED_SEA"], "dwellHours": 12, "detentionHours": 14,
         "unpoweredHours": 1, "fuelTonnes": 44, "source": "ASSUMPTION · test passage"},
    ]
    inputs = dict(
        problemId="test", at=AT, reportingCurrency="USD", keepOptionId="keep", plannedDeliveryHours=175,
        options=options, consignments=demo_consignments(AT)["PWD-001"],
        closure={"medianHours": 35, "source": "ASSUMPTION · test closure"},
        handling={"kind": "DISCRETE", "values": [0, 4], "weights": [.5, .5],
                  "declaration": "ASSUMPTION · test handling"},
        fuel={"low": 440, "high": 620, "currency": "USD", "source": "ASSUMPTION · test fuel"},
        scope="ASSUMPTION · test only",
    )
    return RiskStudy(**(inputs | changes))


def test_sobol_prefix_inverse_distributions_and_shared_futures():
    import numpy as np
    from src.portwatch_os.decision.cargo_sampling import (
        ClosureBasis, Sampling, closure_icdf, handling_icdf, map_futures, sample_losses,
        triangular_icdf, worlds_for,
    )

    model = risk_study()
    config = Sampling(seed=381)
    a, b = worlds_for(config, 5), worlds_for(config, 6)
    np.testing.assert_array_equal(a, b[:, :32])
    assert not np.array_equal(a[0], a[1])
    np.testing.assert_allclose(triangular_icdf(np.array([0, .25, 1]), 0, 1, 4), [0, 1, 4])
    np.testing.assert_array_equal(handling_icdf(np.array([0, .499, .5, .99]), model.handling), [0, 0, 4, 4])
    closure = ClosureBasis(medianHours=28, logSigma=.55, fizzleProbability=.2, source="Test assumption")
    np.testing.assert_allclose(closure_icdf(np.array([.1, .6]), closure), [0, 28])
    worlds = map_futures(model, a)
    option = model.options[0]
    other = option.model_copy(update={"id": "clone"})
    first = sample_losses(model, option, worlds)
    second = sample_losses(model, other, worlds)
    np.testing.assert_array_equal(first.arrival, second.arrival)
    np.testing.assert_array_equal(first.costs.known_subtotal, second.costs.known_subtotal)


def test_adaptive_requires_two_ranks_and_reproducible_bytes():
    import json
    from src.portwatch_os.decision.cargo_sampling import Sampling, adaptive, study_bytes

    model = risk_study(consignments=[], timeCostPerHour=300, timeCostBasis="ASSUMPTION · time cost")
    config = Sampling(seed=68, minPower=4, maxPower=7, standardErrorThreshold=100000)
    stages = []
    _, _, info = adaptive(model, config, progress=stages.append)
    assert info["converged"] and info["n"] == 256
    assert len(stages) == 2 and not stages[0]["stable"] and stages[1]["stable"]
    a = study_bytes(model, config)
    assert a == study_bytes(model.model_validate_json(model.model_dump_json()), config)
    b = study_bytes(model, config.model_copy(update={"seed": 69}))
    assert json.loads(a)["sampleHash"] != json.loads(b)["sampleHash"]
    assert json.loads(a)["inputHash"] == json.loads(b)["inputHash"]


def test_retained_weather_and_fx_respect_as_of_cutoff():
    from datetime import timedelta
    from src.portwatch_os.decision.cargo_market import retained_fx, retained_weather
    from src.portwatch_os.freshness.source_snapshots import Snapshot, SnapshotStore

    store = SnapshotStore("sqlite:///:memory:")
    store.initialize()
    future = AT + timedelta(hours=1)
    weather = {"availableAt": AT.isoformat(), "ports": {"INNSA": {
        "units": {"wind_speed_10m": "kn"},
        "hourly": {"time": [future.isoformat()], "wind_speed_10m_member01": [11], "wind_speed_10m_member02": [21]},
    }}}
    store.record("published", "open-meteo-ensemble", AT, snapshot=Snapshot(weather, None))
    store.record("published", "open-meteo-ensemble", future, snapshot=Snapshot(
        weather | {"availableAt": future.isoformat()}, None))
    assert retained_weather(store, AT, "INNSA", future).windKn == (11, 21)
    assert retained_weather(store, AT, "INNSA", future + timedelta(days=3)) is None
    for days, usd_rate in ((-2, 1.1), (-1, 1.2), (1, 1.3)):
        stamp = AT + timedelta(days=days)
        rates = [{"quote": quote, "rate": rate, "date": stamp.date().isoformat()}
                 for quote, rate in [("USD", usd_rate), ("INR", 100)]]
        store.record("published", "frankfurter-ecb-fx", stamp, snapshot=Snapshot({"rates": rates}, stamp))
    history = retained_fx(store, AT)
    assert [row["USD"] for row in history.datedQuotes] == [1.1, 1.2]
