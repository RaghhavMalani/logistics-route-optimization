"""One arrival's immutable evidence → decision → advisory → action → outcome chain."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from src.portwatch_os.clock import wall_now, world_now
from src.portwatch_os.intelligence import arrival_model
from src.portwatch_os.intelligence.arrival_collection import PROTOCOL, quality
from src.portwatch_os.learning.weather_feedback import instant, VARIABLES, consumed_value, CONSUMPTION_MODE, ADOPTION_STATUS
from src.portwatch_os.ledger.schema import CONTINUOUS, DOMAIN_PORT_OPS, DOMAIN_WEATHER, DecisionRecord, PredictionContext, PredictionRecord, _stable_id
from src.portwatch_os.ledger.store import LedgerError, SqliteLedgerStore
from src.utils import port_registry

FIRST_PORT = "INNSA"


def stamp(value: datetime | str) -> str:
    return instant(value).astimezone(timezone.utc).isoformat(timespec="microseconds")


def archive_track(ledger: SqliteLedgerStore, observation, *, recorded_at: datetime | None = None) -> bool:
    """Archive accepted AIS claims near JNPA; proximity is not a berth/identity match."""
    if observation.message_type not in ("PositionReport", "StandardClassBPositionReport"):
        return False
    if observation.provenance.get("source_time_known") is False:
        return False
    p = port_registry.resolve(FIRST_PORT)
    lat1, lat2 = math.radians(p.lat), math.radians(observation.lat)
    delta = math.radians(observation.lon-p.lon)
    distance = 3440.065*2*math.asin(min(1, math.sqrt(math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(delta/2)**2)))
    if distance > 30:
        return False
    # wall-clock: AIS recording availability is the actual ingest/import receipt, never replay time.
    now = recorded_at or wall_now()
    row = {"id": _stable_id("ais-arrival", observation.provider_id, observation.mmsi,
                            stamp(observation.source_timestamp), observation.lat, observation.lon),
           "portCode": FIRST_PORT, "mmsi": observation.mmsi, "observedAt": stamp(observation.source_timestamp),
           "availableAt": stamp(observation.ingested_at), "recordedAt": stamp(now),
           "source": observation.provider_id, "rawRef": observation.raw_ref,
           "lat": observation.lat, "lon": observation.lon, "sogKnots": observation.sog_knots,
           "navStatus": observation.nav_status, "match": "Within 30 nautical miles of JNPA; operator identifies the arrival"}
    ledger.record_arrival_track(row)
    return True


class ArrivalWorkflow:
    def __init__(self, ledger: SqliteLedgerStore):
        self.ledger = ledger

    def cases(self, *, now: datetime | None = None) -> list[dict]:
        at = stamp(now or world_now())
        grouped = {}
        for event in self.ledger.arrival_events(FIRST_PORT, before=at):
            grouped.setdefault(event["operationId"], []).append(event)
        result = []
        for operation_id, events in grouped.items():
            initial = next((e["body"] for e in events if e["kind"] == "created"), None)
            if not initial:
                continue
            steps = {e["kind"]: e["body"] for e in events}
            outcome = steps.get("outcome")
            prediction = initial["prediction"]
            result.append({**initial, "operationId": operation_id, "events": events,
                           "approved": "approved" in steps, "advisoryId": steps.get("advisory", {}).get("advisoryId"),
                           "actualAction": steps.get("action"), "outcome": outcome,
                           "disposition": steps.get("disposition"),
                           "errorHours": None if not outcome or prediction["value"] is None else outcome["waitHours"]-prediction["value"],
                           "withinInterval": None if not outcome or prediction["low"] is None else prediction["low"] <= outcome["waitHours"] <= prediction["high"]})
        return sorted(result, key=lambda r: r["issuedAt"], reverse=True)

    def get(self, operation_id: str, *, now: datetime | None = None) -> dict:
        for row in self.cases(now=now):
            if row["operationId"] == operation_id:
                return row
        raise ValueError("Arrival operation is unavailable at this clock")

    def training_rows(self, *, now: datetime | None = None) -> list[dict]:
        rows = []
        seen = set()
        for case in reversed(self.cases(now=now)):
            o, f = case["outcome"], case["features"]
            if case.get("disposition") or not o or f.get("wind_speed") is None or f["trackCount"] < 2 or f["trackAgeHours"] > 1:
                continue
            call_key = (case["mmsi"], o["arrivedAt"])
            if call_key in seen:
                continue
            seen.add(call_key)
            rows.append({"operationId": case["operationId"], "issuedAt": case["issuedAt"], "features": f,
                         "waitHours": o["waitHours"], "availableAt": o["availableAt"],
                         "recordedAt": next(e["recordedAt"] for e in case["events"] if e["kind"] == "outcome")})
        return sorted(rows, key=lambda r: (r["issuedAt"], r["operationId"]))

    def benchmarks(self, *, now: datetime | None = None) -> list[dict]:
        return [e["body"] for e in self.ledger.arrival_events(FIRST_PORT, before=stamp(now or world_now())) if e["kind"] == "benchmark"]

    def cohorts(self, *, now: datetime | None = None) -> list[dict]:
        reports = self.benchmarks(now=now)
        sealed = {r.get("cohortId") for r in reports}
        return [{**e["body"], "status": "SEALED" if e["body"]["cohortId"] in sealed else "COLLECTING"}
                for e in self.ledger.arrival_events(FIRST_PORT, before=stamp(now or world_now())) if e["kind"] == "cohort"]

    def start_collection(self, actor: str, *, now: datetime | None = None) -> dict:
        now = instant(now or world_now())
        with self.ledger.atomic():
            cohorts = self.cohorts(now=now)
            if cohorts and cohorts[-1]["status"] == "COLLECTING":
                return cohorts[-1]
            at = stamp(now)
            key = _stable_id("arrival-cohort", FIRST_PORT, at)
            body = {"cohortId": key, "startedAt": at, "protocol": PROTOCOL,
                    "protocolHash": arrival_model.digest(PROTOCOL), "modelCodeHash": arrival_model.hash_code(),
                    "dependencies": arrival_model.dependencies(), "startedBy": actor}
            self.ledger.append_arrival_event(key, "cohort", FIRST_PORT, actor, body, at=at)
        return {**body, "status": "COLLECTING"}

    def collection(self, *, now: datetime | None = None) -> dict:
        now = instant(now or world_now())
        cohorts = self.cohorts(now=now)
        cohort = cohorts[-1] if cohorts else None
        cases = [c for c in self.cases(now=now) if cohort and c.get("cohortId") == cohort["cohortId"]]
        report = quality(cases, now)
        ids = {r["operationId"] for r in report["calls"] if r["qualifying"]}
        rows = [r for r in self.training_rows(now=now) if r["operationId"] in ids]
        report["qualifyingCount"] = len(rows)
        report["cohort"] = cohort
        report["minimumQualifyingCalls"] = 60
        try:
            train, cal, holdout = arrival_model.partition(rows)
            used = {k for c in self.cases(now=now) for k in c["prediction"].get("fitIds", [])+c["prediction"].get("calibrationIds", [])}
            if used.intersection(r["operationId"] for r in holdout):
                raise ValueError("Proposed holdout was already used; collect an untouched later cohort")
            if report["unresolvedCount"] or report["duplicateCandidateCount"]:
                raise ValueError("Resolve all enrolled calls and duplicate candidates before sealing")
            if cohort["modelCodeHash"] != arrival_model.hash_code() or cohort["dependencies"] != arrival_model.dependencies():
                raise ValueError("Model implementation changed after collection began; start a new protocol before evaluation")
            report["evaluationReady"] = cohort["status"] == "COLLECTING"
            report["gateReason"] = "Thresholds enable evaluation; accuracy remains unestablished"
            report["partitions"] = {"fit": len(train), "calibration": len(cal), "holdout": len(holdout),
                                    "purged": len(rows)-len(train)-len(cal)-len(holdout)}
        except ValueError as exc:
            report.update(evaluationReady=False, gateReason=str(exc), partitions=None)
        tracks = self.ledger.arrival_tracks(FIRST_PORT, before=stamp(now), limit=1)
        report["latestAisObservedAt"] = tracks[-1]["observedAt"] if tracks else None
        report["aisArchiveStatus"] = "FRESH" if tracks and now-instant(tracks[-1]["observedAt"]) <= timedelta(hours=1) else "STALE" if tracks else "UNAVAILABLE"
        return report

    def disposition(self, operation_id: str, actor: str, payload: dict, *, now: datetime | None = None) -> dict:
        now = instant(now or world_now())
        with self.ledger.atomic():
            case = self.get(operation_id, now=now)
            if case["outcome"]:
                raise ValueError("Confirmed outcomes cannot be excluded after observing prediction error")
            if case.get("cohortId") and any(r.get("cohortId") == case["cohortId"] for r in self.benchmarks(now=now)):
                raise ValueError("The cohort is sealed")
            if not instant(case["issuedAt"]) <= instant(payload["availableAt"]) <= now:
                raise ValueError("Disposition evidence must be available after enrollment and by now")
            if payload["reason"] == "duplicate":
                other = self.get(payload.get("duplicateOf") or "", now=now)
                if other["operationId"] == operation_id or other["mmsi"] != case["mmsi"] or other.get("disposition"):
                    raise ValueError("Duplicate reference must identify another active call for the same MMSI")
            self.ledger.append_arrival_event(operation_id, "disposition", FIRST_PORT, actor, payload, at=stamp(now))
        return self.get(operation_id, now=now)

    def evaluate(self, actor: str, *, now: datetime | None = None) -> dict:
        with self.ledger.atomic():
            return self._evaluate(actor, now=now)

    def _evaluate(self, actor: str, *, now: datetime | None = None) -> dict:
        at = stamp(now or world_now())
        rows = self.training_rows(now=now)
        used = {k for c in self.cases(now=now) for k in c["prediction"].get("fitIds", []) + c["prediction"].get("calibrationIds", [])}
        # Once sealed, holdout labels never become fit/calibration inputs later.
        reports = self.benchmarks(now=now)
        collection = self.collection(now=now)
        cohort = collection["cohort"]
        if cohort:
            existing = next((r for r in reports if r.get("cohortId") == cohort["cohortId"]), None)
            if existing:
                return existing
            if not collection["evaluationReady"]:
                raise ValueError(collection["gateReason"])
            ids = {r["operationId"] for r in collection["calls"] if r["qualifying"]}
            rows = [r for r in rows if r["operationId"] in ids]
        if reports and reports[-1]["datasetHash"] == arrival_model.digest(rows):
            return reports[-1]
        reserved = {k for r in reports for k in r["holdoutIds"]}
        report = arrival_model.evaluate([r for r in rows if r["operationId"] not in reserved], used)
        report.update({"recordedAt": at, "portCode": FIRST_PORT, "baseline": "Frozen operation-specific incumbent schedule estimate",
                       "limitations": "Operator-confirmed port-call times; AIS proximity is not proof of berth occupancy. No counterfactual savings."})
        if cohort:
            report.update(cohortId=cohort["cohortId"], protocol=cohort["protocol"], protocolHash=cohort["protocolHash"],
                          collectionQuality=collection, enrolledIds=[c["operationId"] for c in self.cases(now=now) if c.get("cohortId") == cohort["cohortId"]])
        evaluation_id = _stable_id("arrival-benchmark", report["datasetHash"])
        existing = next((r for r in reports if r["datasetHash"] == report["datasetHash"]), None)
        if existing:
            return existing
        self.ledger.append_arrival_event(evaluation_id, "benchmark", FIRST_PORT, actor, report, at=at)
        return report

    def signals(self, mmsi: str, planned_arrival: datetime, *, now: datetime) -> tuple[dict, dict]:
        at = stamp(now)
        tracks = self.ledger.arrival_tracks(FIRST_PORT, mmsi=mmsi, before=at, after=stamp(now-timedelta(hours=24)))
        weather = {}
        for row in self.ledger.predictions(domain=DOMAIN_WEATHER, subject=FIRST_PORT):
            if row.target not in VARIABLES or instant(row.issued_at) > now:
                continue
            if row.context.extra.get("targetDate") != planned_arrival.date().isoformat():
                continue
            if row.context.extra.get("unit") != VARIABLES[row.target]:
                continue
            audit = self.ledger.audit_trail("prediction", row.prediction_id)
            recorded = next((e["at"] for e in audit if e["action"] == "created"), None)
            # Legacy creation audits use whole seconds. Wait until the end of
            # that second so replay never claims subsecond knowledge too early.
            available = instant(recorded)+timedelta(seconds=1) if recorded else None
            if not available or available > now:
                continue
            if row.target in weather and instant(weather[row.target]["issuedAt"]) >= instant(row.issued_at):
                continue
            weather[row.target] = {"id": row.prediction_id, "variable": row.target, "original": row.predicted_value,
                "consumed": consumed_value(row.predicted_value, row.context.extra.get("correction")), "unit": VARIABLES[row.target],
                "correctionConsumed": False, "consumptionMode": CONSUMPTION_MODE, "adoptionStatus": ADOPTION_STATUS,
                "issuedAt": row.issued_at, "validAt": row.valid_at, "recordedAt": recorded,
                "availableAt": stamp(max(instant(row.issued_at), available)),
                "source": row.provenance.get("provider", row.model), "statistic": "daily aggregate covering planned arrival"}
        nearby = self.ledger.arrival_tracks(FIRST_PORT, before=at, after=stamp(now-timedelta(minutes=10)), limit=10000)
        latest = {r["mmsi"]: r for r in nearby}
        last = tracks[-1] if tracks else None
        features = {k: weather.get(k, {}).get("consumed") for k in VARIABLES}
        features.update({"sogKnots": last["sogKnots"] if last else None, "trackCount": len(tracks),
                         "trackAgeHours": (now-instant(last["observedAt"])).total_seconds()/3600 if last else None,
                         "observedAnchoredVessels": sum(r["navStatus"] == "at anchor" for r in latest.values())})
        return {"weather": list(weather.values()), "tracks": tracks,
                "matchRationale": "Operator-supplied MMSI and arrival reference; AIS proximity alone does not distinguish nearby Mumbai",
                "camera": {"status": "UNAVAILABLE", "reason": "No authorized camera is attached to this operation"}}, features

    def create(self, payload: dict, actor: str, *, now: datetime | None = None) -> dict:
        with self.ledger.atomic():
            return self._create(payload, actor, now=now)

    def _create(self, payload: dict, actor: str, *, now: datetime | None = None) -> dict:
        now = instant(now or world_now())
        planned = instant(payload["plannedArrivalAt"])
        if not now < planned <= now+timedelta(days=7):
            raise ValueError("Planned arrival must be in the next seven days; retrospective claims are refused")
        operation_id = _stable_id("arrival", FIRST_PORT, payload["operationRef"])
        cohorts = self.cohorts(now=now)
        cohort = cohorts[-1] if cohorts and cohorts[-1]["status"] == "COLLECTING" else None
        if cohort:
            if not all(payload.get(k) for k in ("baselineRef", "baselineEstimatedAt", "baselineAvailableAt")):
                raise ValueError("Prospective enrollment requires scheduler source, reference, estimate time and availability time")
        if payload.get("baselineEstimatedAt") or payload.get("baselineAvailableAt"):
            if not all(payload.get(k) for k in ("baselineRef", "baselineEstimatedAt", "baselineAvailableAt")):
                raise ValueError("Supply all scheduler provenance fields together")
            estimate, available = instant(payload["baselineEstimatedAt"]), instant(payload["baselineAvailableAt"])
            if not estimate <= available <= now:
                raise ValueError("Scheduler estimate must already exist and be available before freezing")
            payload = {**payload, "baselineEstimatedAt": stamp(estimate), "baselineAvailableAt": stamp(available)}
        evidence, features = self.signals(payload["mmsi"], planned, now=now)
        features["baselineWaitHours"] = payload["baselineWaitHours"]
        reports = self.benchmarks(now=now)
        prediction = arrival_model.predict(features, self.training_rows(now=now), reports[-1] if reports else None)
        issued = stamp(now)
        decision_id = _stable_id("arrival-decision", operation_id)
        prediction_id = _stable_id("arrival-prediction", operation_id) if prediction["value"] is not None else None
        missing = list(prediction["missing"])
        for variable in VARIABLES:
            if features[variable] is None:
                missing.append(f"{variable} forecast unavailable; explicit missingness feature")
        if not payload.get("routeRevision"):
            missing.append("Route revision unavailable; this model covers the named arrival only")
        body = {**payload, "portCode": FIRST_PORT, "plannedArrivalAt": stamp(planned), "issuedAt": issued,
                "cohortId": cohort["cohortId"] if cohort else None,
                "evidence": evidence, "features": features, "prediction": prediction, "predictionId": prediction_id,
                "decisionId": decision_id, "missingEvidence": missing,
                "recommendation": "Review the planned arrival with the berth scheduler; no arrival shift or savings is established"}
        with self.ledger.atomic():
            self.ledger.append_arrival_event(operation_id, "created", FIRST_PORT, actor, body, at=issued)
            if prediction_id:
                self.ledger.record_prediction(PredictionRecord(prediction_id, DOMAIN_PORT_OPS, CONTINUOUS,
                    "anchorage_wait_hours", operation_id, prediction.get("model", "GBM"), prediction["modelVersion"], issued,
                    stamp(planned), PredictionContext(port_code=FIRST_PORT, extra={"operationId": operation_id}),
                    predicted_value=prediction["value"], predicted_low=prediction["low"], predicted_high=prediction["high"],
                    interval_nominal=prediction["intervalNominal"], features={k: v for k, v in features.items() if v is not None},
                    provenance={"evidenceHash": arrival_model.digest(evidence), "benchmarkHash": prediction["benchmarkHash"]}))
            self.ledger.record_decision(DecisionRecord(decision_id, "arrival_wait_review", operation_id, issued, actor,
                {"action": "REVIEW_ARRIVAL", "plannedArrivalAt": stamp(planned)}, body["recommendation"],
                prediction_ids=[prediction_id] if prediction_id else [], model_version=prediction["modelVersion"],
                approval_state="pending", expected_impact={"anchorage_wait_hours": prediction["value"]} if prediction_id else {}))
        return self.get(operation_id, now=now)

    def approve(self, operation_id: str, actor: str, note: str, *, now: datetime | None = None) -> dict:
        now = instant(now or world_now())
        with self.ledger.atomic():
            case = self.get(operation_id, now=now)
            if instant(case["plannedArrivalAt"]) <= now:
                raise ValueError("Arrival review window has closed; create a fresh operation before making a new claim")
            self.ledger.append_arrival_event(operation_id, "approved", FIRST_PORT, actor, {"note": note}, at=stamp(now))
            decision = self.ledger.get_decision(case["decisionId"])
            decision.approval_state, decision.approver = "approved", actor
            self.ledger.record_decision(decision)
        return self.get(operation_id, now=now)

    def action(self, operation_id: str, actor: str, payload: dict, *, now: datetime | None = None) -> dict:
        now = instant(now or world_now())
        with self.ledger.atomic():
            case = self.get(operation_id, now=now)
            occurred, available = instant(payload["occurredAt"]), instant(payload["availableAt"])
            if not case["approved"] or not case["advisoryId"]:
                raise ValueError("Approve the review and link an issued advisory before recording actual action")
            if not instant(case["issuedAt"]) <= occurred <= available <= now:
                raise ValueError("Action times must follow the frozen claim and be available now")
            self.ledger.append_arrival_event(operation_id, "action", FIRST_PORT, actor,
                {**payload, "occurredAt": stamp(occurred), "availableAt": stamp(available)}, at=stamp(now))
        return self.get(operation_id, now=now)

    def outcome(self, operation_id: str, actor: str, payload: dict, *, now: datetime | None = None) -> dict:
        now = instant(now or world_now())
        with self.ledger.atomic():
            case = self.get(operation_id, now=now)
            arrival, berth, available = (instant(payload[k]) for k in ("arrivedAt", "berthedAt", "availableAt"))
            if case.get("disposition"):
                raise ValueError("This call has an immutable exclusion disposition")
            if not instant(case["issuedAt"]) <= arrival <= berth <= available <= now:
                raise ValueError("Outcome must follow the claim: arrival ≤ all-fast ≤ available ≤ now")
            if case.get("cohortId") and instant(case["issuedAt"]) >= arrival:
                raise ValueError("Prospective evidence must be frozen strictly before actual arrival")
            if case["actualAction"] and instant(case["actualAction"]["occurredAt"]) > berth:
                raise ValueError("Actual action must precede the observed all-fast time")
            if case.get("cohortId") and not all(payload.get(k) for k in ("arrivalAvailableAt", "allFastAvailableAt", "sourceRef")):
                raise ValueError("Prospective outcomes require both event availability times and a source reference")
            for event, key in ((arrival, "arrivalAvailableAt"), (berth, "allFastAvailableAt")):
                if payload.get(key) and not event <= instant(payload[key]) <= available:
                    raise ValueError("Each event's availability must follow its occurrence and precede the combined availability")
                if payload.get(key):
                    payload = {**payload, key: stamp(payload[key])}
            for other in self.cases(now=now):
                o = other["outcome"]
                if other["operationId"] == operation_id or other["mmsi"] != case["mmsi"] or not o:
                    continue
                if instant(o["arrivedAt"]) == arrival or max(arrival, instant(o["arrivedAt"])) < min(berth, instant(o["berthedAt"])):
                    raise ValueError("This MMSI already has a measured arrival with overlapping waiting times; duplicate calls cannot become extra labels")
            wait = (berth-arrival).total_seconds()/3600
            body = {**payload, "arrivedAt": stamp(arrival), "berthedAt": stamp(berth), "availableAt": stamp(available),
                    "recordedAt": stamp(now), "waitHours": wait, "definition": "Confirmed anchorage arrival to confirmed all-fast"}
            self.ledger.append_arrival_event(operation_id, "outcome", FIRST_PORT, actor, body, at=stamp(now))
            point = case["prediction"]["value"]
            if case["predictionId"]:
                self.ledger.resolve_prediction(case["predictionId"], wait, stamp(available), payload["source"],
                    {"error": wait-point, "absolute_error": abs(wait-point),
                     "within_interval": case["prediction"]["low"] <= wait <= case["prediction"]["high"]})
            if case["actualAction"]:
                self.ledger.resolve_decision(case["decisionId"], case["actualAction"]["actionState"],
                    {"anchorage_wait_hours": wait}, stamp(available), impact_error=None if point is None else wait-point)
        return self.get(operation_id, now=now)
