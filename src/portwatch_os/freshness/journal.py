"""Persistent attempt history and retry state. API readers never fetch providers."""
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median


def safe_error(error):
    message = f'{type(error).__name__}: {error}'
    from src.utils.settings import Settings, get_settings
    settings = get_settings()
    for name, field in Settings.model_fields.items():
        value = getattr(settings, name)
        if field.exclude and value:
            message = message.replace(value, '[redacted]')
    return re.sub(r'(https?://[^\s?]+)\?[^\s]+', r'\1?[redacted]', message)[:1200]


class FreshnessJournal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS refresh_attempts (
                    id INTEGER PRIMARY KEY, artifact TEXT NOT NULL, finished TEXT NOT NULL,
                    ok INTEGER NOT NULL, skipped INTEGER NOT NULL, result TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS refresh_history ON refresh_attempts(artifact, finished);
                CREATE TABLE IF NOT EXISTS refresh_state (
                    artifact TEXT PRIMARY KEY, last_good TEXT, next_attempt TEXT, attempts INTEGER NOT NULL,
                    last_result TEXT, last_error TEXT);
            ''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(refresh_state)')}
            for name in ('last_result', 'last_error'):
                if name not in columns:
                    db.execute(f'ALTER TABLE refresh_state ADD COLUMN {name} TEXT')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute('PRAGMA busy_timeout=10000')
            with db:
                yield db
        finally:
            db.close()

    def save(self, result, next_attempt, attempts):
        payload = result.to_dict()
        # Avoid persisting large provider documents in the attempt journal.
        payload['detail'] = {
            key: result.detail[key] for key in ('sourceObservedAt', 'sourceReceivedAt')
            if result.artifact == 'port_forecast' and key in result.detail
        }
        rendered = json.dumps(payload)
        finished = result.finished_at.astimezone(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute('INSERT INTO refresh_attempts(artifact,finished,ok,skipped,result) VALUES(?,?,?,?,?)',
                       (result.artifact, finished, result.ok, result.skipped, rendered))
            old = db.execute('SELECT last_good,last_error FROM refresh_state WHERE artifact=?', (result.artifact,)).fetchone()
            good = rendered if result.ok and not result.skipped else old[0] if old else None
            error = rendered if not result.ok else old[1] if old else None
            db.execute('INSERT OR REPLACE INTO refresh_state(artifact,last_good,next_attempt,attempts,last_result,last_error) VALUES(?,?,?,?,?,?)',
                       (result.artifact, good, next_attempt.isoformat() if next_attempt else None, attempts, rendered, error))
            cutoff = (result.finished_at - timedelta(days=7)).astimezone(timezone.utc).isoformat()
            from .publication_lag import HISTORY_WINDOW
            history_cutoff = (result.finished_at - HISTORY_WINDOW).astimezone(timezone.utc).isoformat()
            db.execute("""DELETE FROM refresh_attempts WHERE finished < ? OR
                       (finished < ? AND (artifact NOT IN ('port_forecast', 'port_activity_collection')
                                          OR ok != 1 OR skipped = 1))""",
                       (history_cutoff, cutoff))

    def record_port_activity_collection(self, observed_at, received_at):
        received = received_at.astimezone(timezone.utc).isoformat()
        result = json.dumps({"detail": {"sourceObservedAt": observed_at.isoformat(),
                                        "sourceReceivedAt": received}})
        with self.connect() as db:
            db.execute("""INSERT INTO refresh_attempts(artifact,finished,ok,skipped,result)
                          VALUES('port_activity_collection',?,1,0,?)""", (received, result))

    def publication_receipts(self):
        with self.connect() as db:
            rows = db.execute("""SELECT result FROM refresh_attempts
                                WHERE artifact IN ('port_activity_collection', 'port_forecast')
                                  AND ok=1 AND skipped=0""").fetchall()
        details = [json.loads(row[0]).get('detail', {}) for row in rows]
        return [(row['sourceObservedAt'], row['sourceReceivedAt'])
                for row in details if row.get('sourceObservedAt') and row.get('sourceReceivedAt')]

    def load(self, artifact):
        with self.connect() as db:
            state = db.execute('SELECT last_good,next_attempt,attempts,last_result FROM refresh_state WHERE artifact=?', (artifact,)).fetchone()
            history = db.execute('SELECT result FROM refresh_attempts WHERE artifact=? ORDER BY id DESC LIMIT 12', (artifact,)).fetchall()
            if not history and state and state[3]:
                history = [(state[3],)]
        return state, [json.loads(row[0]) for row in reversed(history)]

    def recent_outcomes(self, artifact, now, *, hours):
        since = (now - timedelta(hours=hours)).astimezone(timezone.utc).isoformat()
        until = now.astimezone(timezone.utc).isoformat()
        with self.connect() as db:
            rows = db.execute(
                "SELECT finished,ok,result FROM refresh_attempts "
                "WHERE artifact=? AND skipped=0 AND finished>=? AND finished<=? ORDER BY finished",
                (artifact, since, until),
            ).fetchall()
        count = len(rows)
        successes = sum(bool(row[1]) for row in rows)
        return {"attempts": count, "successes": successes,
                "rate": successes / count if count else None,
                "http429": sum(not row[1] and "HTTP 429" in (json.loads(row[2]).get("error") or "") for row in rows),
                "firstFinishedAt": rows[0][0] if count else None,
                "lastFinishedAt": rows[-1][0] if count else None}

    def metrics(self, artifact, now):
        since = (now - timedelta(days=7)).astimezone(timezone.utc).isoformat()
        until = now.astimezone(timezone.utc).isoformat()
        with self.connect() as db:
            rows = db.execute('SELECT ok,skipped,result FROM refresh_attempts WHERE artifact=? AND finished>=? AND finished<=? ORDER BY id DESC',
                              (artifact, since, until)).fetchall()
            state = db.execute('SELECT last_error FROM refresh_state WHERE artifact=?', (artifact,)).fetchone()
        attempted = [row for row in rows if not row[1]]
        lags = []
        for row in attempted:
            sample = json.loads(row[2])
            if row[0] and sample.get('observedAt'):
                lags.append(max(0, (datetime.fromisoformat(sample['finishedAt']) - datetime.fromisoformat(sample['observedAt'])).total_seconds()))
        errors = [json.loads(row[2]) for row in rows if not row[0]]
        if not errors and state and state[0]:
            retained = json.loads(state[0])
            if datetime.fromisoformat(retained['finishedAt']) <= now:
                errors = [retained]
        return {'attempts7d': len(attempted),
                'medianLagSeconds': median(lags) if lags else None,
                'successRate7d': sum(bool(row[0]) for row in attempted) / len(attempted) if attempted else None,
                'lastError': errors[0]['error'] if errors else None,
                'lastErrorAt': errors[0]['finishedAt'] if errors else None}


def result_from_dict(value):
    from .job import RefreshResult
    return RefreshResult(artifact=value['artifact'], ok=value['ok'],
                         started_at=datetime.fromisoformat(value['startedAt']),
                         finished_at=datetime.fromisoformat(value['finishedAt']),
                         attempt=value['attempt'], reason=value['reason'],
                         changed=value.get('changed', False), skipped=value.get('skipped', False),
                         observed_at=datetime.fromisoformat(value['observedAt']) if value.get('observedAt') else None,
                         error=value.get('error'), detail=value.get('detail', {}))
