"""Adapt visitor worlds to the contracts consumed by the original terminal."""
from datetime import datetime, timedelta
from functools import lru_cache
import hashlib

from src.portwatch_os.sandbox import Sandbox


@lru_cache(maxsize=128)
def resources(root: str, demo_id: str, generation: str) -> Sandbox:
    from pathlib import Path
    # Both identifiers are server-owned; caller paths never choose a namespace.
    return Sandbox(Path(root) / "terminal" / demo_id / generation, {})


def bind(session, world, store):
    generation = hashlib.sha256(world["epoch"].encode()).hexdigest()[:16]
    scoped = resources(str(store.path.parent), session["demoId"], generation)
    scoped.world = world
    return scoped


def company_for(world):
    from src.portwatch_os.fleet.company import demo_company
    profile = demo_company(vessel_count=len(world["fleet"]))
    epoch = datetime.fromisoformat(world["epoch"])
    for vessel, row in zip(profile.vessels, world["fleet"]):
        vessel.name = row["name"]
        vessel.lat, vessel.lon = row["lat"], row["lon"]
        vessel.lane_code, vessel.destination_port = row["laneCode"], row["portCode"]
        vessel.hours_to_chokepoint = {"SUEZ" if row["laneCode"] == "EUR_IND" else "HORMUZ": row["hoursToRisk"]}
        shift = 0
        proposal = world.get("terminalProposal") or world.get("proposal")
        outcome = world.get("currentArrivalOutcome") or {}
        if proposal and proposal["vesselId"] == row["id"] and (
            not proposal.get("environmentEvidenceId") or outcome.get("environmentEvidenceId") == proposal["environmentEvidenceId"]):
            shift = proposal["etaShiftHours"] or 0
        vessel.eta = (epoch + timedelta(hours=row["etaHours"] + shift)).isoformat()
    return profile


def event_for(world):
    from src.portwatch_os.global_eye.model import GlobalEvent, EventSource
    return GlobalEvent(
        event_id=world["event"]["id"], title=world["event"]["title"] + " · fictional demo",
        category="chokepoint_disruption", region="Suez", lat=30.0, lon=32.6,
        geolocation_basis="chokepoint_centroid", first_seen=world["epoch"], last_seen=world["epoch"],
        sources=[EventSource(outlet="DEMO_SCENARIO", feed="DEMO_SCENARIO", title="Visitor-owned assumed restriction")],
        source_count=0, confidence=1.0, severity=1.0, probability=None,
        horizon_hours=world["event"]["closureHours"], chokepoints=["SUEZ"],
        claim="ASSUMPTION: closure for this simulation only", data_source="DEMO_SCENARIO",
        excerpts=[world["meaning"]],
    )
