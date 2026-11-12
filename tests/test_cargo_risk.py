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
