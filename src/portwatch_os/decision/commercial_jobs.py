"""One bounded commercial study per API process; no worker or collector startup.

The caller journals lifecycle metadata in its visitor-owned ledger. This registry
only controls in-flight CPU work; absence after restart means interrupted.
"""
from contextlib import contextmanager
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import BoundedSemaphore, Event, Lock
from time import monotonic
from uuid import uuid4

MAX_SECONDS = 20.0
_SLOT = BoundedSemaphore(1)
_LOCK = Lock()
_JOBS = OrderedDict()


class Busy(ValueError): pass
class Cancelled(ValueError): pass
class BudgetExceeded(ValueError): pass
class UnknownJob(ValueError): pass


@dataclass
class Control:
    id: str
    owner: str
    budget: float
    started: float = field(default_factory=monotonic)
    stop: Event = field(default_factory=Event)
    status: str = 'RUNNING'
    elapsed: float = 0.0
    progress: dict | None = None

    def checkpoint(self):
        if self.stop.is_set(): raise Cancelled('Study cancelled; earlier retained results are unchanged')
        # Monotonic compute duration, independent of forecast/replay world time.
        if monotonic() - self.started > self.budget: raise BudgetExceeded('Study exceeded its compute budget; reduce the sample/input size')

    def update_progress(self, stage):
        self.checkpoint()
        self.progress = stage

    def public(self):
        return dict(id=self.id,status=self.status,budgetSeconds=self.budget,
                    elapsedSeconds=round(self.elapsed,4),parallelStudies=1,
                    **({"progress": self.progress} if self.progress is not None else {}))


@contextmanager
def study(owner,job_id=None,*,budget=MAX_SECONDS):
    if not _SLOT.acquire(blocking=False): raise Busy('Another study is running; retry later. No new study was accepted')
    control=Control(job_id or str(uuid4()),owner,budget)
    try:
        with _LOCK:
            if control.id in _JOBS: raise Busy('This job identifier has already been used; retain or inspect it before starting another study')
            _JOBS[control.id]=control
            while len(_JOBS)>256: _JOBS.popitem(last=False)
        try:
            yield control
            control.checkpoint()
        except Cancelled:
            control.status='CANCELLED';raise
        except BudgetExceeded:
            control.status='BUDGET_EXCEEDED';raise
        except BaseException:
            control.status='FAILED';raise
        else: control.status='COMPLETED'
        finally: control.elapsed=monotonic()-control.started
    finally: _SLOT.release()


def inspect(owner,job_id):
    with _LOCK:
        control=_JOBS.get(job_id)
        if control is None or control.owner!=owner: raise UnknownJob('No owned in-flight study')
        return control.public()


def cancel(owner,job_id):
    with _LOCK:
        control=_JOBS.get(job_id)
        if control is None or control.owner!=owner: raise UnknownJob('No owned in-flight study')
        if control.status!='RUNNING': return control.public()
        control.stop.set()
        return {**control.public(),'status':'CANCELLATION_REQUESTED'}
