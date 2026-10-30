"""Synthetic authority-shape fixtures test software, not current aid conditions."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import copy
import hashlib
import json
from unittest.mock import Mock

import pytest
import requests

from src.portwatch_os.intelligence import indian_notices as n, indian_review as review

AT = datetime(2026, 10, 30, 8, tzinfo=timezone.utc)
URL = 'https://www.hydrobharat.gov.in/documents/d/guest/synthetic-test'
ID = n.FAMILY + ':609/25'


def pages(wording='', day='30 OCT 2026'):
    return [f'WARNINGS IN FORCE AS ON {day}\n031001Z/JUL 25\nNAVAREA VIII - 609/25\nINDIA EAST COAST – PARADIP\nDGPS TRANSMISSION FROM PARADIP LT (20-15.32N 086-39.38E) OFF AIR. {wording}']


def retain(tmp_path, monkeypatch, *, at=AT, wording='', day='30 OCT 2026', raw=None):
    text = pages(wording, day)
    monkeypatch.setattr(n, 'parse', lambda raw: n.parse_pages(text))
    return n.retain(raw or ('SYNTHETIC '+str(text)).encode(), document_url=URL, received_at=at.isoformat(), root=tmp_path)


def test_product_date_issue_precision_mapping_and_no_calculation():
    data=n.parse_pages(pages())
    row=data['notices'][0]
    assert data['productAsOfDate']=='2026-10-30'
    assert row['providerIssueAt']=='2025-07-03T10:01:00+00:00' and row['publishedAt'] is None
    assert row['coordinates']['lat']==pytest.approx(20.25533333333333)
    assert row['areaId']==n.AREA and row['portCodes']==['INPRT']
    assert row['extractionStatus']=='CONTEXT_METADATA' and not row['calculationSupported']
    assert row['windows']==[] and 'not a port boundary' in row['coordinates']['basis']


def test_cross_page_notice_and_unsupported_duplicates_remain_inspectable():
    text=pages();text.append('CONTINUED SOURCE TEXT\n031005Z/JUL 25\nNAVAREA VIII - 610/25\nUNREVIEWED AREA EXERCISE')
    rows=n.parse_pages(text)['notices']
    assert rows[0]['documentPages']==[1,2] and rows[1]['extractionStatus']=='UNSUPPORTED'
    duplicate=n.parse_pages(pages()+pages('CONFLICTING WORDING'))['notices'][0]
    assert duplicate['status']=='AMBIGUOUS' and duplicate['extractionStatus']=='UNSUPPORTED'


@pytest.mark.parametrize('text', [[],['No explicit product date'],['WARNINGS IN FORCE AS ON 30 OCT 2026\nNo provider headings']])
def test_malformed_product_fails_closed(text):
    with pytest.raises(ValueError):n.parse_pages(text)


def test_fresh_receipt_does_not_refresh_old_product(tmp_path, monkeypatch):
    retain(tmp_path,monkeypatch,day='07 JUL 2025')
    row=n.retained(root=tmp_path,as_of=AT)['notices'][0]
    assert row['sourceStatus']=='HISTORICAL_PRODUCT' and row['productAgeDays']>400
    assert 'sourceText' not in row and not row['originalDownloadAvailable']


def test_unchanged_revision_dedup_changed_revision_and_reversion(tmp_path,monkeypatch):
    first=retain(tmp_path,monkeypatch)['notices'][0]
    again=retain(tmp_path,monkeypatch,at=AT+timedelta(minutes=1))['notices'][0]
    assert again['revisionId']==first['revisionId'] and again['availableAt']==first['availableAt']
    changed=retain(tmp_path,monkeypatch,at=AT+timedelta(minutes=2),wording='REVISED')['notices'][0]
    reverted=retain(tmp_path,monkeypatch,at=AT+timedelta(minutes=3))['notices'][0]
    assert changed['previousRevisionId']==first['revisionId']
    assert reverted['previousRevisionId']==changed['revisionId'] and reverted['revisionId']!=first['revisionId']
    historical=n.retained(root=tmp_path,as_of=AT+timedelta(seconds=90))['notices'][0]
    assert historical['revisionId']==first['revisionId'] and historical['checkedAt']==again['checkedAt']
    assert n.retained(root=tmp_path,as_of=AT-timedelta(seconds=1))['notices']==[]


def test_parser_version_new_availability_and_original_hash(tmp_path,monkeypatch):
    first=retain(tmp_path,monkeypatch)['notices'][0]
    raw=(tmp_path/(first['responseSha256']+'.response')).read_bytes()
    revised=n.retain(raw,document_url=URL,received_at=(AT+timedelta(minutes=1)).isoformat(),root=tmp_path,parser_version='synthetic-parser-v2')['notices'][0]
    assert revised['revisionId']!=first['revisionId'] and revised['sourceFirstReceivedAt']==first['availableAt']
    assert revised['extractionVersion']=='synthetic-parser-v2'
    assert hashlib.sha256(raw).hexdigest()==revised['responseSha256']


def test_explicit_cancellation_deduplicates_and_does_not_establish_clearance(tmp_path,monkeypatch):
    first=retain(tmp_path,monkeypatch)['notices'][0]
    text=pages()+['301000Z/OCT 26\nNAVAREA VIII - 701/26\nCANCEL NAVAREA VIII 609/25']
    monkeypatch.setattr(n,'parse',lambda _:n.parse_pages(text))
    second=n.retain(b'SYNTHETIC CANCELLATION',document_url=URL,received_at=(AT+timedelta(minutes=1)).isoformat(),root=tmp_path)['notices'][0]
    third=n.retain(b'SYNTHETIC CANCELLATION',document_url=URL,received_at=(AT+timedelta(minutes=2)).isoformat(),root=tmp_path)['notices'][0]
    assert second['status']=='SOURCE_NOTICE_CANCELLED' and 'clearance is not established' in second['reason']
    assert second['previousRevisionId']==first['revisionId'] and third['revisionId']==second['revisionId']


def test_omission_is_not_cancellation(tmp_path,monkeypatch):
    retain(tmp_path,monkeypatch)
    monkeypatch.setattr(n,'parse',lambda _:n.parse_pages(['WARNINGS IN FORCE AS ON 30 OCT 2026\n301000Z/OCT 26\nNAVAREA VIII - 701/26\nUNRELATED']))
    result=n.retain(b'SYNTHETIC OMISSION',document_url=URL,received_at=(AT+timedelta(minutes=1)).isoformat(),root=tmp_path)
    row=next(r for r in result['notices'] if r['noticeId']==ID)
    assert row['status']=='NOT_LISTED' and 'no explicit cancellation' in row['reason']


@pytest.mark.parametrize('error',[requests.HTTPError('403'),requests.Timeout('offline'),ValueError('malformed')])
def test_failure_retains_last_good_and_receipt(error,tmp_path,monkeypatch):
    first=retain(tmp_path,monkeypatch)['notices'][0]
    monkeypatch.setattr(n,'wall_now',lambda:AT+timedelta(minutes=1))
    fetch=Mock(side_effect=error)
    result=n.refresh(root=tmp_path,fetch=fetch,force=True)
    assert result['sourceStatus']=='UNAVAILABLE' and result['notices'][0]['revisionId']==first['revisionId']
    public=n.retained(root=tmp_path,as_of=AT+timedelta(minutes=2))['notices'][0]
    assert public['sourceStatus']=='UNAVAILABLE' and public['lastSuccessfulReceiptAt']==AT.isoformat()
    assert fetch.call_count==(2 if isinstance(error,requests.Timeout) else 1)


@pytest.mark.parametrize('url',['http://www.hydrobharat.gov.in/documents/a','https://other.example/documents/a','https://www.hydrobharat.gov.in:bad/documents/a','https://user@www.hydrobharat.gov.in/documents/a'])
def test_untrusted_document_rejected(url,tmp_path):
    with pytest.raises(ValueError):n.retain(b'ignored',document_url=url,received_at=AT.isoformat(),root=tmp_path)
    assert list(tmp_path.iterdir())==[]


def test_query_requires_timezone_and_get_is_read_only(tmp_path,monkeypatch):
    retain(tmp_path,monkeypatch)
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    monkeypatch.setattr(n.requests,'get',Mock(side_effect=AssertionError('GET must not collect')))
    n.retained(root=tmp_path,as_of=AT+timedelta(minutes=1))
    assert before=={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError):n.retained(root=tmp_path,as_of='2026-10-30T08:00:00')


def vessel():
    plan={'id':'operator-plan','vesselId':'PWD-001','sourceFamily':n.FAMILY,'areaId':n.AREA,'route':[n.AREA,'INPRT'],'passageAt':(AT+timedelta(hours=4)).isoformat(),'operationalEpisode':{'id':'call-1'}}
    return {'id':'PWD-001','name':'Synthetic vessel','portCode':'INPRT','operationalEpisode':{'id':'call-1'},'declaredPassages':{n.AREA:plan}}


def test_destination_is_only_possible_and_exact_declaration_matches():
    notice=n.parse_pages(pages())['notices'][0];notice['sourceStatus']='CURRENT_PRODUCT_DATE'
    v=vessel();assert review.exposure(notice,v,AT)['status']=='DECLARED_REVIEW_CONTEXT'
    v['declaredPassages']={};assert review.exposure(notice,v,AT)['status']=='POSSIBLE_EXPOSURE'
    v['portCode']='INNSA';assert review.exposure(notice,v,AT)['status']=='NO_DEMONSTRATED_EXPOSURE'


def test_binding_revision_changes_and_expiry_do_not_mutate_original(tmp_path,monkeypatch):
    first=retain(tmp_path,monkeypatch)['notices'][0]
    monkeypatch.setattr(n,'root_path',lambda:tmp_path)
    v=vessel();scoped=SimpleNamespace(world={'fleet':[v]})
    selection=[{'noticeId':ID,'revisionId':first['revisionId'],'acknowledged':True}]
    bindings=review.freeze(scoped,v['id'],selection,at=AT)
    original=copy.deepcopy(bindings)
    assert bindings[0]['numericalEffect'] is None
    assert review.assess(bindings,scoped.world,n.retained(root=tmp_path,as_of=AT)['notices'],at=AT)==[]
    retain(tmp_path,monkeypatch,wording='REVISED',at=AT+timedelta(minutes=1))
    findings=review.assess(bindings,scoped.world,n.retained(root=tmp_path,as_of=AT+timedelta(minutes=2))['notices'],at=AT+timedelta(minutes=2))
    assert findings[0]['code']=='INDIAN_SOURCE_REVISION_CHANGED'
    assert any(c['field']=='semanticId' for c in findings[0]['changes']) and bindings==original
    v['declaredPassages'][n.AREA]['id']='changed-plan'
    assert review.assess(bindings,scoped.world,[],at=AT)[0]['code']=='INDIAN_DECLARATION_CHANGED'


def test_historical_context_cannot_be_consumed(tmp_path,monkeypatch):
    first=retain(tmp_path,monkeypatch,day='07 JUL 2025')['notices'][0]
    monkeypatch.setattr(n,'root_path',lambda:tmp_path)
    with pytest.raises(ValueError,match='Historical'):
        review.freeze(SimpleNamespace(world={'fleet':[vessel()]}),'PWD-001',[{'noticeId':ID,'revisionId':first['revisionId'],'acknowledged':True}],at=AT)


def test_malformed_coordinates_never_qualify_context():
    text=pages()[0].replace('20-15.32N 086-39.38E','90-15.32N 180-39.38E')
    row=n.parse_pages([text])['notices'][0]
    assert row['coordinates'] is None and row['extractionStatus']=='UNSUPPORTED'


def test_unconsumed_sources_do_not_duplicate_calls_or_change_workflow():
    v=vessel();notice=n.parse_pages(pages())['notices'][0]
    notices=[{**notice,'noticeId':n.FAMILY+':'+str(i)+'/26','revisionId':str(i),'sourceStatus':'CURRENT_PRODUCT_DATE'} for i in range(10)]
    row={'vessel':{'id':v['id']},'workflow':{'stage':'AWAITING_VESSEL','nextRole':'VESSEL_OPERATOR','completed':False},'currentPlan':{},'reasons':[],'primaryCategory':'WAITING_OTHER_ROLE'}
    data={'rows':[row]};original=copy.deepcopy(row['workflow'])
    review.annotate_worklist(data,{'fleet':[v]},[],notices,at=AT)
    assert len(data['rows'])==1 and len(row['sourceReviews'])==10
    assert data['reasonCounts']['INDIAN_SOURCE_REVIEW_REQUIRED']==1
    assert row['workflow']==original and row['primaryCategory']=='WAITING_OTHER_ROLE'
    row['workflow']['completed']=True
    review.annotate_worklist(data,{'fleet':[v]},[],notices,at=AT)
    assert row['sourceReviews']==[]
