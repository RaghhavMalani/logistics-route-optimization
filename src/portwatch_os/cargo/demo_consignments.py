"""Fixed fictional terms for the three visitor-owned Company hulls."""

from datetime import datetime, timedelta

from src.portwatch_os.decision.commercial import Consignment, instant

DEMO_BASIS = "DEMO ASSUMPTION: fictional consignment terms for conditional comparison."
_ROWS = (
    ("PWD-001", "Temperature-controlled produce", "0709", "reefer", 84_000, 190, 1, 195),
    ("PWD-001", "Machine parts for scheduled assembly", "8483", "dry", 58_000, 185, 1, None),
    ("PWD-001", "Bulk mineral filler", "2521", "dry", 8_000, 275, 3, None),
    ("PWD-002", "Chilled fish", "0302", "reefer", 96_000, 154, 1, 156),
    ("PWD-002", "Frozen vegetables", "0710", "reefer", 37_000, 169, 2, 194),
    ("PWD-002", "Paint and varnish", "3208", "DG", 29_000, 191, 2, None),
    ("PWD-003", "Temperature-controlled fruit", "0808", "reefer", 44_000, 99, 1, 109),
    ("PWD-003", "Flammable industrial solvent", "3814", "DG", 21_000, 120, 2, None),
    ("PWD-003", "Bulk gypsum", "2520", "dry", 6_000, 165, 3, None),
)


def assumption(value):
    return {"value": value, "basis": "assumption", "source": DEMO_BASIS}


def usd(amount):
    return {"amount": amount, "currency": "USD"}


def demo_consignments(epoch: str | datetime) -> dict[str, list[dict]]:
    at = instant(epoch)
    declaration = {
        "kind": "SIMULATION",
        "source": DEMO_BASIS,
        "actor": "demo-company",
        "firstAvailableAt": at,
        "applicableFrom": at,
        "applicableThrough": at + timedelta(days=366),
    }
    by_hull = {}
    for index, (vessel, goods, hs, handling, value, due, priority, shelf) in enumerate(_ROWS, 1):
        deadline = at + timedelta(hours=due)
        terms = {
            "commodityHsCode": assumption(hs),
            "currency": assumption("USD"),
            "cifValue": assumption(usd(value)),
            "handlingClass": assumption(handling),
            "perishable": assumption(handling == "reefer"),
            "deliveryDeadline": assumption(deadline),
            "latePenalty": assumption({
                "amount": usd({1: 960, 2: 180, 3: 25}[priority]),
                "unit": "per_day" if priority != 3 else "flat",
            }),
            "freeTimeHours": assumption(24),
            "detentionFreeHours": assumption(48),
            "demurrageRatePerDay": assumption(usd(75)),
            "detentionRatePerDay": assumption(usd(45)),
            "annualInventoryRate": assumption("0.11"),
            "priority": assumption(priority),
            "margin": assumption(usd(value * 0.10)),
            "cargoPolicyRate": assumption("0.0018"),
            "deductible": assumption(usd(500)),
            "separateDeductibleEventProbability": assumption("0.005"),
            "excludedAreas": assumption([]),
            "warRiskAreas": assumption([{
                "area": "RED_SEA",
                "required": assumption(True),
                "premiumRate": assumption("0.003"),
            }]),
            "generalAverageExposed": assumption(True),
        }
        if index % 3 == 0:
            terms["insuredValue"] = assumption(usd(value + 500))
        if handling == "reefer":
            terms.update(
                reeferSetPointC=assumption(2 if index != 5 else -18),
                maxUnpoweredHours=assumption(5),
                remainingShelfLifeHours=assumption(shelf),
            )
        if handling == "DG":
            terms["imdgClass"] = assumption("3")
        shipment = Consignment(
            id=f"DEMO-CARGO-{index:02d}",
            goodsClass=goods,
            hsCode=hs,
            destinationPort="INNSA",
            event="DECLARED_FINAL_DELIVERY",
            deadline=deadline,
            shelfLifeReferenceAt=at if shelf is not None else None,
            remainingShelfLifeHours=shelf,
            delayCostParty="carrier",
            riskTerms=terms,
            basis=declaration,
        )
        by_hull.setdefault(vessel, []).append(shipment.model_dump(mode="json"))
    return by_hull
