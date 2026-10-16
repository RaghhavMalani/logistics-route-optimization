"""Synthetic source-ledger regressions, not authority or operational accuracy."""
import copy
from datetime import timedelta
from types import SimpleNamespace

from tests.test_navigation_restrictions import NOW, retained, scripted_clock as collection_clock
from src.portwatch_os.learning import intelligence_reconciliation as c, shared_feedback as f
from src.portwatch_os.ledger.store import SqliteLedgerStore


def test_feature_cancellation_and_revision_never_change_another_notice(tmp_path,monkeypatch,collection_clock):
    first=retained(tmp_path,monkeypatch)
    second={**copy.deepcopy(first),'providerNoticeId':'synthetic-second','noticeId':'NAVCEN_MSI:synthetic-second',
        'areaId':'SYNTHETIC_SECOND_ASSET','revisionId':'synthetic-second-version','noticeRef':'Synthetic second authority fixture'}
    store=SqliteLedgerStore(tmp_path/'public.db')
    a=c.collect_navigation(store,first);b=c.collect_navigation(store,second)
    assert len(a)==len(b)==2 and len(store.feedback('claim'))==4
    revised={**second,'revisionId':'synthetic-second-revision','previousRevisionId':second['revisionId'],
        'availableAt':(NOW+timedelta(minutes=1)).isoformat()}
    newer=c.collect_navigation(store,revised)
    assert {r['supersedesClaimId'] for r in newer}=={r['id'] for r in b}
    cancelled={**revised,'revisionId':'synthetic-second-cancel','status':'CANCELLED',
        'availableAt':(NOW+timedelta(minutes=2)).isoformat()}
    c.collect_navigation(store,cancelled)
    assert all(f.current_assessment(store,r)['applicability']=='AS_REPORTED' for r in a)
    assert all(f.current_assessment(store,r)['applicability']=='SUPERSEDED' for r in b+newer)
    assert all(r['cancellationTarget']['effectiveAt'] is None for r in store.feedback('evidence'))
    c.collect_navigation(store,first)
    assert len(store.feedback('claim'))==6
    store.close()


def test_distinct_windows_and_changed_period_retain_source_lineage_without_cross_target_supersession(tmp_path,monkeypatch,collection_clock):
    source=retained(tmp_path,monkeypatch)
    other={**source['windows'][0],'start':'2026-10-18T08:30:00+00:00','end':'2026-10-18T14:15:00+00:00','localDate':'2026-10-18'}
    source['windows'].append(other)
    store=SqliteLedgerStore(tmp_path/'public.db')
    claims=c.collect_navigation(store,source)
    assert len(claims)==4 and len({f.news_vintages.identity(r)['targetId'] for r in claims})==4
    assert all(r['target']['precision']=='MINUTE' for r in claims)
    changed={**source,'revisionId':'new-period-version','previousRevisionId':source['revisionId'],
        'availableAt':(NOW+timedelta(minutes=1)).isoformat(),'windows':[{**other,'end':'2026-10-18T15:15:00+00:00'}]}
    newer=c.collect_navigation(store,changed)
    assert len(newer)==2 and all('supersedesClaimId' not in r and 'supersedesClaimIds' not in r for r in newer)
    assert all(r['sourcePreviousRevisionId']==source['revisionId'] for r in newer)
    assert len(store.feedback('claim'))==6
    # Future-available revisions remain retained but invisible to an earlier as-of view.
    view=f.news_vintages.aggregate(store,NOW.isoformat())
    # Only reported announcement targets enter descriptive source reliability;
    # contingent actual-event hypotheses remain separately inspectable.
    assert view['summary']['claimCount']==2
    assert {r['claimId'] for r in view['claims']}.isdisjoint({r['id'] for r in newer})
    assert len([r for r in store.feedback('claim') if f.instant(r['firstAvailableAt'])<=NOW])==4
    store.close()


