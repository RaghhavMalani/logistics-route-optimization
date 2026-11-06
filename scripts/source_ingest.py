"""Run or inspect an isolated 48-hour source trial."""

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timedelta
from functools import partial
import json
import logging
import re
from statistics import median

from src.portwatch_os.clock import wall_now
from src.portwatch_os.fabric.products import ProductCatalogue
from src.portwatch_os.freshness.source_snapshots import configured_store, utc
from src.portwatch_os.freshness.source_worker import SourceJob, collect_due, run_worker
from src.portwatch_os.freshness.trial_collectors import ecb_rates, gdelt_discovery, nho_warning_metadata
from src.portwatch_os.freshness.candidate_weather import weather_trial
from src.portwatch_os.freshness.gdelt_bigquery import collect as gdelt_bigquery

TRIAL = timedelta(hours=48)
COLLECTORS = {
    "gdelt-bigquery-gkg": (gdelt_bigquery, timedelta(hours=6)),
    "open-meteo-marine-extended": (partial(weather_trial, 'marine'), timedelta(hours=6)),
    "open-meteo-ensemble": (partial(weather_trial, 'ensemble'), timedelta(hours=6)),
    "nho-navarea-viii": (nho_warning_metadata, timedelta(hours=6)),
    "frankfurter-ecb-fx": (partial(ecb_rates, "https://api.frankfurter.dev/v2/providers/ecb/rates"), timedelta(days=1)),
    "gdelt-events": (gdelt_discovery, timedelta(hours=3)),
}


def report(store, product, scope, start, now, cadence):
    end = start + TRIAL
    through = min(end, now)
    attempts = store.attempts(scope, product, since=start, until=through)
    samples = store.snapshots(scope, product, since=start, until=through)
    lags = [item.lag_seconds for item in attempts if item.error is None and item.lag_seconds is not None]
    coverage = Counter(key for sample in samples for key in sample.payload["coverage"])
    pairs = {key: len({sample.payload["coverage"][key] for sample in samples
                      if key in sample.payload["coverage"]}) for key in coverage} if product == "frankfurter-ecb-fx" else None
    timeline = [start, *(item.finished_at for item in reversed(attempts)), through]
    longest_gap = max((b - a).total_seconds() for a, b in zip(timeline, timeline[1:]))
    return {
        "product": product, "trial": scope, "startedAt": start.isoformat(),
        "endsAt": end.isoformat(), "reportedAt": now.isoformat(),
        "phase": "pending review" if now >= end else "in progress",
        "cadenceSeconds": cadence.total_seconds(),
        "attempts": len(attempts), "successfulSnapshots": len(samples),
        "successRate": len(samples) / len(attempts) if attempts else None,
        "longestAttemptGapSeconds": longest_gap,
        "medianLagSeconds": median(lags) if lags else None,
        "lagBasis": samples[0].payload["precision"] if samples else None,
        "distinctCoverageKeys": len(coverage),
        "coveragePerSnapshot": [len(sample.payload["coverage"]) for sample in reversed(samples)],
        "distinctReferenceDatesByPair": pairs,
        "failureKinds": Counter(item.error for item in attempts if item.error),
        "decision": "pending",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "probe", "report"])
    parser.add_argument("product", choices=COLLECTORS)
    parser.add_argument("--trial", required=True, help="Unique trial name, reused when resuming")
    parser.add_argument("--start", required=True, help="Trial start with UTC offset, reused when resuming")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", args.trial):
        parser.error("Trial names use lowercase letters, digits and hyphens")
    try:
        start = utc(datetime.fromisoformat(args.start))
    except ValueError:
        parser.error("Trial start must be an ISO timestamp with offset")
    now = wall_now()
    if start > now or (args.action != "report" and start + TRIAL <= now):
        parser.error("Collection requires a current 48-hour window")
    scope = "trial-" + args.trial
    fetch, cadence = COLLECTORS[args.product]
    _, product = ProductCatalogue().product(args.product)
    store = configured_store()
    if store is None:
        parser.error("Set PORTWATCH_SOURCE_SNAPSHOT_URL for an isolated trial store")
    if args.action != "report":
        store.initialize()
        job = SourceJob(product, fetch, cadence, scope, trial_permitted=True)
        if args.action == "run":
            asyncio.run(run_worker(store, [job], until=start + TRIAL))
        else:
            collect_due(store, job)
    print(json.dumps(report(store, args.product, scope, start, wall_now(), cadence), indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
