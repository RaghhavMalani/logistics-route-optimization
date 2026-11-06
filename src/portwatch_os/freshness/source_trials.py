"""Finite, resumable private trials; publication is a separate review."""
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
    from src.portwatch_os.freshness.source_snapshots import configured_store
    from src.portwatch_os.freshness.source_worker import SourceJob, run_worker
    trial = configured()
    # wall-clock: trial collection stops at its real 48-hour deadline.
    if trial is None or trial['end'] <= wall_now():
        return
    store = configured_store()
    if store is None:
        raise ValueError('An isolated trial snapshot store is required')
    store.initialize()
    catalogue = ProductCatalogue()
    jobs = []
    for key in trial['products']:
        fetch, cadence = COLLECTORS[key]
        _, product = catalogue.product(key)
        jobs.append(SourceJob(product, fetch, cadence, trial['scope'], trial_permitted=True))
    await run_worker(store, jobs, until=trial['end'])
