"""Actual public report case, anonymous publication boundaries and replay."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import public_cases
from src.portwatch_os.clock import get_clock
from src.portwatch_os.intelligence import public_collection
from src.portwatch_os.intelligence.public_ports import PublicPilot

PDFS = Path(__file__).parent / "fixtures/public_ports"
COLLECTED = datetime(2026, 10, 7, 11, 42, 18, tzinfo=timezone.utc)
OUTCOMES = datetime(2026, 10, 8, 8, 25, 9, tzinfo=timezone.utc)
REVIEWED = OUTCOMES + timedelta(hours=1)


@pytest.fixture
def published(tmp_path, monkeypatch):
    store = PublicPilot(tmp_path)
    for day, at in ((7,COLLECTED),(8,OUTCOMES)):
        store.import_pdf("INPRT", "traffic", f"https://www.paradipport.gov.in/uploads/2026/10/dtr{day:02d}10.pdf",
            (PDFS/f"paradip-2026-10-{day:02d}.pdf").read_bytes(), collected=at, actor="PRIVATE_COLLECTOR_NAME")
    workspace = store.workspace("INPRT", REVIEWED)
    call = next(c for c in workspace["cases"] if c["nameKey"] == "GLAD YOUNG")
    chain = public_collection.verify_chain(store, workspace, call)
    info = public_collection.prepare_audit(store.root, chain, OUTCOMES.isoformat())
    path = Path(info["json"])
    audit = json.loads(path.read_text(encoding="utf-8"))
    audit["visualReview"] = {"status":"PASSED", "reviewer":"PRIVATE_REVIEWER_NAME", "reviewedAt":REVIEWED.isoformat(),
        "pageChecks":[{"event":e["event"], "status":"PASSED", "reviewedAt":REVIEWED.isoformat(),
            "sourceHashVerified":True, "sourceSha256":e["sha256"], "originalPage":e["page"],
            "observedFields":{"rawPublisherClock":e["rawTimestamps"][{"frozenEta":"etaAt","reportedArrival":"arrivalAt","reportedBerth":"berthAt"}[e["event"]]],
                "vesselName":e["reportedVesselName"],"loaMetres":e["loaMetres"],"beamMetres":e["beamMetres"],
                "berthRef":e["berthRef"],"printedDateHeadings":["08-10-2026"]},
            "checks":{"identity":True,"clock":True,"heading":True,"berth":True}} for e in audit["evidence"]]}
    path.write_text(json.dumps(audit), encoding="utf-8")
    monkeypatch.setenv("PORTWATCH_IDENTITY_MODE", "verified")
    monkeypatch.setenv("PORTWATCH_PUBLIC_CASE_DIR", str(tmp_path/"publication"))
    monkeypatch.setattr(public_cases, "get_service", lambda:store)
    monkeypatch.setattr(public_collection, "get_service", lambda:store)
    client = TestClient(app)
    with get_clock().pin_replay(REVIEWED+timedelta(seconds=1)):
        yield client, store, path
    client.close()
    store.close()


def test_real_reviewed_case_has_baseline_error_and_web_evidence(published):
    client, _, _ = published
    response = client.get("/api/public/port-calls")
    assert response.status_code == 200
    call = response.json()["cases"][0]
    assert call["vesselName"] == "MV. GLAD YOUNG"
    assert call["publishedEtaBaselineErrorMinutes"] == -24 and call["reportedWaitingHours"] == 2.4
    assert call["identity"]["mmsi"] is None and call["berthRef"] == "SQ"
    assert "PRIVATE_" not in response.text and "path" not in response.text and str(published[1].root) not in response.text
    for e in call["events"]:
        pdf = client.get(e["url"].split("#")[0])
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
        assert pdf.headers["content-type"] == "application/pdf" and pdf.headers["etag"] == '"'+e["sha256"]+'"'
    exported = client.get(call["auditUrl"])
    assert exported.status_code == 200 and exported.json() == call
    assert "attachment" in exported.headers["content-disposition"]


def test_replay_withholds_later_outcomes_reviews_and_originals(published):
    client, _, _ = published
    with get_clock().pin_replay(OUTCOMES-timedelta(seconds=1)):
        data = client.get("/api/public/port-calls").json()
        assert data["cases"] == []
        sha = public_cases.digest((PDFS/"paradip-2026-10-08.pdf").read_bytes())
        assert client.get(f"/api/public/port-calls/evidence/{sha}.pdf").status_code == 404
    with get_clock().pin_replay(REVIEWED-timedelta(seconds=1)):
        assert client.get("/api/public/port-calls").json()["cases"] == []


@pytest.mark.parametrize("problem", ["pending", "failed_page", "changed_outcome", "corrupt_pdf"])
def test_unreviewed_or_inconsistent_case_is_not_published(published, problem):
    client, store, path = published
    audit = json.loads(path.read_text(encoding="utf-8"))
    if problem == "pending": audit["visualReview"]["status"] = "PENDING"
    elif problem == "failed_page": audit["visualReview"]["pageChecks"][1]["checks"]["clock"] = False
    elif problem == "changed_outcome": audit["reportedBerthAt"] = "2026-10-07T22:30:00Z"
    else:
        sha = audit["evidence"][0]["sha256"]
        (store.root/"evidence"/(sha+".pdf")).write_bytes(b"%PDF-corrupt")
        assert client.get(f"/api/public/port-calls/evidence/{sha}.pdf").status_code == 404
    path.write_text(json.dumps(audit), encoding="utf-8")
    assert client.get("/api/public/port-calls").json()["cases"] == []
    assert client.get(f"/api/public/port-calls/{audit['caseId']}/audit").status_code == 404


def test_public_call_routes_deny_writes_unknown_files_and_private_headers(published):
    client, _, _ = published
    for path in ("/api/public/port-calls", "/api/public/port-calls/evidence/"+"a"*64+".pdf"):
        assert client.post(path, headers={"X-PortWatch-Role":"NATIONAL_ADMIN"}).status_code == 401
    assert client.get("/api/public/port-calls/evidence/"+"a"*64+".pdf").status_code == 404
    assert client.get("/api/intelligence/cameras", headers={"X-PortWatch-Role":"NATIONAL_ADMIN"}).status_code == 401
    assert client.get("/api/public/port-calls/private-data").status_code == 401


def test_freshness_for_a_failed_latest_run_uses_the_last_success(published):
    client, store, _ = published
    for at, errors in (("2026-10-08T04:09:00.000000Z", []), ("2026-10-08T08:25:00.000000Z", []), ("2026-10-08T11:30:00.000000Z", ["test failure"])):
        body = {"startedAt":at, "finishedAt":at, "errors":errors}
        store.db.execute("INSERT INTO collections VALUES(?,?,?,?)", (at,"INPRT",at,json.dumps(body)))
    store.db.commit()
    with get_clock().pin_replay(datetime(2026,10,8,12,tzinfo=timezone.utc)):
        port = client.get("/api/public/port-calls").json()["ports"][0]
        assert port["collectionFailed"] and port["freshness"] == "OVERDUE"
        assert port["collectionDelayMinutes"] == 5 and port["expectedCollectionAt"] == "2026-10-08T11:25:00+00:00"


def test_archived_publication_survives_missing_collection_database_and_checks_hashes(published, monkeypatch):
    from unittest.mock import patch
    client, store, _ = published
    case = client.get("/api/public/port-calls").json()["cases"][0]
    folder = store.root/"publication/case-publication-0123456789abcdef"
    (folder/"evidence").mkdir(parents=True)
    documents = []
    for e in case["events"]:
        (folder/"evidence"/(e["sha256"]+".pdf")).write_bytes((store.root/"evidence"/(e["sha256"]+".pdf")).read_bytes())
        documents.append({k:e[k] for k in ("sha256","sourceUrl","firstSeenAt")})
    manifest = {"publishedAt":REVIEWED.isoformat(), "cases":[case], "documents":documents}
    body = json.dumps(manifest).encode()
    (folder/"publication.json").write_bytes(body)
    pointer = folder.parent/"current.json"
    pointer.write_text(json.dumps({"publicationId":folder.name,"sha256":public_cases.digest(body)}))
    with patch.object(public_cases,"get_service",side_effect=OSError("PRIVATE_DB_PATH")):
        data = client.get("/api/public/port-calls").json()
        assert data["cases"][0]["archivedPublication"] is True and data["ports"] == []
        assert "PRIVATE_DB_PATH" not in json.dumps(data)
    assert client.get(case["events"][0]["url"].split("#")[0]).status_code == 200
    (folder/"publication.json").write_bytes(b"changed")
    assert client.get("/api/public/port-calls").status_code == 503
