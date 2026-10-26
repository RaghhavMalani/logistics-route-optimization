"""Public feedback reads and visitor-scoped review continuity, using fixtures only."""
from datetime import datetime
import hashlib
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes import shared_feedback as routes
from src.portwatch_os.learning import intelligence_reconciliation as collector
from src.portwatch_os.learning import shared_feedback as feedback
from src.portwatch_os.ledger.store import SqliteLedgerStore
from tests.feedback_originals import (
    AUTHORITY_ORIGINAL, NEWS_BYTES, NEWS_ORIGINAL, retain_test_originals,
)


ISSUE = "2026-10-13T10:00:00+00:00"
LATER = "2026-10-19T21:00:00+00:00"
AS_OF = "2026-10-23T12:00:00+00:00"
BASE = "/api/demo/terminal"


def news(store, number=0):
    return feedback.news_report(
        store, wording=f"SYNTHETIC operator announcement {number}",
        source="Synthetic attributed report", source_version=f"report-{number}:v1",
        independence_key=f"report-origin-{number}", event_key=f"fixture-lock:{number}",
        entity=f"Fixture Lock {number}", geography="Synthetic canal area",
        target={"kind": "ANNOUNCEMENT", "predicate": "OPERATOR_ANNOUNCED_LOCK_CLOSURE",
                "from": "2026-10-15", "through": "2026-10-17"},
        first_available_at=ISSUE, published_at=ISSUE, response_sha256=NEWS_ORIGINAL,
    )


def confirmation(store, item, **changes):
    return feedback.evidence(store, {
        "eventKey": item["eventKey"], "target": item["target"], "entity": item["entity"],
        "geography": item["geography"], "source": "Synthetic independent operator log",
        "sourceVersion": "operator-v1", "independenceKey": "fixture-operator",
        "firstAvailableAt": LATER, "observedAt": "2026-10-15T12:00:00+00:00",
        "unit": "boolean", "aggregation": "EXPLICIT_NEWS_TARGET", "value": True,
        "recordKind": "AUTHORITY_RECORD", "responseSha256": AUTHORITY_ORIGINAL,
        **changes,
    })


def dump(path):
    with sqlite3.connect(path) as connection:
        return tuple(connection.iterdump())


@pytest.fixture
def public_api(tmp_path, monkeypatch):
    path = tmp_path / "public.db"
    monkeypatch.setattr(collector, "DB", path)
    monkeypatch.setattr(collector, "ROOT", tmp_path)
    monkeypatch.setattr(routes, "wall_now", lambda: datetime.fromisoformat(AS_OF))
    retain_test_originals(tmp_path)
    store = SqliteLedgerStore(path)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    client = TestClient(app)
    yield store, client, path
    client.close()
    store.close()


def test_complete_public_audit_is_not_the_visible_page_and_gets_are_read_only(public_api, monkeypatch):
    store, client, path = public_api
    for index in range(105):
        news(store, index)
    # Future claims and collector runs must not leak into the selected as-of view.
    later = news(store, 200)
    body = {key: value for key, value in later.items() if key not in ("id", "contractVersion")}
    body.update(firstAvailableAt="2026-10-24T10:00:00+00:00", originAt="2026-10-24T10:00:00+00:00")
    feedback.claim(store, body)
    store.append_feedback("run", {"id": "past-run", "ranAt": ISSUE, "status": "COLLECTING"})
    store.append_feedback("run", {"id": "future-run", "ranAt": "2026-10-24T10:00:00+00:00", "status": "CURRENT"})
    before = dump(path)
    monkeypatch.setattr(collector, "collect_fx", lambda *a, **k: pytest.fail("GET collected a forecast"))
    monkeypatch.setattr(collector.requests, "get", lambda *a, **k: pytest.fail("GET fetched a provider"))
    first = client.get("/api/intelligence/feedback", params={"kind": "NEWS", "limit": 100, "asOf": AS_OF})
    assert first.status_code == 200, first.text
    view = first.json()
    assert view["dataset"]["filteredClaims"] == 106
    assert view["dataset"]["returnedClaims"] == 100 and view["dataset"]["hasMore"]
    assert view["newsAggregation"]["summary"]["independentTargets"] == 106
    assert view["collector"]["id"] == "past-run"
    second = client.get("/api/intelligence/feedback", params={"kind": "NEWS", "limit": 100, "offset": 100, "asOf": AS_OF}).json()
    audit = client.get("/api/intelligence/feedback/audit", params={"kind": "NEWS", "asOf": AS_OF})
    assert audit.status_code == 200, audit.text
    exported = audit.json()
    assert exported["dataset"]["complete"] is True
    assert exported["dataset"]["returnedClaims"] == 106
    assert exported["claims"] == view["claims"] + second["claims"]
    assert exported["newsAggregation"] == view["newsAggregation"]
    assert audit.headers["x-audit-sha256"] == hashlib.sha256(audit.content).hexdigest()
    assert "attachment" in audit.headers["content-disposition"]
    assert dump(path) == before
    # Fresh SQLite connections reproduce exactly the same fixed-clock export.
    assert client.get("/api/intelligence/feedback/audit", params={"kind": "NEWS", "asOf": AS_OF}).content == audit.content
    assert dump(path) == before


