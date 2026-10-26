"""Collector result availability is its completion, never its start clock."""
from datetime import datetime
from types import SimpleNamespace

from backend.app.routes import shared_feedback as routes
from src.portwatch_os.intelligence import navigation_restrictions, operational_notices
from src.portwatch_os.learning import intelligence_reconciliation as collector
from src.portwatch_os.learning import reviewed_news, shared_feedback as feedback
from src.portwatch_os.ledger.store import SqliteLedgerStore


START='2026-10-25T10:00:00+00:00'
CUTOFF='2026-10-25T10:01:00+00:00'
FINISH='2026-10-25T10:02:00+00:00'


def test_legacy_run_with_later_nested_fetch_does_not_leak_completed_results(tmp_path):
    store=SqliteLedgerStore(tmp_path/'public.db')
    store.append_feedback('run',{'id':'older','ranAt':'2026-10-25T09:00:00+00:00','status':'COLLECTING'})
    later={'id':'legacy-run','ranAt':START,'status':'COLLECTING','resolved':3,
        'reviewedNews':{'status':'UNAVAILABLE','checkedAt':START,'receivedAt':FINISH,
            'reason':'Fixture result became known after the requested cutoff'},
        'navigation':{'checkedAt':CUTOFF}}
    store.append_feedback('run',later)
    assert routes.collector_projection(store,CUTOFF)['id']=='older'
    assert routes.collector_projection(store,FINISH)==later
    store.close()


def test_worker_result_is_visible_only_after_recorded_completion(tmp_path,monkeypatch):
    from backend.app.services import cache_service
    monkeypatch.setattr(collector,'DB',tmp_path/'public.db')
    clock=[START]
    monkeypatch.setattr(collector,'wall_now',lambda:datetime.fromisoformat(clock[0]))
    monkeypatch.setattr(collector.requests,'get',lambda *a,**k:SimpleNamespace(content=b'fixture',raise_for_status=lambda:None))
    monkeypatch.setattr(collector,'collect_fx',lambda *a,**k:[])
    monkeypatch.setattr(operational_notices,'refresh',lambda:{})
    monkeypatch.setattr(collector,'collect_notice',lambda *a:[])
    monkeypatch.setattr(reviewed_news,'refresh_gac_eastham',lambda *a:{'status':'RETAINED','checkedAt':START})
    monkeypatch.setattr(navigation_restrictions,'refresh_all',lambda:{'sourceStatus':'CURRENT','notices':[]})
    monkeypatch.setattr(cache_service,'get_news_bundle',lambda:{'events':[]})
    monkeypatch.setattr(collector,'collect_news_product',lambda *a:None)
    def reconcile(*a):
        clock[0]=FINISH
        return 3,0
    monkeypatch.setattr(feedback,'reconcile',reconcile)
    monkeypatch.setattr(feedback,'reliability_version',lambda *a:{'id':'fixture-neutral'})
    result=collector.run_once()
    assert result['ranAt']==START
    assert result['completedAt']==result['firstAvailableAt']==FINISH
    store=SqliteLedgerStore(collector.DB)
    assert routes.collector_projection(store,CUTOFF)=={'status':'COLLECTING','failures':[]}
    assert routes.collector_projection(store,FINISH)['resolved']==3
    store.close()
