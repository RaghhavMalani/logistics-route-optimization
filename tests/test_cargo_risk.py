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
