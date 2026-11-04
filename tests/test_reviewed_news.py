"""Synthetic reviewed-family contracts, not evidence of real closure/savings."""
import copy
import hashlib
import json
from datetime import datetime

import pytest
import requests

from src.portwatch_os.ledger.store import SqliteLedgerStore
from src.portwatch_os.learning import reviewed_news as reviewed
from src.portwatch_os.learning import news_vintages as vintages
from src.portwatch_os.learning import shared_feedback as feedback
from src.portwatch_os.intelligence import operational_notices

T0 = '2026-10-10T10:00:00+00:00'
T1 = '2026-10-11T10:00:00+00:00'
T2 = '2026-10-12T10:00:00+00:00'
T3 = '2026-10-13T10:00:00+00:00'


def article():
    # Clearly synthetic HTML with the reviewed grammar; no provider original
    # is copied into the source repository or manufactured as live evidence.
    rows = [
        ('September', 7, 16, '19.38', 'BST', 6, '03.12', 17),
        ('October', 6, 15, '19.33', 'BST', 5, '02.42', 16),
        ('November', 9, 18, '22.30', 'GMT', 8, '06.06', 19),
    ]
    content = ''.join(f'<li>{month} {start}-{end}, 2026<br>'
        f'Last operational tide: {last} ({zone}) HW on {month} {last_day}, 2026<br>'
        f'First operational tide: {first} ({zone}) HW on {month} {first_day}, 2026</li>'
        for month, start, end, last, zone, last_day, first, first_day in rows)
    return ("<html><h1>SIMULATED reviewed parser fixture</h1>"
        "<p>The Eastham 80′ Lock will close to vessel movements.</p><ul>" + content +
        '</ul><p>The Queen Elizabeth II Lock will not be affected by the works.</p></html>').encode()


def authority_fixture(tmp_path, monkeypatch, raw=None):
    raw = raw or b'SIMULATED primary notice original; parser is mocked explicitly'
    parsed = reviewed.parse_gac_eastham(article())
    document = {'noticeRef': reviewed.REFERENCE, 'areaId': reviewed.ENTITY,
        'windows': [{**row, 'start': row['closureStartDate'] + 'T00:00:00+00:00',
                     'end': row['firstOperationalTide']} for row in parsed['windows']],
        'publishedDate': '2026-08-10', 'status': 'SCHEDULED'}
    digest = hashlib.sha256(raw).hexdigest()
    folder = tmp_path / 'operational_notices'
    folder.mkdir(exist_ok=True)
    (folder / (digest + '.response')).write_bytes(raw)
    monkeypatch.setattr(operational_notices, 'ROOT', tmp_path)
    monkeypatch.setattr(operational_notices, 'parse_eastham', lambda supplied: copy.deepcopy(document))
    return {**document, 'revisionId': hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest(), 'pdfSha256': digest,
        'pdfSource': operational_notices.PDF, 'availableAt': T0, 'source': operational_notices.SOURCE}


def test_parser_retains_calendar_precision_and_excludes_broader_consequences():
    parsed = reviewed.parse_gac_eastham(article())
    assert len(parsed['windows']) == 3
    assert parsed['windows'][1]['closureStartDate'] == '2026-10-06'
    assert parsed['windows'][1]['firstOperationalTide'] == '2026-10-16T01:42:00+00:00'
    assert parsed['publicationTime'] is None
    assert 'ACTUAL_CLOSURE_AND_SHIPPING_EFFECT_NOT_OBSERVED' in parsed['exclusions']
    assert reviewed._target(parsed['windows'][0])['reportedPeriod']['precision'] == 'DATE_ONLY'


