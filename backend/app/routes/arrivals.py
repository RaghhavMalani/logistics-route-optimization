"""Verified JNPA arrival evidence and measured outcomes."""
from datetime import datetime
import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.identity import Identity, require_verified
from backend.app.routes.intelligence import may_write
from src.portwatch_os.advisories.model import Advisory, ISSUER
from src.portwatch_os.advisories.store import Principal, get_advisory_store
from src.portwatch_os.clock import world_now
from src.portwatch_os.intelligence.arrivals import ArrivalWorkflow, FIRST_PORT, stamp
from src.portwatch_os.intelligence.jnpa_public import latest_report
from src.portwatch_os.learning.weather_feedback import instant
from src.portwatch_os.ledger.schema import _stable_id
from src.portwatch_os.ledger.store import LedgerError, get_ledger
from src.portwatch_os.roles import NATIONAL_ADMIN, PORT_AUTHORITY
from src.utils import port_registry

router = APIRouter()


def scope(port_code: str = Query(FIRST_PORT, alias="portCode"), who: Identity = Depends(require_verified)) -> Identity:
    port = port_registry.resolve(port_code)
    if not port:
        raise HTTPException(404, "Port is not registered")
    if who.role != NATIONAL_ADMIN and not (who.role == PORT_AUTHORITY and port.locode in who.port_codes):
        raise HTTPException(403, "Arrival evidence is restricted to national command and the port's verified authority")
    if port.locode != FIRST_PORT:
        raise HTTPException(422, "Measured arrival workflow currently covers JNPA (INNSA)")
    return who


def workflow() -> ArrivalWorkflow:
    return ArrivalWorkflow(get_ledger())


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="after")
    @classmethod
    def aware(cls, value):
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Timestamps require a timezone")
        return value


class ArrivalInput(Input):
    operationRef: str = Field(min_length=1, max_length=150)
    mmsi: str = Field(pattern=r"^[1-9][0-9]{8}$")
    vesselName: str = Field(min_length=1, max_length=150)
    recipientOrganisation: str = Field(min_length=1, max_length=200)
    plannedArrivalAt: datetime
    baselineWaitHours: float = Field(ge=0, le=720, allow_inf_nan=False)
    baselineSource: str = Field(min_length=3, max_length=500)
    baselineRef: str | None = Field(None, min_length=1, max_length=200)
    baselineEstimatedAt: datetime | None = None
    baselineAvailableAt: datetime | None = None
    routeRevision: str | None = Field(None, max_length=200)


class ApprovalInput(Input):
    note: str = Field(min_length=3, max_length=1000)


class ActionInput(Input):
    actualAction: str = Field(min_length=3, max_length=1000)
    actionState: Literal["taken", "modified", "not_taken"]
    occurredAt: datetime
    availableAt: datetime
    source: str = Field(min_length=3, max_length=500)


class OutcomeInput(Input):
    arrivedAt: datetime
    berthedAt: datetime
    availableAt: datetime
    source: str = Field(min_length=3, max_length=500)
    kind: Literal["port_call_log", "operator_confirmed"]
    berthRef: str = Field(min_length=1, max_length=200)
    sourceRef: str | None = Field(None, min_length=1, max_length=200)
    arrivalAvailableAt: datetime | None = None
    allFastAvailableAt: datetime | None = None


class DispositionInput(Input):
    reason: Literal["cancelled", "duplicate"]
    source: str = Field(min_length=3, max_length=500)
    availableAt: datetime
    duplicateOf: str | None = Field(None, max_length=100)


class OutcomeImport(OutcomeInput):
    operationRef: str = Field(min_length=1, max_length=150)
    mmsi: str = Field(pattern=r"^[1-9][0-9]{8}$")


class ImportInput(Input):
    recordType: Literal["operations", "outcomes"]
    csvText: str = Field(min_length=1, max_length=250_000)
    commit: bool = False


def call(fn):
    try:
        return fn()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except LedgerError as exc:
        if "already recorded" in str(exc):
            raise HTTPException(409, str(exc)) from exc
        raise


