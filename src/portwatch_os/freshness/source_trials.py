"""Run private trials and approved collection under separate snapshot scopes."""
import asyncio
from datetime import datetime, timedelta
from src.utils.settings import get_settings
from src.portwatch_os.clock import wall_now


def configured():
    settings = get_settings()
    if not settings.PORTWATCH_SOURCE_TRIAL_START or not settings.PORTWATCH_SOURCE_TRIAL_PRODUCTS:
        return None
    from scripts.source_ingest import COLLECTORS
    start = datetime.fromisoformat(settings.PORTWATCH_SOURCE_TRIAL_START)
    # wall-clock: forbid a fabricated future trial start, regardless of app replay.
    if start.utcoffset() is None or start > wall_now():
        raise ValueError('Trial start must be an actual elapsed, aware instant')
    products = settings.PORTWATCH_SOURCE_TRIAL_PRODUCTS.split(',')
    if any(key not in COLLECTORS for key in products):
        raise ValueError('Unknown trial product')
    return {'start': start, 'end': start+timedelta(hours=48),
            'scope': 'trial-live-' + start.strftime('%Y%m%d%H%M%S'), 'products': products}


async def run():
    from scripts.source_ingest import COLLECTORS
    from src.portwatch_os.fabric.products import ProductCatalogue
    from src.portwatch_os.freshness.reviewed_sources import PUBLISHED_MAX_AGE, permits_publication
    from src.portwatch_os.freshness.source_snapshots import configured_store
    from src.portwatch_os.freshness.source_worker import SourceJob, run_worker
    from src.portwatch_os.freshness.write_health import record_write
    trial = configured()
    # wall-clock: trial collection stops at its real 48-hour deadline.
    active_trial = trial if trial and trial['end'] > wall_now() else None
    catalogue = ProductCatalogue()
    published = []
    for key in PUBLISHED_MAX_AGE:
        _, product = catalogue.product(key)
        if permits_publication(product):
            fetch, cadence = COLLECTORS[key]
            published.append(SourceJob(product, fetch, cadence, "published", publication_approved=True))
    if not active_trial and not published:
        return
    store = configured_store()
    try:
        if store is None:
            raise ValueError('A source snapshot store is required')
        store.initialize()
    except Exception:
        if published:
            record_write("source-snapshot-store", ok=False)
        raise
    record_write("source-snapshot-store", ok=True)
    workers = []
    if active_trial:
        jobs = []
        for key in active_trial['products']:
            fetch, cadence = COLLECTORS[key]
            _, product = catalogue.product(key)
            jobs.append(SourceJob(product, fetch, cadence, active_trial['scope'], trial_permitted=True))
        workers.append(run_worker(store, jobs, until=active_trial['end']))
    if published:
        workers.append(run_worker(store, published))
    await asyncio.gather(*workers)
