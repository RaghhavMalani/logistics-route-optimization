"""Semantic targets, causal availability and durable connected consumption."""
import copy
import json
import pytest
from src.portwatch_os.ledger.store import SqliteLedgerStore, LedgerError
from src.portwatch_os.learning import shared_feedback as f
from src.portwatch_os.learning import intelligence_reconciliation as collector

ORIGIN = "2026-10-13T10:00:00+00:00"
LATER = "2026-10-19T21:00:00+00:00"


def fx(store, tmp_path):
    collector.collect_fx(store, b"observation_date,DEXINUS\n2026-10-12,96.31\n2026-10-13,.\n", ORIGIN, tmp_path)
    return next(c for c in store.feedback("claim") if c["kind"] == "FORECAST")


def report(store, source="Reuters", wording="The operator announced a closure", target_kind="ANNOUNCEMENT"):
    return f.news_report(store, wording=wording, source=source, source_version=source+":v1", independence_key="Reuters wire",
        event_key="operator-notice:17", entity="Lock A", geography="Canal control area",
        target={"kind": target_kind, "from": "2026-10-15", "through": "2026-10-17"},
        first_available_at=ORIGIN, published_at=ORIGIN, response_sha256="a"*64)


def authority(store, item, **changes):
    return f.evidence(store, {"eventKey": item["eventKey"], "target": item["target"], "entity": item["entity"],
        "geography": item["geography"], "source": "Canal authority log", "sourceVersion": "authority-v1",
        "independenceKey": "Canal authority", "firstAvailableAt": LATER, "observedAt": "2026-10-15T12:00:00+00:00",
        "unit": "boolean", "aggregation": "EXPLICIT_NEWS_TARGET", "value": True,
        "recordKind": "AUTHORITY_RECORD", "responseSha256": "b"*64, **changes})


def test_syndication_is_one_event_not_multiple_observations(tmp_path):
    store = SqliteLedgerStore(tmp_path/"ledger.db")
    a = report(store); b = report(store, source="Syndicating newspaper")
    assert a["id"] != b["id"]
    authority(store, a, independenceKey="Reuters wire")
    assert f.verify_news(store, a, LATER)["verdict"] == "UNRESOLVED"
    authority(store, a)
    for item in (a, b): assert f.verify_news(store, item, LATER)["verdict"] == "CORROBORATED"
    view = f.inspect(store, LATER)
    assert view["newsIndependentEvents"] == 1
    assert len(view["events"][0]["reportIds"]) == 2
    assert view["reliability"]["consumedWeight"] == 1
    store.close()


def test_announcement_actual_cancellation_and_contradiction_are_separate(tmp_path):
    store = SqliteLedgerStore(tmp_path/"ledger.db")
    announcement = report(store); actual = report(store, target_kind="ACTUAL_EVENT")
    confirmation = authority(store, announcement)
    assert f.verify_news(store, announcement, LATER)["verdict"] == "CORROBORATED"
    assert f.verify_news(store, actual, LATER)["verdict"] == "UNRESOLVED"
    authority(store, announcement, recordKind="CANCELLATION", cancelsSourceVersion=announcement["sourceVersion"], value=None)
    after = f.verify_news(store, announcement, LATER)
    assert (after["verdict"], after["applicability"]) == ("CORROBORATED", "SUPERSEDED")
    authority(store, announcement, value=False, sourceVersion="authority-v2", supersedes=confirmation["id"])
    assert f.verify_news(store, announcement, LATER)["verdict"] == "CONTRADICTED"
    assert len(store.feedback("assessment")) >= 3
    store.close()


def test_future_authority_does_not_verify_now(tmp_path):
    store = SqliteLedgerStore(tmp_path/"ledger.db"); item = report(store)
    authority(store, item)
    assert f.verify_news(store, item, ORIGIN)["verdict"] == "UNRESOLVED"
    f.verify_news(store, item, LATER)
    visitor=SqliteLedgerStore(tmp_path/"visitor.db")
    frozen=f.freeze_consumption(store,visitor,[item["id"]],ORIGIN)
    assert frozen["inputs"][0]["assessment"]["verdict"] == "UNRESOLVED"
    assert frozen["reliabilityVersion"]["newsSlices"][0]["independentTargets"] == 0
    f.require_consumption(store,frozen,now=ORIGIN)
    visitor.close()
    store.close()