def present(case: dict) -> dict:
    advisory = get_advisory_store().get(case["advisoryId"]) if case["advisoryId"] else None
    if advisory:
        # A replay sees only transitions known at that instant, not today's response.
        audit = [a.to_dict() for a in advisory.audit if instant(a.at) <= world_now()]
        case["advisory"] = {"id": advisory.advisory_id, "state": audit[-1]["to_state"] if audit else "UNAVAILABLE",
                            "audit": audit}
    else:
        case["advisory"] = None
    return case


@router.get("/arrivals/workspace")
def workspace(who: Identity = Depends(scope), service: ArrivalWorkflow = Depends(workflow)) -> dict:
    reports = service.benchmarks()
    cases = service.cases()
    reserved = {k for r in reports for k in r["holdoutIds"]}
    eligible = [r for r in service.training_rows() if r["operationId"] not in reserved]
    return {"portCode": FIRST_PORT, "asOf": stamp(world_now()), "operations": [present(c) for c in cases],
            "measuredCount": len(service.training_rows()), "evaluationEligibleCount": len(eligible), "benchmark": reports[-1] if reports else None,
            "reason": "Need 60 complete arrivals with issue-time weather, observed AIS and later confirmed outcomes for evaluation",
            "target": "Anchorage arrival to all-fast, hours", "cameraStatus": "UNAVAILABLE",
            "collection": service.collection(),
            "publicEvidence": latest_report(before=world_now())}


@router.get("/arrivals/dataset")
def dataset(who: Identity = Depends(scope), service: ArrivalWorkflow = Depends(workflow)) -> dict:
    collection = service.collection()
    key = collection["cohort"]["cohortId"] if collection["cohort"] else None
    return {"portCode": FIRST_PORT, "asOf": stamp(world_now()), "collection": collection,
            "operations": [present(c) for c in service.cases() if key and c.get("cohortId") == key],
            "benchmarks": [r for r in service.benchmarks() if key and r.get("cohortId") == key]}


@router.post("/arrivals/collection")
def start_collection(who: Identity = Depends(scope), service: ArrivalWorkflow = Depends(workflow)) -> dict:
    may_write(who, FIRST_PORT)
    return call(lambda: service.start_collection(who.actor))


@router.post("/arrivals/import")
def import_csv(payload: ImportInput, who: Identity = Depends(scope), service: ArrivalWorkflow = Depends(workflow)) -> dict:
    may_write(who, FIRST_PORT)
    def run():
        model = ArrivalInput if payload.recordType == "operations" else OutcomeImport
        reader = csv.DictReader(io.StringIO(payload.csvText.lstrip("\ufeff")), strict=True)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV requires unique named columns")
        if set(reader.fieldnames) - set(model.model_fields):
            raise ValueError("CSV contains unknown columns")
        records = []
        try:
            for index, row in enumerate(reader, 2):
                if len(records) >= 200:
                    raise ValueError("Import at most 200 records per batch")
                if None in row or any(v is None for v in row.values()):
                    raise ValueError(f"CSV row {index} has the wrong number of cells")
                records.append((index, model.model_validate({k: v for k, v in row.items() if v != ""})))
        except (ValueError, csv.Error) as exc:
            raise ValueError(f"Invalid CSV: {exc}") from exc
        if not records:
            raise ValueError("CSV has no data rows")
        class PreviewRollback(Exception):
            pass
        results = []
        try:
            with service.ledger.atomic():
                for index, record in records:
                    try:
                        body = record.model_dump(mode="json")
                        if payload.recordType == "operations":
                            result = service.create(body, who.actor)
                        else:
                            key = _stable_id("arrival", FIRST_PORT, body.pop("operationRef"))
                            case = service.get(key)
                            if body.pop("mmsi") != case["mmsi"]:
                                raise ValueError("MMSI differs from the enrolled call")
                            result = service.outcome(key, who.actor, body)
                        results.append({"row": index, "operationId": result["operationId"], "operationRef": result["operationRef"]})
                    except (ValueError, LedgerError) as exc:
                        raise ValueError(f"CSV row {index}: {exc}; entire batch rolled back") from exc
                if not payload.commit:
                    raise PreviewRollback()
        except PreviewRollback:
            pass
        return {"status": "IMPORTED" if payload.commit else "PREVIEW", "count": len(results), "rows": results,
                "note": "Commit revalidates and freezes evidence at server receipt time; preview writes nothing"}
    return call(run)


