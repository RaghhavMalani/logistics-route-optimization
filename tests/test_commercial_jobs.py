"""Bounded CPU/cancellation ownership; no provider or operational accuracy claim."""
from threading import Event,Thread
from uuid import uuid4
import pytest
from src.portwatch_os.decision import commercial_jobs as jobs


def test_one_slot_cancel_ownership_and_release():
    entered,release=Event(),Event();job_id=str(uuid4());errors=[]
    def run():
        try:
            with jobs.study('visitor-a',job_id) as job:
                entered.set();release.wait(2);job.checkpoint()
        except jobs.Cancelled: errors.append('cancelled')
    thread=Thread(target=run);thread.start();assert entered.wait(2)
    try:
        with pytest.raises(jobs.Busy):
            with jobs.study('visitor-b'): pass
        with pytest.raises(jobs.UnknownJob): jobs.cancel('visitor-b',job_id)
        assert jobs.cancel('visitor-a',job_id)['status']=='CANCELLATION_REQUESTED'
    finally: release.set();thread.join(2)
    assert errors==['cancelled'] and jobs.inspect('visitor-a',job_id)['status']=='CANCELLED'
    with jobs.study('visitor-b') as job: job.checkpoint()
    assert job.status=='COMPLETED'


def test_monotonic_budget_and_reused_job_refused(monkeypatch):
    now=[100.]
    monkeypatch.setattr(jobs,'monotonic',lambda:now[0])
    # The dataclass default factory is the real timer; set the control start
    # explicitly to isolate this test from the clock/replay mechanisms.
    job_id=str(uuid4())
    with pytest.raises(jobs.BudgetExceeded):
        with jobs.study('visitor',job_id,budget=1) as job:
            job.started=100.;now[0]=101.01;job.checkpoint()
    assert jobs.inspect('visitor',job_id)['status']=='BUDGET_EXCEEDED'
    with pytest.raises(jobs.Busy):
        with jobs.study('visitor',job_id): pass
    with jobs.study('visitor') as job: job.started=now[0];job.checkpoint()