def test_explicit_provider_revision_link_survives_reversed_import_and_restart(tmp_path,monkeypatch,collection_clock):
    source=retained(tmp_path,monkeypatch)
    later=(NOW+timedelta(minutes=1)).isoformat()
    revised={**source,'revisionId':'synthetic-revised-original','previousRevisionId':source['revisionId'],
        'availableAt':later,'checkedAt':later,'originalWording':source['originalWording']+' Synthetic reviewed revision marker.'}
    views=[]
    for label,ordered in (('forward',[source,revised]),('reverse',[revised,source])):
        path=tmp_path/(label+'.db');store=SqliteLedgerStore(path)
        for item in ordered: c.collect_navigation(store,item)
        store.close();store=SqliteLedgerStore(path)
        earlier=f.news_vintages.aggregate(store,NOW.isoformat())
        current=f.news_vintages.aggregate(store,(NOW+timedelta(minutes=2)).isoformat())
        assert earlier['summary']['claimCount']==1 and current['summary']['independentTargets']==1
        assert all(row['status']=='ELIGIBLE' for row in current['targets'])
        assert all(len(row['activeClaimIds'])==1 and len(row['supersededClaimIds'])==1 for row in current['targets'])
        views.append([(row['targetId'],row['status'],len(row['activeClaimIds'])) for row in current['targets']])
        store.close()
    assert views[0]==views[1]


def test_missing_unavailable_and_unsupported_products_never_cancel_or_inherit_claims(tmp_path,monkeypatch,collection_clock):
    source=retained(tmp_path,monkeypatch);store=SqliteLedgerStore(tmp_path/'public.db')
    claims=c.collect_navigation(store,source)
    for changes in ({'sourceStatus':'MISSING'},{'sourceStatus':'UNAVAILABLE'},
                    {'extractionStatus':'UNSUPPORTED','calculationSupported':False}):
        assert c.collect_navigation(store,{**source,**changes})==[]
    assert len(store.feedback('claim'))==2 and not store.feedback('evidence')
    assert len(store.feedback('navigation-source-version'))==4
    assert all(f.current_assessment(store,r)['applicability']=='AS_REPORTED' for r in claims)
    store.close()


def test_worker_collects_all_features_and_reports_provider_failure(tmp_path,monkeypatch,collection_clock):
    from src.portwatch_os.intelligence import navigation_restrictions as n, operational_notices
    from backend.app.services import cache_service
    first=retained(tmp_path,monkeypatch)
    second={**copy.deepcopy(first),'providerNoticeId':'synthetic-second','noticeId':'NAVCEN_MSI:synthetic-second',
        'areaId':'SYNTHETIC_SECOND_ASSET','revisionId':'synthetic-second-version','noticeRef':'Synthetic second fixture'}
    monkeypatch.setattr(c,'DB',tmp_path/'worker.db')
    monkeypatch.setattr(c.requests,'get',lambda *args,**kwargs:SimpleNamespace(content=b'DATE,DEXINUS\n2026-10-13,95.0\n',raise_for_status=lambda:None))
    monkeypatch.setattr(operational_notices,'refresh',lambda:{})
    monkeypatch.setattr(cache_service,'get_news_bundle',lambda:{})
    monkeypatch.setattr(n,'refresh_all',lambda:{'sourceStatus':'CURRENT','checkedAt':NOW.isoformat(),'notices':[first,second]})
    def legacy_default(*args,**kwargs):
        raise AssertionError('Rolling worker must not collect only the default fixed feature')
    monkeypatch.setattr(n,'refresh',legacy_default)
    # Keep public source writes within the isolated test root.
    monkeypatch.setattr(c,'collect_fx',lambda *args,**kwargs:[])
    monkeypatch.setattr(c,'collect_news_product',lambda *args,**kwargs:None)
    result=c.run_once()
    assert result['navigation']['discovered']==2 and result['navigation']['claimsCollected']==4
    store=SqliteLedgerStore(c.DB)
    assert len({r['providerNoticeId'] for r in store.feedback('claim')})==2
    store.close()
    monkeypatch.setattr(n,'refresh_all',lambda:{'sourceStatus':'UNAVAILABLE','checkedAt':NOW.isoformat(),
        'reason':'Synthetic provider failure','notices':[{**first,'sourceStatus':'UNAVAILABLE'}]})
    failed=c.run_once()
    assert failed['navigation']['sourceStatus']=='UNAVAILABLE'
    assert any(row['source']=='USCG NAVCEN' and 'Synthetic provider failure' in row['reason'] for row in failed['failures'])
    store=SqliteLedgerStore(c.DB);assert len(store.feedback('claim'))==4;store.close()