@router.post("/arrivals/operations/{operation_id}/disposition")
def disposition(operation_id: str, payload: DispositionInput, who: Identity = Depends(scope), service: ArrivalWorkflow = Depends(workflow)) -> dict:
    may_write(who, FIRST_PORT)
    return call(lambda: present(service.disposition(operation_id, who.actor, payload.model_dump(mode="json"))))


@router.post("/arrivals/operations")
def create(payload: ArrivalInput, who: Identity = Depends(scope), service: ArrivalWorkflow = Depends(workflow)) -> dict:
    may_write(who, FIRST_PORT)
    return call(lambda: present(service.create(payload.model_dump(mode="json"), who.actor)))


@router.post("/arrivals/operations/{operation_id}/approve")
def approve(operation_id: str, payload: ApprovalInput, who: Identity = Depends(scope), service: ArrivalWorkflow = Depends(workflow)) -> dict:
    may_write(who, FIRST_PORT)
    return call(lambda: present(service.approve(operation_id, who.actor, payload.note)))


@router.post("/arrivals/operations/{operation_id}/advisory")
def advisory(operation_id: str, who: Identity = Depends(scope), service: ArrivalWorkflow = Depends(workflow)) -> dict:
    may_write(who, FIRST_PORT)
    def build():
        with service.ledger.atomic():
            case = service.get(operation_id)
            if not case["approved"] or instant(case["plannedArrivalAt"]) <= world_now():
                raise ValueError("Approve the arrival review within its planning window first")
            if case["advisoryId"]:
                return present(case)
            at = stamp(world_now())
            advisory_id = _stable_id("arrival-advisory", operation_id)
            store = get_advisory_store()
            # Deterministic ID recovers a draft if a previous cross-store write failed.
            draft = store.get(advisory_id)
            if not draft:
                draft = Advisory(advisory_id, "arrival_review", FIRST_PORT, who.actor,
                    who.organisation or port_registry.resolve(FIRST_PORT).authority,
                    case["mmsi"], case["vesselName"], case["recipientOrganisation"], at,
                    {"review": case["recommendation"], "plannedArrivalAt": case["plannedArrivalAt"]},
                    "Weather and observed AIS are frozen for this arrival; waiting estimates are observational, not evidence of savings.",
                    prediction_ids=[case["predictionId"]] if case["predictionId"] else [],
                    evidence={"operationId": operation_id, "prediction": case["prediction"], "missingEvidence": case["missingEvidence"]},
                    decision_id=case["decisionId"], valid_until=case["plannedArrivalAt"])
                store.create(draft, principal=Principal(actor=who.actor, role=ISSUER, port_code=FIRST_PORT,
                                                       is_admin=who.role == NATIONAL_ADMIN))
            service.ledger.append_arrival_event(operation_id, "advisory", FIRST_PORT, who.actor,
                                               {"advisoryId": advisory_id}, at=at)
        return present(service.get(operation_id))
    return call(build)


@router.post("/arrivals/operations/{operation_id}/action")
def action(operation_id: str, payload: ActionInput, who: Identity = Depends(scope), service: ArrivalWorkflow = Depends(workflow)) -> dict:
    may_write(who, FIRST_PORT)
    def record():
        case = service.get(operation_id)
        advisory = get_advisory_store().get(case["advisoryId"]) if case["advisoryId"] else None
        if not advisory or not any(a.to_state == "issued" and instant(a.at) <= instant(payload.occurredAt) for a in advisory.audit):
            raise ValueError("An issued advisory must precede the reported action; acceptance alone is not actual action")
        body = {**payload.model_dump(mode="json"), "advisoryState": advisory.state,
                "advisoryAudit": [a.to_dict() for a in advisory.audit]}
        return present(service.action(operation_id, who.actor, body))
    return call(record)


@router.post("/arrivals/operations/{operation_id}/outcome")
def outcome(operation_id: str, payload: OutcomeInput, who: Identity = Depends(scope), service: ArrivalWorkflow = Depends(workflow)) -> dict:
    may_write(who, FIRST_PORT)
    return call(lambda: present(service.outcome(operation_id, who.actor, payload.model_dump(mode="json"))))


@router.post("/arrivals/benchmark")
def benchmark(who: Identity = Depends(scope), service: ArrivalWorkflow = Depends(workflow)) -> dict:
    may_write(who, FIRST_PORT)
    return call(lambda: service.evaluate(who.actor))
