"""Partition-filtered discovery, fail-closed with a durable daily scan budget."""
from datetime import timedelta
import math
import sqlite3
from urllib.parse import urlsplit

from src.portwatch_os.clock import wall_now
from src.portwatch_os.freshness.source_snapshots import Snapshot
from src.utils.settings import get_settings

SQL = '''SELECT DATE, DocumentIdentifier
FROM `gdelt-bq.gdeltv2.gkg_partitioned`
WHERE _PARTITIONTIME >= TIMESTAMP_TRUNC(@start, DAY)
  AND _PARTITIONTIME < TIMESTAMP_ADD(TIMESTAMP_TRUNC(@end, DAY), INTERVAL 1 DAY)
  AND PARSE_TIMESTAMP('%Y%m%d%H%M%S', CAST(DATE AS STRING)) BETWEEN @start AND @end
  AND REGEXP_CONTAINS(LOWER(V2Themes), r'(maritime|shipping|port)')
  AND REGEXP_CONTAINS(LOWER(V2Locations), r'(india|mumbai|chennai|paradip|mundra)')
ORDER BY DATE DESC LIMIT 100'''


def reserve(path, project, day, amount, cap):
    with sqlite3.connect(path, timeout=10) as db:
        db.execute('CREATE TABLE IF NOT EXISTS scan_budget (project TEXT, day TEXT, reserved INTEGER, PRIMARY KEY(project,day))')
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT reserved FROM scan_budget WHERE project=? AND day=?', (project, day)).fetchone()
        used = old[0] if old else 0
        if amount <= 0 or used + amount > cap:
            raise ValueError('BigQuery daily scan budget exhausted; no billed query submitted')
        db.execute('INSERT OR REPLACE INTO scan_budget VALUES(?,?,?)', (project, day, used + amount))


def collect():
    settings = get_settings()
    project = settings.PORTWATCH_BIGQUERY_PROJECT
    cap = int(settings.PORTWATCH_BIGQUERY_DAILY_BYTE_CAP or 0)
    if not project or cap <= 0:
        raise ValueError('BigQuery requires explicit project, credentials and daily byte cap')
    from google.cloud import bigquery
    from src.utils.config import STATE_DIR
    now = wall_now()  # wall-clock: query and billing windows describe actual elapsed collection.
    parameters = [bigquery.ScalarQueryParameter('start', 'TIMESTAMP', now-timedelta(hours=24)),
                  bigquery.ScalarQueryParameter('end', 'TIMESTAMP', now)]
    client = bigquery.Client(project=project, location='US')
    dry = client.query(SQL, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False,
                       query_parameters=parameters), timeout=20)
    # Reserve a rounded upper bound, including BigQuery's minimum billing unit.
    amount = max(10*1024**2, math.ceil(int(dry.total_bytes_processed)/1024**2)*1024**2)
    path = STATE_DIR / 'live/bigquery-budget.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    reserve(path, project, now.date().isoformat(), amount, cap)
    job = client.query(SQL, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=amount,
                       query_parameters=parameters), timeout=20)
    links = {}
    from datetime import datetime, timezone
    for row in job.result(timeout=60, max_results=100):
        url = urlsplit(row['DocumentIdentifier'])
        seen = datetime.strptime(str(row['DATE']), '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        if url.scheme in ('http', 'https') and url.hostname and not url.username and seen <= now:
            links[url.geturl()] = seen.isoformat()
    return Snapshot({'attribution': 'GDELT Project, https://www.gdeltproject.org/',
                     'precision': 'INDEX_SEEN_TIME', 'coverage': links, 'reservedBytes': amount,
                     'billedBytes': job.total_bytes_billed, 'scope': 'Indian maritime discovery, not validated incidents'},
                    max((datetime.fromisoformat(value) for value in links.values()), default=None))