def test_persistence_observations_missing_dates_revision_and_restart(tmp_path):
    path = tmp_path/"ledger.db"; store = SqliteLedgerStore(path); item = fx(store, tmp_path)
    assert item["target"]["date"] == "2026-10-14"
    assert len(store.predictions()) == 1  # Historical quotes are not predictions.
    assert len(store.feedback("missing-date")) == 1
    assert f.reconcile(store, ORIGIN)[0] == 0
    raw = b"observation_date,DEXINUS\n2026-10-12,96.31\n2026-10-14,97.31\n"
    collector.collect_fx(store, raw, LATER, tmp_path)
    f.reconcile(store, LATER)
    assert store.get_prediction(item["id"]).error == pytest.approx(1)
    collector.collect_fx(store, raw, LATER, tmp_path)
    assert len([e for e in store.feedback("evidence") if e["eventKey"] == "DEXINUS:2026-10-14"]) == 1
    actual = next(e for e in store.feedback("evidence") if e["eventKey"] == "DEXINUS:2026-10-14")
    f.evidence(store, {**{k:v for k,v in actual.items() if k != "id"}, "value":1200,
        "recordKind":"SIMULATED", "firstAvailableAt":"2026-10-20T09:00:00+00:00"})
    assert f.reliability_version(store, "2026-10-20T10:00:00+00:00")["slices"][0]["independentTargets"] == 1
    collector.collect_fx(store, raw.replace(b"97.31", b"97.50"), "2026-10-20T11:00:00+00:00", tmp_path)
    assert store.get_prediction(item["id"]).observed_value == 97.31
    assert f.reliability_version(store, "2026-10-20T12:00:00+00:00")["slices"] == []
    collector.collect_fx(store, raw, "2026-10-21T12:00:00+00:00", tmp_path)
    vintages = [e for e in store.feedback("evidence") if e["eventKey"] == "DEXINUS:2026-10-14"]
    assert len([v for v in vintages if v["recordKind"] == "ECONOMIC_OBSERVATION"]) == 3  # Reversion is a new vintage.
    assert max(vintages, key=lambda e:e["firstAvailableAt"])["value"] == 97.31
    assert f.reliability_version(store, "2026-10-20T10:00:00+00:00")["slices"][0]["independentTargets"] == 1
    store.close(); store = SqliteLedgerStore(path)
    assert store.get_prediction(item["id"]).observed_value == 97.31
    assert len(store.feedback("match", item["id"])) == 1
    assert len(f.inspect(store, "2026-10-20T12:00:00+00:00")["claims"][0]["inputs"]) == 1
    store.close()


@pytest.mark.parametrize("change", [{"unit": "USD/INR"}, {"recordKind": "SIMULATED"},
    {"recordKind":"ACTUAL_OPERATIONAL_RECORD","independentTargetKey":"wrong-economic-record-kind"},
    {"aggregation": "CLOSING_PRICE"}, {"entity": "EUR/INR"}, {"firstAvailableAt": "2026-10-21T00:00:00+00:00"}])
def test_wrong_units_identity_availability_and_simulation_do_not_score(tmp_path, change):
    store = SqliteLedgerStore(tmp_path/"ledger.db"); item = fx(store, tmp_path)
    f.evidence(store, {"eventKey": item["eventKey"], "target": item["target"], "entity": item["entity"],
        "geography": item["geography"], "source": "Federal Reserve H.10", "sourceVersion": "new-vintage",
        "independenceKey": "Federal Reserve H.10", "firstAvailableAt": LATER,
        "observedAt": "2026-10-14T00:00:00+00:00", "unit": f.FX_UNIT, "aggregation": f.FX_AGGREGATION,
        "value": 97.31, "recordKind": "ECONOMIC_OBSERVATION", "responseSha256": "b"*64, **change})
    assert f.reconcile(store, LATER)[0] == 0
    assert store.get_prediction(item["id"]).observed_value is None
    store.close()


def test_immutable_consumption_requires_new_review_and_is_private(tmp_path):
    public = SqliteLedgerStore(tmp_path/"public.db"); visitor = SqliteLedgerStore(tmp_path/"a.db")
    other = SqliteLedgerStore(tmp_path/"b.db"); item = report(public)
    f.verify_news(public, item, ORIGIN)
    consumed = f.freeze_consumption(public, visitor, [item["id"]], ORIGIN)
    assert not other.feedback("consumption")
    assert visitor.feedback("consumption")[0]["id"] == consumed["id"]
    authority(public, item); f.verify_news(public, item, LATER)
    with pytest.raises(ValueError, match="verification changed"): f.require_consumption(public, consumed, now=LATER)
    successor = f.freeze_consumption(public, visitor, [item["id"]], LATER)
    assert successor["id"] != consumed["id"]
    assert len(visitor.feedback("consumption")) == 2
    with pytest.raises(LedgerError): visitor.append_feedback("consumption", {**consumed, "effect": "changed"})
    public.close(); visitor.close(); other.close()