@pytest.mark.parametrize('change', [
    lambda raw: raw.replace(b'will close', b'will not close'),
    lambda raw: raw.replace(b'September 7-16', b'September 17-6'),
    lambda raw: raw.replace(b'03.12', b'33.12'),
    lambda raw: raw.replace(b'<ul>', b'<p>These works were cancelled.</p><ul>'),
    lambda raw: raw.replace(b'Queen Elizabeth II', b'Unreviewed alternative'),
    lambda raw: raw.replace(b'November 9-18', b'November 19-18'),
])
def test_unsupported_changed_or_conflicting_body_fails_closed(change):
    with pytest.raises(ValueError):
        reviewed.parse_gac_eastham(change(article()))


def test_repeated_collection_retains_first_receipt_and_derived_interpretation(tmp_path, monkeypatch):
    notice = authority_fixture(tmp_path, monkeypatch)
    store = SqliteLedgerStore(tmp_path / 'ledger.db')
    first = reviewed.collect_gac_eastham(store, article(), T0, notice, root=tmp_path, interpreted_at=T1)
    original_bodies = copy.deepcopy(first)
    again = reviewed.collect_gac_eastham(store, article(), T2, notice, root=tmp_path, interpreted_at=T3)
    assert first == again == original_bodies
    assert len(store.feedback('claim')) == 3 and len(store.feedback('evidence')) == 3
    assert len(store.feedback('receipt')) == 1
    assert all(row['sourceFirstReceivedAt'] == T0 and row['firstAvailableAt'] == T1 for row in first)
    assert all(row['publishedAt'] is None for row in first)
    digest = first[0]['responseSha256']
    assert hashlib.sha256((tmp_path / 'shared_feedback' / (digest + '.response')).read_bytes()).hexdigest() == digest
    before = vintages.aggregate(store, T0)
    assert before['summary']['independentTargets'] == 0
    store.close()
    reopened = SqliteLedgerStore(tmp_path / 'ledger.db')
    assert reviewed.collect_gac_eastham(reopened, article(), T2, notice, root=tmp_path, interpreted_at=T3) == first
    assert len(reopened.feedback('claim')) == 3
    reopened.close()


def test_primary_document_exception_preserves_shared_origin_not_independent_occurrence(tmp_path, monkeypatch):
    notice = authority_fixture(tmp_path, monkeypatch)
    store = SqliteLedgerStore(tmp_path / 'ledger.db')
    claims = reviewed.collect_gac_eastham(store, article(), T0, notice, root=tmp_path, interpreted_at=T1)
    evidence = next(row for row in store.feedback('evidence') if row['target'] == claims[0]['target'])
    assert vintages.primary_announcement_verification(claims[0], evidence)
    assert vintages.lineage(claims[0]) == vintages.lineage(evidence)
    assert evidence['independentReportingConfirmations'] == 0
    assessment = feedback.news_assessment(store, claims[0], T1)
    assert assessment['verdict'] == 'CORROBORATED'
    assert assessment['verificationMode'] == reviewed.MODE
    assert assessment['independentReportingConfirmations'] == 0
    assert assessment['operationalEffectStatus'] == 'NOT_OBSERVED'
    assert assessment['realOperationalTargetsAdded'] == 0
    assert feedback.news_assessment(store, claims[0], T0)['verdict'] == 'UNRESOLVED'
    assert not any(row.get('recordKind') == 'ACTUAL_OPERATIONAL_RECORD' for row in store.feedback('evidence'))
    assert all(row['target']['kind'] == 'ANNOUNCEMENT' for row in claims)
    store.close()


