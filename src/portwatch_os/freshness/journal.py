"""Persistent attempt history and retry state. API readers never fetch providers."""
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


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
        payload['detail'] = {}
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
            db.execute('DELETE FROM refresh_attempts WHERE finished < ?', (cutoff,))

    def load(self, artifact):
        with self.connect() as db:
            state = db.execute('SELECT last_good,next_attempt,attempts,last_result FROM refresh_state WHERE artifact=?', (artifact,)).fetchone()
            history = db.execute('SELECT result FROM refresh_attempts WHERE artifact=? ORDER BY id DESC LIMIT 12', (artifact,)).fetchall()
            if not history and state and state[3]:
                history = [(state[3],)]
        return state, [json.loads(row[0]) for row in reversed(history)]

    def metrics(self, artifact, now):
        since = (now - timedelta(days=7)).astimezone(timezone.utc).isoformat()
        until = now.astimezone(timezone.utc).isoformat()
        with self.connect() as db:
            rows = db.execute('SELECT ok,skipped,result FROM refresh_attempts WHERE artifact=? AND finished>=? AND finished<=? ORDER BY id DESC',
                              (artifact, since, until)).fetchall()
            state = db.execute('SELECT last_error FROM refresh_state WHERE artifact=?', (artifact,)).fetchone()
        attempted = [row for row in rows if not row[1]]
        errors = [json.loads(row[2]) for row in rows if not row[0]]
        if not errors and state and state[0]:
            retained = json.loads(state[0])
            if datetime.fromisoformat(retained['finishedAt']) <= now:
                errors = [retained]
        return {'attempts7d': len(attempted),
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