def test_future_input_and_backdated_forecast_rejected(tmp_path):
    store = SqliteLedgerStore(tmp_path/"ledger.db"); item = fx(store, tmp_path)
    body = {k:v for k,v in item.items() if k not in ("id", "contractVersion")}
    body["inputs"][0]["firstAvailableAt"] = LATER
    with pytest.raises(ValueError, match="unavailable"): f.claim(store, body)
    body["originAt"] = "2026-10-15T10:00:00+00:00"
    with pytest.raises(ValueError, match="future target"): f.claim(store, body)
    store.close()


@pytest.mark.parametrize("family", ["economic", "news"])
def test_context_stays_nonnumerical_and_review_task_recovers_across_roles(tmp_path, monkeypatch, family):
    from tests.test_demo_terminal import setup, resources
    from tests.test_current_recovery import BASE, step
    from src.portwatch_os.clock import wall_now
    store, client = setup(tmp_path, monkeypatch)
    monkeypatch.setattr("backend.app.routes.shipping_intelligence.ROOT", tmp_path/"sources")
    now = wall_now(); public = collector.open_public()
    day = (now-f.timedelta(days=2)).date().isoformat()
    collector.collect_fx(public, f"observation_date,DEXINUS\n{day},96.31\n".encode(), now.isoformat(), tmp_path/"sources")
    if family == "news":
        collector.collect_news_product(public, {"events": [{"title": "Centcom says 133 vessels redirected in Hormuz as it enforces Iran blockade",
            "url": "https://fixture-news.example/report", "affectedPorts": ["INNSA"], "tag": "CHOKEPOINT_CLOSURE"}]}, now.isoformat(), tmp_path/"sources")
    item = next(c for c in public.feedback("claim") if c["kind"] == ("FORECAST" if family == "economic" else "REPORTED_FACT")); public.close()
    session = store.create("SHIPPING_COMPANY"); token = session["accessToken"]; headers = {"Authorization": "Bearer " + token}
    response = client.post(BASE+"/intelligence/feedback/comparison", headers=headers,
        json={"claimId": item["id"], "vesselId": "PWD-001", "assumedHoldHours": 6})
    if family == 'economic':
        assert response.status_code == 422 and 'does not justify a vessel hold' in response.text
        view=client.get(BASE+'/intelligence/feedback',headers=headers).json()
        assert any(c['id']==item['id'] and c['score']['status']=='open' for c in view['claims'])
        assert not client.get(BASE+'/intelligence/feedback/impacts',headers=headers).json()['claims']
        client.close()
        return
    assert response.status_code == 422 and 'review-tasks' in response.text
    task_path=BASE+'/intelligence/review-tasks'
    request={'claimId':item['id'],'vesselId':'PWD-001','requestId':'news-review-task-001'}
    original_path=tmp_path/'sources'/'shared_feedback'/(item['responseSha256']+'.response')
    original_bytes=original_path.read_bytes(); original_path.write_bytes(b'corrupted source')
    rejected=client.post(task_path,headers=headers,json=request)
    assert rejected.status_code==409 and 'corrupt' in rejected.text
    assert client.get(task_path,headers=headers).json()['tasks']==[]
    original_path.write_bytes(original_bytes)
    created=client.post(task_path,headers=headers,json=request)
    assert created.status_code==200,created.text
    task=created.json()
    assert task['kind']=='SOURCE_EXPOSURE_VERIFICATION_TASK'
    assert task['status']=='PENDING_VERIFICATION'
    assert task['source']['claim']==item
    assert task['calculatedDelayHours'] is None and task['calculatedCost'] is None
    assert task['actualExecutionStatus']=='NOT_OBSERVED' and task['createsOperationalTarget'] is False
    assert not store.read(token).get('terminalProposal')
    resources.cache_clear()
    # A retained task retries from durable state even if its original later fails.
    original_path.write_bytes(b'corrupted source')
    assert client.post(task_path,headers=headers,json=request).json()==task
    original_path.write_bytes(original_bytes)
    assert client.post(task_path,headers=headers,json={**request,'claimId':'another-claim'}).status_code==409
    for role in ('PORT_AUTHORITY','VESSEL_OPERATOR','NATIONAL_ADMIN'):
        store.switch(token,role)
        assert client.get(task_path,headers=headers).json()['tasks']==[task]
        assert client.post(task_path,headers=headers,json=request).status_code==403
    assert not client.get(BASE+'/intelligence/feedback/impacts',headers=headers).json()['claims']
    other=store.create('SHIPPING_COMPANY');other_headers={'Authorization':'Bearer '+other['accessToken']}
    assert client.get(task_path,headers=other_headers).json()['tasks']==[]
    assert not client.get(BASE+'/intelligence/feedback/impacts',headers=other_headers).json()['claims']
    assert client.get(BASE+'/intelligence/feedback',headers=headers).json()['newsAggregation']['summary']['resolvedIndependentTargets']==0
    client.close()