@pytest.mark.parametrize('field,value', [
    ('sourceRole', 'PRIMARY_AUTHORITY_NOTICE'), ('sourceReportId', reviewed.REFERENCE),
    ('derivedFrom', None), ('sourceRevisionId', None), ('reviewedSourceFamily', 'GENERAL_ARTICLE'),
    ('source', 'https://unreviewed.example/report'),
])
def test_exception_does_not_allow_self_confirmation_or_missing_attribution(tmp_path, monkeypatch, field, value):
    notice = authority_fixture(tmp_path, monkeypatch)
    store = SqliteLedgerStore(tmp_path / 'ledger.db')
    claim = reviewed.collect_gac_eastham(store, article(), T0, notice, root=tmp_path, interpreted_at=T1)[0]
    evidence = next(row for row in store.feedback('evidence') if row['target'] == claim['target'])
    assert not vintages.primary_announcement_verification({**claim, field: value}, evidence)
    assert not vintages.primary_announcement_verification(claim, {**evidence, 'responseSha256': claim['responseSha256']})
    actual = {**claim, 'target': {**claim['target'], 'kind': 'ACTUAL_EVENT'}}
    assert not vintages.primary_announcement_verification(actual, evidence)
    other_period = {**evidence, 'target': {**evidence['target'], 'reportedPeriod': {'from': '2026-09-08', 'through': '2026-09-16', 'precision': 'DATE_ONLY'}}}
    assert not vintages.primary_announcement_verification(claim, other_period)
    store.close()


def test_changed_original_cannot_be_qualified_as_the_retained_primary(tmp_path, monkeypatch):
    notice = authority_fixture(tmp_path, monkeypatch)
    original = tmp_path / 'operational_notices' / (notice['pdfSha256'] + '.response')
    original.write_bytes(b'SIMULATED corrupt replacement')
    store = SqliteLedgerStore(tmp_path / 'ledger.db')
    with pytest.raises(ValueError, match='corrupt'):
        reviewed.collect_gac_eastham(store, article(), T0, notice, root=tmp_path, interpreted_at=T1)
    assert len(store.feedback('evidence')) == 0
    store.close()


def test_provider_403_is_diagnostic_not_false_or_a_manufactured_claim(tmp_path, monkeypatch):
    response = requests.Response()
    response.status_code = 403
    def unavailable(*args, **kwargs):
        raise requests.HTTPError('Forbidden', response=response)
    monkeypatch.setattr(reviewed.requests, 'get', unavailable)
    store = SqliteLedgerStore(tmp_path / 'ledger.db')
    result = reviewed.refresh_gac_eastham(store, None, root=tmp_path)
    assert result['status'] == 'UNAVAILABLE' and result['failureKind'] == 'HTTP_403'
    assert store.feedback('claim') == [] and store.feedback('evidence') == []
    assert len(store.feedback('reviewed-news-source-check')) == 1
    store.close()


def test_explicit_primary_cancellation_survives_report_outage_without_falsifying_announcement(tmp_path, monkeypatch):
    notice = authority_fixture(tmp_path, monkeypatch)
    store = SqliteLedgerStore(tmp_path / 'ledger.db')
    claims = reviewed.collect_gac_eastham(store, article(), T0, notice, root=tmp_path, interpreted_at=T1)
    cancelled = {'noticeRef': reviewed.REFERENCE, 'status': 'CANCELLED', 'windows': []}
    raw = b'SIMULATED explicit withdrawal of the reviewed primary notice'
    digest = hashlib.sha256(raw).hexdigest()
    (tmp_path / 'operational_notices' / (digest + '.response')).write_bytes(raw)
    monkeypatch.setattr(operational_notices, 'parse_eastham', lambda supplied: copy.deepcopy(cancelled))
    monkeypatch.setattr(reviewed, 'wall_now', lambda: datetime.fromisoformat(T3))
    revision = {**cancelled, 'revisionId': hashlib.sha256(json.dumps(cancelled, sort_keys=True).encode()).hexdigest(),
        'pdfSha256': digest, 'pdfSource': operational_notices.PDF, 'availableAt': T2}
    response = requests.Response(); response.status_code = 403
    monkeypatch.setattr(reviewed.requests, 'get', lambda *a, **k: (_ for _ in ()).throw(requests.HTTPError('Forbidden', response=response)))
    result = reviewed.refresh_gac_eastham(store, revision, root=tmp_path)
    assert result['failureKind'] == 'HTTP_403' and result['primaryEvidenceStatus'] == 'RETAINED'
    cancellations = [row for row in store.feedback('evidence') if row['recordKind'] == 'CANCELLATION']
    assert len(cancellations) == 3
    assert {row['target']['reportedPeriod']['from'] for row in cancellations} == {item['target']['reportedPeriod']['from'] for item in claims}
    assert all(row['value'] is None and row['cancelsSourceVersion'] == claims[0]['sourceVersion'] for row in cancellations)
    assessment = feedback.news_assessment(store, claims[0], T3)
    assert assessment['verdict'] == 'CORROBORATED' and assessment['applicability'] == 'SUPERSEDED'
    assert feedback.news_assessment(store, claims[0], T1)['applicability'] == 'AS_REPORTED'
    assert len(store.feedback('claim')) == 3  # No false/actual-event forecast was created.
    reviewed.refresh_gac_eastham(store, revision, root=tmp_path)
    assert len([row for row in store.feedback('evidence') if row['recordKind'] == 'CANCELLATION']) == 3
    store.close()


