"""Adapt visitor worlds to the contracts consumed by the original terminal."""
from datetime import datetime, timedelta
from dataclasses import replace
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
    owned = resources(str(store.path.parent), session["demoId"], generation)
    # Cache durable domain resources, while each request holds its own world
    # snapshot and save callback. Concurrent map polls must not replace inputs
    # under a comparison or approval that is already running.
    return Sandbox(owned.root, world, resources=owned.resources, lock=owned.lock)


def demo_hulls(world, identity=None):
    from backend.app.identity import current_identity, may_see_vessel

    identity = identity if identity is not None else current_identity.get()
    if identity is None:
        return []
    # The demo session has already authenticated this visitor's fictional world.
    # This local principal is never installed in the operational request context.
    visitor = replace(identity, verified=True)
    return [row for row in world["fleet"] if may_see_vessel(visitor, {
        "id": row["id"], "operatorOrganisation": row.get("operatorOrganisation", world["organisation"]),
        "destinationPort": row["portCode"],
    })]


def demo_principal(user):
    from backend.app.identity import Identity

    return Identity(role=user["role"], actor=user["id"], port_code=user["portCode"],
                    organisation=user["organisation"], vessel_ids=tuple(user["vesselIds"]))


def company_for(world, *, allowed_ids=None):
    from src.portwatch_os.fleet.company import demo_company
    profile = demo_company(vessel_count=len(world["fleet"]))
    epoch = datetime.fromisoformat(world["epoch"])
    for vessel, row in zip(profile.vessels, world["fleet"]):
        vessel.vessel_id = row["id"]
        vessel.name = row["name"]
        vessel.lat, vessel.lon = row["lat"], row["lon"]
        vessel.lane_code, vessel.destination_port = row["laneCode"], row["portCode"]
        if row.get('serviceSpeedKn') is not None:
            vessel.service_speed_kn = row['serviceSpeedKn']
        vessel.hours_to_chokepoint = {"SUEZ" if row["laneCode"] == "EUR_IND" else "HORMUZ": row["hoursToRisk"]}
        shift = 0
        proposal = world.get("terminalProposal") or world.get("proposal")
        outcome = world.get("currentArrivalOutcome") or {}
        if proposal and proposal["vesselId"] == row["id"] and (
            not proposal.get("environmentEvidenceId") or outcome.get("environmentEvidenceId") == proposal["environmentEvidenceId"]):
            shift = proposal["etaShiftHours"] or 0
        vessel.eta = (epoch + timedelta(hours=row["etaHours"] + shift)).isoformat()
    if allowed_ids is not None:
        profile.vessels = [vessel for vessel in profile.vessels if vessel.vessel_id in allowed_ids]
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