def test_as_of_hides_later_economic_outcome_news_evidence_and_assessment(public_api):
    store, client, path = public_api
    collector.collect_fx(store, b"observation_date,DEXINUS\n2026-10-12,96.31\n", ISSUE, path.parent)
    item = next(c for c in store.feedback("claim") if c["kind"] == "FORECAST")
    reported = news(store)
    confirmation(store, reported)
    feedback.verify_news(store, reported, LATER)
    collector.collect_fx(store, b"observation_date,DEXINUS\n2026-10-14,97.31\n", LATER, path.parent)
    feedback.reconcile(store, LATER)
    before = dump(path)
    early = client.get("/api/intelligence/feedback", params={"asOf": ISSUE}).json()
    fx = next(c for c in early["claims"] if c["id"] == item["id"])
    report = next(c for c in early["claims"] if c["id"] == reported["id"])
    assert fx["score"]["status"] == "open" and fx["score"]["error"] is None
    assert fx["match"] is None and fx["outcomes"] == []
    assert report["verification"] is None
    assert report["newsInspection"]["assessmentHistory"] == []
    assert report["newsInspection"]["currentAssessment"]["verdict"] == "UNRESOLVED"
    late = client.get("/api/intelligence/feedback", params={"asOf": AS_OF, "claimId": item["id"]}).json()
    assert late["claims"][0]["score"]["error"] == pytest.approx(1)
    assert late["claims"][0]["economicInspection"]["errorConvention"] == "observed minus predicted"
    assert dump(path) == before


@pytest.mark.parametrize("params", [
    {"asOf": "2026-10-13T10:00:00"}, {"asOf": "not-an-instant"},
    {"asOf": "2026-10-24T10:00:00+00:00"}, {"kind": "UNKNOWN"},
    {"offset": -1}, {"limit": 101}, {"limit": 0},
])
def test_inspection_rejects_invalid_or_future_selection_without_writes(public_api, params):
    _, client, path = public_api
    before = dump(path)
    assert client.get("/api/intelligence/feedback", params=params).status_code == 422
    if "asOf" in params or "kind" in params:
        assert client.get("/api/intelligence/feedback/audit", params=params).status_code == 422
    assert dump(path) == before


def test_selected_audit_receipts_and_download_hash_have_original_parity_without_paths(public_api):
    store, client, path = public_api
    item = news(store)
    decisive = confirmation(store, item)
    collector.retain_response(store, NEWS_BYTES, "https://fixture.example/report", ISSUE, path.parent)
    feedback.verify_news(store, item, LATER)
    audit = client.get("/api/intelligence/feedback/audit", params={"claimId": item["id"], "asOf": AS_OF})
    data = audit.json()
    selected = client.get("/api/intelligence/feedback", params={"claimId": item["id"], "asOf": AS_OF}).json()
    assert data["claims"] == selected["claims"]
    assert data["dataset"]["exportScope"] == "SELECTED_CLAIM_AS_OF"
    assert {row["id"] for row in data["evidence"]} == {decisive["id"]}
    assert data["receipts"][0]["responseSha256"] == NEWS_ORIGINAL
    assert "archivePath" not in audit.text and str(path.parent) not in audit.text
    original = client.get("/api/intelligence/feedback/evidence/" + NEWS_ORIGINAL)
    assert original.status_code == 200 and original.content == NEWS_BYTES
    assert original.headers["x-source-sha256"] == hashlib.sha256(original.content).hexdigest()
    store.append_feedback("news-source-quality", {"id": item["id"], "originalAccess": "LOCAL_RESEARCH_ARCHIVE"})
    assert client.get("/api/intelligence/feedback/evidence/" + NEWS_ORIGINAL).status_code == 403