def test_missing_feed_record_is_not_primary_cancellation(tmp_path, monkeypatch):
    notice = authority_fixture(tmp_path, monkeypatch)
    store = SqliteLedgerStore(tmp_path / 'ledger.db')
    reviewed.collect_gac_eastham(store, article(), T0, notice, root=tmp_path, interpreted_at=T1)
    assert reviewed.collect_primary_notice_state(store, {'sourceStatus': 'MISSING'}, interpreted_at=T2) == []
    assert not any(row['recordKind'] == 'CANCELLATION' for row in store.feedback('evidence'))
    store.close()


@pytest.mark.parametrize('failed_stage',['refresh','primary_collection'])
def test_existing_worker_checks_report_when_primary_notice_stage_fails(tmp_path,monkeypatch,failed_stage):
    """One source failure cannot suppress the other source's retained check."""
    from types import SimpleNamespace
    from src.portwatch_os.learning import intelligence_reconciliation as collector
    from src.portwatch_os.intelligence import navigation_restrictions
    from backend.app.services import cache_service
    monkeypatch.setattr(collector,'DB',tmp_path/'public.db')
    monkeypatch.setattr(collector.requests,'get',lambda *a,**k:SimpleNamespace(content=b'fixture',raise_for_status=lambda:None))
    monkeypatch.setattr(collector,'collect_fx',lambda *a,**k:[])
    def unavailable(*a,**k):raise ValueError('Synthetic primary failure')
    notice={'noticeRef':reviewed.REFERENCE,'sourceStatus':'UNAVAILABLE'}
    monkeypatch.setattr(operational_notices,'refresh',unavailable if failed_stage=='refresh' else lambda:notice)
    monkeypatch.setattr(collector,'collect_notice',unavailable if failed_stage=='primary_collection' else lambda *a:[])
    calls=[]
    def report_check(store,primary):
        calls.append(primary)
        return {'status':'RETAINED','reason':None,'claimsCollected':0}
    monkeypatch.setattr(reviewed,'refresh_gac_eastham',report_check)
    monkeypatch.setattr(navigation_restrictions,'refresh_all',lambda:{'sourceStatus':'CURRENT','notices':[]})
    monkeypatch.setattr(cache_service,'get_news_bundle',lambda:{'events':[]})
    monkeypatch.setattr(collector,'collect_news_product',lambda *a:None)
    monkeypatch.setattr(feedback,'reconcile',lambda *a:(0,0))
    monkeypatch.setattr(feedback,'reliability_version',lambda *a:{'id':'fixture-neutral'})
    result=collector.run_once()
    assert calls==[{} if failed_stage=='refresh' else notice]
    assert result['reviewedNews']['status']=='RETAINED'
    assert [row['source'] for row in result['failures']]==['Peel Ports']
