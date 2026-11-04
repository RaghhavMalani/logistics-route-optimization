"""A frozen, declared connection on one passage; no booking or cargo execution.

The cargo model's available_hour means the start of its *whole* handling chain,
including discharge.  We pass clear approach + the explicit approach-to-start
interval, never an already discharged/readied time.  UTC comparison time is
simulation hour zero.  Missing declarations stay unknown; VesselCapacity's
legacy implicit cutoff is deliberately never consumed here.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math

from src.portwatch_os.cargo.model import (
    CARGO_CLASSES, DISCHARGE_TEU_PER_HOUR, LOAD_TEU_PER_HOUR,
    TRANSFER_OVERHEAD_HOURS, Shipment, StorageZone, VesselCapacity,
    check_compatibility, check_zone, discharge_hours, evaluate_connection,
    load_hours, yard_move_hours,
)

VERSION = "passage-cargo-commitment-v1"
MODEL_VERSION = "cargo-model-schematic-v1"


def _time(value, label):
    if not isinstance(value, str):
        raise ValueError(label + " must be an aware timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        raise ValueError(label + " must include a valid timezone") from None


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ValueError(label + " must be nonempty text of at most 500 characters")
    return value.strip()


def _num(value, label, low=0, high=1e8):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be finite and between {low} and {high}")
    return float(value)


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def validate_commitment(raw, *, voyage_id, port_code, at):
    """Validate identity/binding and present values, preserving missing inputs.

    This path only supports explicitly created fictional cargo. Its identity is
    stored inside the visitor-owned comparison, never mapped to a public berth.
    Root request ownership still belongs to the existing demo/decision service.
    """
    if not isinstance(raw, dict) or type(raw.get("schemaVersion")) is not int or raw["schemaVersion"] != 1:
        raise ValueError("Cargo commitment requires schemaVersion 1")
    try:
        json.dumps(raw, allow_nan=False)
    except (ValueError, TypeError):
        raise ValueError("Cargo commitment must contain finite JSON values") from None
    out = deepcopy(raw)
    for derived in ("inputVersion", "version", "conversionReferenceAt", "simulationHourAtReference"):
        out.pop(derived, None)
    if out.get("fictionalShipment") is not True:
        raise ValueError("Explicitly create a fictional shipment; public berth records do not identify this cargo")
    if out.get("voyageId") != voyage_id or out.get("portCode") != port_code:
        raise ValueError("Cargo commitment must bind to this owned voyage and destination port")
    out["basis"] = _text(out.get("basis"), "Cargo declaration basis")
    declared = _time(out.get("declaredAt"), "Cargo declaration time")
    if declared > at:
        raise ValueError("Cargo declaration cannot be in the future")
    if type(out.get("mustMeet", False)) is not bool:
        raise ValueError("mustMeet must be an explicit boolean")
    out["mustMeet"] = out.get("mustMeet", False)
    out["declaredAt"] = declared.isoformat()
    shipment = out.get("shipment")
    if not isinstance(shipment, dict):
        raise ValueError("Declare one fictional shipment")
    shipment["shipmentId"] = _text(shipment.get("shipmentId"), "Fictional shipment ID")
    for key, low in (("teu", .01), ("weightT", 0)):
        if shipment.get(key) is not None:
            shipment[key] = _num(shipment[key], "Shipment " + key, low)
    if shipment.get("cargoClass") is not None and shipment["cargoClass"] not in CARGO_CLASSES:
        raise ValueError("Unknown cargo class")
    if shipment.get("cargoClass") == "reefer" and shipment.get("teu") is not None and not shipment["teu"].is_integer():
        raise ValueError("Declare whole-TEU reefer units for the existing plug-count model")
    if shipment.get("destinationPort") is not None:
        shipment["destinationPort"] = _text(shipment["destinationPort"], "Cargo destination").upper()
    for key in ("latestDepartureAt",):
        if shipment.get(key) is not None:
            shipment[key] = _time(shipment[key], key).isoformat()
    shipment.setdefault("basis", out["basis"])
    shipment["basis"] = _text(shipment["basis"], "Shipment basis")
    if not isinstance(out.get("transfer", {}), dict):
        raise ValueError("transfer must be an object")
    transfer = out.setdefault("transfer", {})
    if transfer.get("approachToStartHours") is not None:
        transfer["approachToStartHours"] = _num(transfer["approachToStartHours"], "Approach-to-start hours", 0, 720)
    if transfer.get("gangs") is not None:
        if type(transfer["gangs"]) is not int or not 1 <= transfer["gangs"] <= 20:
            raise ValueError("Handling gangs must be an integer between 1 and 20")
    if transfer.get("mode") is not None and transfer["mode"] not in ("DIRECT", "YARD"):
        raise ValueError("Transfer mode must be DIRECT or YARD")
    if transfer.get("basis") is not None:
        transfer["basis"] = _text(transfer["basis"], "Transfer basis")
    if transfer.get("acceptedSchematicHandling") is not None and type(transfer["acceptedSchematicHandling"]) is not bool:
        raise ValueError("Schematic handling acceptance must be boolean")
    zone = transfer.get("zone")
    if zone is not None:
        if not isinstance(zone, dict):
            raise ValueError("Yard zone must be an object")
        for key in ("zoneId", "name"):
            if zone.get(key) is not None:
                zone[key] = _text(zone[key], "Zone " + key)
        for key in ("freeTeu", "capacityTeu", "reeferPlugsFree", "quayTransferMinutesPerTeu"):
            if zone.get(key) is not None:
                zone[key] = _num(zone[key], "Zone " + key)
        if zone.get("reeferPlugsFree") is not None and not zone["reeferPlugsFree"].is_integer():
            raise ValueError("Free yard reefer plugs must be a whole count")
        for key in ("acceptsHazardous", "acceptsOog"):
            if zone.get(key) is not None and type(zone[key]) is not bool:
                raise ValueError("Zone " + key + " must be boolean")
    for key in ("bookedConnection",):
        if not isinstance(out.get(key, {}), dict):
            raise ValueError(key + " must be an object")
    out.setdefault("bookedConnection", {})
    if not isinstance(out.get("laterConnections", []), list) or len(out.get("laterConnections", [])) > 3:
        raise ValueError("Declare at most three later connections")
    out.setdefault("laterConnections", [])
    seen = set()
    for connection in [out["bookedConnection"], *out["laterConnections"]]:
        if not isinstance(connection, dict):
            raise ValueError("Each connection must be an object")
        for key in ("vesselId", "name", "basis"):
            if connection.get(key) is not None:
                connection[key] = _text(connection[key], "Connection " + key)
        if connection.get("vesselId"):
            if connection["vesselId"] in seen:
                raise ValueError("Connections must have distinct declared vessel IDs")
            seen.add(connection["vesselId"])
        for key in ("departureAt", "loadingCutoffAt"):
            if connection.get(key) is not None:
                connection[key] = _time(connection[key], "Connection " + key).isoformat()
        if connection.get("departureAt") and connection.get("loadingCutoffAt") and _time(connection["loadingCutoffAt"], "Cutoff") > _time(connection["departureAt"], "Departure"):
            raise ValueError("Loading cutoff cannot be later than sailing")
        for key in ("availableTeu", "availableDeadweightT", "availableReeferPlugs"):
            if connection.get(key) is not None:
                connection[key] = _num(connection[key], "Connection " + key)
        if connection.get("availableReeferPlugs") is not None and not connection["availableReeferPlugs"].is_integer():
            raise ValueError("Available reefer plugs must be a whole count")
        for key in ("acceptsHazardous", "acceptsOog"):
            if connection.get(key) is not None and type(connection[key]) is not bool:
                raise ValueError("Connection " + key + " must be boolean")
        if connection.get("onwardPorts") is not None:
            if not isinstance(connection["onwardPorts"], list) or len(connection["onwardPorts"]) > 30:
                raise ValueError("Declare a bounded onward rotation")
            connection["onwardPorts"] = [_text(p, "Onward port").upper() for p in connection["onwardPorts"]]
    out["conversionReferenceAt"] = at.astimezone(timezone.utc).isoformat()
    out["simulationHourAtReference"] = 0.
    out["version"] = VERSION
    out["inputVersion"] = "cargo-inputs-" + _hash(out)
    return out


def _hour(value, reference):
    return (_time(value, "Cargo time") - reference).total_seconds() / 3600


def _stamp(hour, reference):
    return (reference + timedelta(hours=hour)).isoformat() if hour is not None else None


def _required(raw, keys, prefix, missing):
    for key in keys:
        if raw.get(key) is None or raw.get(key) == "":
            missing.append(prefix + "." + key)


def _objects(commitment, connection, start_hour):
    """Known rule inputs and separately reported missingness.

    Neutral placeholders only let existing rule functions check the *known*
    dimensions. They never appear as retained capacity or verified inputs.
    Missingness below prevents a compatible/required-pass claim.
    """
    raw = commitment["shipment"]
    transfer = commitment["transfer"]
    reference = _time(commitment["conversionReferenceAt"], "Reference")
    missing = []
    _required(raw, ("teu", "cargoClass", "destinationPort", "weightT"), "shipment", missing)
    _required(connection, ("vesselId", "name", "basis", "availableTeu", "availableDeadweightT", "onwardPorts", "departureAt", "loadingCutoffAt"), "connection", missing)
    if connection.get("onwardPorts") == []:
        # An explicitly empty rotation is a known incompatibility, not unknown.
        pass
    class_key = raw.get("cargoClass") or "dry"
    teu = raw.get("teu") or 0.
    shipment = Shipment(raw["shipmentId"], teu, class_key, raw.get("destinationPort") or "UNKNOWN",
        inbound_vessel_id=commitment["voyageId"], booked_vessel_id=connection.get("vesselId"),
        available_hour=start_hour, weight_t=raw.get("weightT") or 0.,
        latest_departure_hour=_hour(raw["latestDepartureAt"], reference) if raw.get("latestDepartureAt") else None)
    relevant = {"reefer": "availableReeferPlugs", "hazardous": "acceptsHazardous", "oog": "acceptsOog"}.get(class_key)
    if relevant:
        _required(connection, (relevant,), "connection", missing)
    cutoff = _hour(connection["loadingCutoffAt"], reference) if connection.get("loadingCutoffAt") else None
    departure = _hour(connection["departureAt"], reference) if connection.get("departureAt") else None
    # No cutoff -> no departure passed to legacy cutoff(), eliminating -2 h fallback.
    vessel = VesselCapacity(connection.get("vesselId") or "UNKNOWN", connection.get("name") or "Undeclared connection",
        connection.get("availableTeu") if connection.get("availableTeu") is not None else teu,
        available_reefer_plugs=connection.get("availableReeferPlugs") if connection.get("availableReeferPlugs") is not None else math.ceil(teu),
        accepts_hazardous=connection["acceptsHazardous"] if connection.get("acceptsHazardous") is not None else True,
        accepts_oog=connection["acceptsOog"] if connection.get("acceptsOog") is not None else True,
        available_deadweight_t=connection.get("availableDeadweightT"),
        onward_ports=connection.get("onwardPorts") if connection.get("onwardPorts") is not None else [shipment.destination_port],
        departure_hour=departure if cutoff is not None else None, load_cutoff_hour=cutoff)
    zone = None
    if transfer.get("mode") == "YARD":
        z = transfer.get("zone") or {}
        _required(z, ("zoneId", "name", "freeTeu", "capacityTeu", "quayTransferMinutesPerTeu"), "transfer.zone", missing)
        zone_relevant = {"reefer": "reeferPlugsFree", "hazardous": "acceptsHazardous", "oog": "acceptsOog"}.get(class_key)
        if zone_relevant:
            _required(z, (zone_relevant,), "transfer.zone", missing)
        if z.get("quayTransferMinutesPerTeu") is not None:
            zone = StorageZone(z.get("zoneId") or "UNKNOWN", z.get("name") or "Undeclared yard",
                z.get("freeTeu") if z.get("freeTeu") is not None else teu,
                z.get("capacityTeu") if z.get("capacityTeu") is not None else max(1., teu),
                reefer_plugs_free=z.get("reeferPlugsFree") if z.get("reeferPlugsFree") is not None else math.ceil(teu),
                accepts_hazardous=z["acceptsHazardous"] if z.get("acceptsHazardous") is not None else True,
                accepts_oog=z["acceptsOog"] if z.get("acceptsOog") is not None else True,
                quay_transfer_minutes_per_teu=z["quayTransferMinutesPerTeu"])
            shipment.yard_block_id = zone.zone_id
    return shipment, vessel, zone, missing, departure


def _assess(commitment, connection, clear_approach_at):
    reference = _time(commitment["conversionReferenceAt"], "Reference")
    transfer = commitment["transfer"]
    missing = []
    _required(transfer, ("approachToStartHours", "basis", "gangs", "mode"), "transfer", missing)
    if transfer.get("acceptedSchematicHandling") is not True:
        missing.append("transfer.acceptedSchematicHandling")
    if not clear_approach_at:
        missing.append("passage.clearApproachAt")
    start = (_hour(clear_approach_at, reference) + transfer["approachToStartHours"]
             if clear_approach_at and transfer.get("approachToStartHours") is not None else None)
    shipment, vessel, zone, object_missing, departure = _objects(commitment, connection, start)
    missing.extend(object_missing)
    # Missing stages cannot silently act like direct transfer or one gang.
    timing_fields = {"transfer.approachToStartHours", "transfer.basis", "transfer.gangs", "transfer.mode",
                     "transfer.acceptedSchematicHandling", "transfer.zone.quayTransferMinutesPerTeu"}
    timing_inputs = [k for k in missing if k in timing_fields or k in (
        "passage.clearApproachAt", "shipment.teu", "shipment.cargoClass", "connection.loadingCutoffAt")]
    if transfer.get("mode") == "YARD" and zone is None:
        timing_inputs.append("transfer.zone")
    reasons = check_compatibility(shipment, vessel)
    if zone is not None:
        reasons.extend(check_zone(shipment, zone))
    # Avoid explaining a synthetic class/destination placeholder as a known failure.
    if commitment["shipment"].get("destinationPort") is None:
        reasons = [r for r in reasons if "does not call at" not in r]
    ready = handling = slack = None
    stages = None
    if not timing_inputs:
        connection_result = evaluate_connection(shipment, vessel, zone=zone, inbound_discharge_hour=start,
            gangs=transfer["gangs"])
        handling = connection_result.window.handling_hours
        ready = connection_result.window.ready_hour
        slack = connection_result.window.slack_hours
        reasons = connection_result.reasons
        stages = {"dischargeHours": discharge_hours(shipment, transfer["gangs"]),
            "transferOverheadHours": TRANSFER_OVERHEAD_HOURS,
            "yardMovesHours": 0. if zone is None else 2 * yard_move_hours(shipment, zone),
            "loadHours": load_hours(shipment, transfer["gangs"]), "totalHandlingHours": handling}
    elif shipment.latest_departure_hour is not None and departure is not None and departure > shipment.latest_departure_hour:
        reasons.append("Declared onward sailing is later than the shipment's latest-departure commitment")
    if commitment["shipment"].get("destinationPort") is None:
        reasons = [r for r in reasons if "does not call at" not in r]
    status = "BLOCKED" if reasons else ("UNKNOWN" if missing else "COMPATIBLE_UNDER_ASSUMPTIONS")
    return {"status": status, "timingStatus": "UNKNOWN" if slack is None else ("FITS" if slack >= 0 else "MISSES"),
        "startAt": _stamp(start, reference), "readinessAt": _stamp(ready, reference),
        "cutoffAt": connection.get("loadingCutoffAt"), "departureAt": connection.get("departureAt"),
        "startHour": start, "readyHour": ready, "cutoffHour": vessel.load_cutoff_hour,
        "departureHour": departure, "slackHours": slack, "handlingHours": handling,
        "stages": stages, "reasons": reasons, "missing": sorted(set(missing)),
        "vesselId": connection.get("vesselId"), "vesselName": connection.get("name"),
        "basis": connection.get("basis"), "connection": deepcopy(connection)}


def _alternatives(commitment, base, clear_approach_at, option_id, source_passage_id):
    """Ask the existing cargo decision engine only about fully declared sailings.

    No decision is persisted/approved/executed. Empty financial basis prevents a
    generic scenario penalty being reinterpreted as a contractual charge.
    """
    if base["status"] != "BLOCKED" or base["startHour"] is None or commitment["transfer"].get("gangs") != 1:
        return []
    eligible = []
    booked_departure = base.get("departureAt")
    for item in commitment["laterConnections"]:
        assessed = _assess(commitment, item, clear_approach_at)
        if assessed["status"] == "COMPATIBLE_UNDER_ASSUMPTIONS" and booked_departure and item.get("departureAt") and _time(item["departureAt"], "Departure") > _time(booked_departure, "Booked departure"):
            eligible.append((item, assessed))
    if not eligible or base["missing"]:
        return []
    from .cargo import build_cargo_problem
    from .model import DecisionActor
    from src.portwatch_os.finance.basis import CostBasis
    reference = _time(commitment["conversionReferenceAt"], "Reference")
    shipment, booked, zone, _, _ = _objects(commitment, commitment["bookedConnection"], base["startHour"])
    vessels = [booked] + [_objects(commitment, item, base["startHour"])[1] for item, _ in eligible]
    problem = build_cargo_problem(shipment, vessels, [zone] if zone else [],
        decision_id="cargo-inspection-" + _hash({"input": commitment["inputVersion"], "option": option_id})[:20],
        actor=DecisionActor("SHIPPING_COMPANY"), at=reference, port_code=commitment["portCode"],
        world_state_id=source_passage_id or option_id, world_revision={"sourcePassageOptionId": option_id},
        basis=CostBasis(), now_hour=base["startHour"])
    by_vessel = {item["vesselId"]: assessed for item, assessed in eligible}
    rows = []
    for option in problem.options:
        vid = option.params.get("vesselId")
        if option.is_baseline or vid not in by_vessel or not option.feasible:
            continue
        assessed = by_vessel[vid]
        rows.append({"optionId": option.option_id, "action": option.action, "label": option.label,
            "status": "PROPOSAL_UNDER_ASSUMPTIONS", "sourcePassageOptionId": option_id,
            "sourcePassageId": source_passage_id, "cargoInputVersion": commitment["inputVersion"],
            "cargoInspectionId": problem.decision_id, "vesselId": vid,
            "departureAt": assessed["departureAt"], "readinessAt": assessed["readinessAt"],
            "cutoffAt": assessed["cutoffAt"], "slackHours": assessed["slackHours"],
            "departureShiftHours": (_time(assessed["departureAt"], "Departure") - _time(booked_departure, "Booked departure")).total_seconds()/3600,
            "constraintChecks": [c.to_dict() for c in option.constraints],
            "bookingStatus": "NOT_RESERVED", "execution": "SEPARATE_COMPANY_REVIEW_REQUIRED",
            "money": {"available": False, "reason": "No applicable declared cargo storage or missed-connection rate; partial passage money is separate"},
            "limitation": "Declared next sailing only; no booking, terminal guarantee or final-delivery ETA"})
    return rows


def evaluate_commitment(commitment, *, clear_approach_at, option_id, source_passage_id=None):
    """Pure per-option assessment; comparison selection/authority stay upstream."""
    result = _assess(commitment, commitment["bookedConnection"], clear_approach_at)
    required = commitment["mustMeet"]
    result.update({"version": VERSION, "ruleVersion": MODEL_VERSION,
        "optionId": option_id, "sourcePassageOptionId": option_id, "sourcePassageId": source_passage_id,
        "inputVersion": commitment["inputVersion"], "shipmentId": commitment["shipment"]["shipmentId"],
        "destinationPort": commitment["shipment"].get("destinationPort"),
        "conversionReferenceAt": commitment["conversionReferenceAt"], "simulationHourAtReference": 0.,
        "clearApproachAt": clear_approach_at,
        "requiredConstraint": {"required": required, "passed": True if result["status"] == "COMPATIBLE_UNDER_ASSUMPTIONS" else (False if result["status"] == "BLOCKED" else None),
            "meaning": "Only an explicitly declared must-meet connection affects passage approval eligibility"},
        "handlingBasis": {"model": MODEL_VERSION, "dischargeTeuPerHourPerGang": DISCHARGE_TEU_PER_HOUR,
            "loadTeuPerHourPerGang": LOAD_TEU_PER_HOUR, "transferOverheadHours": TRANSFER_OVERHEAD_HOURS,
            "startMeaning": "Clear approach plus declared pre-handling interval; complete cargo handling is then counted once",
            "source": "Explicitly accepted schematic demonstration constants, not terminal performance evidence"},
        "financial": {"available": False, "reason": "No applicable declared cargo charges; no storage charged during sailing or anchorage"},
        "finalDeliveryEta": {"available": False, "reason": "No supported onward transit schedule declared"},
        "limitations": ["Conditional clear approach is not berth access, all-fast, discharge completion or customs release",
            "Capacity, handling and schedule are declared fictional assumptions, not confirmed booking feasibility",
            "Navigation advisory acceptance cannot book, reserve capacity or execute a cargo alternative"]})
    result["alternatives"] = _alternatives(commitment, result, clear_approach_at, option_id, source_passage_id)
    if result["status"] == "BLOCKED" and not result["alternatives"]:
        result["alternativesUnavailableBecause"] = (
            "The existing cargo decision engine proposes single-gang transfers only; this declaration uses another gang count."
            if commitment["transfer"].get("gangs") != 1 else
            "No fully declared compatible later sailing is evaluable under the retained commitment; no booking is invented.")
    result["assessmentId"] = "cargo-assessment-" + _hash(result)
    return result


__all__ = ["VERSION", "MODEL_VERSION", "validate_commitment", "evaluate_commitment"]