def test_relevant_news_change_reaches_existing_review_guard_without_rewriting_task(tmp_path, monkeypatch):
    from tests.test_demo_terminal import setup, resources
    from backend.app.routes import shipping_intelligence
    store, client = setup(tmp_path, monkeypatch)
    sources = tmp_path / "sources"
    sources.mkdir(exist_ok=True)
    retain_test_originals(sources)
    # Generic retained-original lookup also supports the ledger's local archive.
    retain_test_originals(tmp_path)
    monkeypatch.setattr(shipping_intelligence, "ROOT", sources)
    clock = [datetime.fromisoformat("2026-10-18T12:00:00+00:00")]
    monkeypatch.setattr(shipping_intelligence, "wall_now", lambda: clock[0])
    public = collector.open_public()
    item = news(public)
    public.append_feedback("news-source-quality", {"id": item["id"], "sourceFamily": "SYNTHETIC_TEST_ONLY"})
    feedback.verify_news(public, item, ISSUE)
    public.close()
    session = store.create("SHIPPING_COMPANY")
    headers = {"Authorization": "Bearer " + session["accessToken"]}
    request = {"claimId": item["id"], "vesselId": "PWD-001", "requestId": "fixture-review-continuity"}
    created = client.post(BASE + "/intelligence/review-tasks", headers=headers, json=request)
    assert created.status_code == 200, created.text
    frozen_task = created.json()
    frozen = frozen_task["source"]["feedbackConsumption"]
    public = collector.open_public()
    # Unused claims and neutral descriptive statistics are not dependencies.
    unrelated = news(public, 99)
    confirmation(public, unrelated, firstAvailableAt="2026-10-18T11:00:00+00:00")
    feedback.verify_news(public, unrelated, "2026-10-18T11:00:00+00:00")
    feedback.require_consumption(public, frozen, now=clock[0].isoformat())
    public.close()
    untouched = client.get(BASE + "/intelligence/review-tasks", headers=headers).json()["tasks"][0]
    assert untouched["sourceReview"]["status"] == "UNCHANGED"
    # A newly retained decisive record is sufficient to require review even if
    # the next worker has not yet appended a stored assessment.
    public = collector.open_public()
    confirmation(public, item)
    clock[0] = datetime.fromisoformat(AS_OF)
    with pytest.raises(ValueError, match="verification changed"):
        feedback.require_consumption(public, frozen, now=AS_OF)
    public.close()
    resources.cache_clear()
    changed = client.get(BASE + "/intelligence/review-tasks", headers=headers).json()["tasks"][0]
    assert changed["sourceReview"]["status"] == "REVIEW_REQUIRED"
    assert changed["sourceReview"]["requiresFreshReview"] is True
    assert changed["sourceReview"]["currentAssessment"]["verdict"] == "CORROBORATED"
    assert changed["sourceReview"]["realOperationalTargetsAdded"] == 0
    assert {k: v for k, v in changed.items() if k != "sourceReview"} == frozen_task
    assert client.post(BASE + "/intelligence/review-tasks", headers=headers, json=request).json() == frozen_task
    successor = client.post(BASE + "/intelligence/review-tasks", headers=headers,
        json={**request, "requestId": "fixture-fresh-evidence-review"})
    assert successor.status_code == 200, successor.text
    fresh = successor.json()
    assert fresh["source"]["verification"]["verdict"] == "CORROBORATED"
    resources.cache_clear()
    projected = client.get(BASE + "/intelligence/review-tasks", headers=headers).json()["tasks"]
    by_id = {row["id"]: row for row in projected}
    assert by_id[fresh["id"]]["sourceReview"]["status"] == "UNCHANGED"
    assert by_id[frozen_task["id"]]["sourceReview"]["status"] == "REVIEW_REQUIRED"
    stranger = store.create("SHIPPING_COMPANY")
    other = {"Authorization": "Bearer " + stranger["accessToken"]}
    assert client.get(BASE + "/intelligence/review-tasks", headers=other).json()["tasks"] == []
    assert client.get(BASE + "/intelligence/feedback/impacts", headers=other).json()["claims"] == []
    client.close()