def test_news_source_product_repeated_receipts_preserve_first_availability_and_ignore_closure_tag(tmp_path):
    store = SqliteLedgerStore(tmp_path/"ledger.db")
    bundle = {"events": [{"title": "Centcom says 133 vessels redirected in Hormuz as it enforces Iran blockade",
        "url": "https://fixture.example/report", "timestamp": "2026-10-10T06:45:00", "tag": "CHOKEPOINT_CLOSURE", "affectedPorts": ["INNSA"]},
        {"title": "Keeping the Malacca Strait Safe", "url": "https://fixture.example/safe", "tag": "CHOKEPOINT_CLOSURE"}]}
    collector.collect_news_product(store, bundle, ORIGIN, tmp_path)
    collector.collect_news_product(store, bundle, LATER, tmp_path)
    assert len(store.feedback("claim")) == 1
    item = store.feedback("claim")[0]
    assert item["firstAvailableAt"] == ORIGIN and item["publishedAt"] is None
    assert item["value"] == 133 and item["unit"] == "vessels"
    assert not store.feedback("news-source-quality")[0]["articleBodyRetained"]
    changed_period = {**item["target"], "reportedPeriod": "A later reporting period"}
    authority(store, item, target=changed_period, value=135, unit="vessels")
    assert f.verify_news(store, item, LATER)["verdict"] == "UNRESOLVED"
    store.close()


def test_legacy_approved_targets_without_episode_and_execution_stay_unscored(tmp_path):
    store = SqliteLedgerStore(tmp_path/"ledger.db")
    for decision in ("company", "port-review"):
        body={"kind":"FORECAST","wording":"Conditional selected wait","value":6,"unit":"hours","aggregation":"SELECTED_VOYAGE_OPTION",
            "entity":"vessel-A","geography":"port-A","originAt":ORIGIN,"firstAvailableAt":ORIGIN,"source":"conditional scenario",
            "sourceVersion":decision,"eventKey":decision+":WAITING","independenceKey":"PortWatch scenario","inputs":[],
            "independentTargetKey":"one-voyage-one-wait","target":{"kind":"WAITING","at":"2026-10-15T12:00:00+00:00","decisionId":decision}}
        item=f.claim(store,body);f.register_prediction(store,item,"operational_consequence")
        record={"eventKey":item["eventKey"],"target":item["target"],"entity":item["entity"],"geography":item["geography"],
            "source":"Independent operator log fixture","sourceVersion":"record-1","independenceKey":"Operator",
            "independentTargetKey":"one-voyage-one-wait","firstAvailableAt":LATER,"observedAt":"2026-10-15T13:00:00+00:00",
            "unit":"hours","aggregation":"SELECTED_VOYAGE_OPTION","value":4,"recordKind":"ACTUAL_OPERATIONAL_RECORD","responseSha256":"b"*64}
        f.evidence(store,record)
        assert f.reconcile(store,LATER)[0]==0  # Counterfactual/unapproved cannot settle.
        store.append_feedback("selected-impact",{"id":item["id"],"decisionId":decision})
        assert f.reconcile(store,LATER)[0]==0
    view=f.reliability_version(store,"2026-10-20T00:00:00+00:00")
    assert view["slices"]==[]
    assert len(store.feedback("claim"))==2  # Historical records remain inspectable.
    assert view["consumedWeight"]==1
    store.close()
