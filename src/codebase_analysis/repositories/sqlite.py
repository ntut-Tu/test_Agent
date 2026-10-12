"""SQLite job persistence for a single Agent instance with a mounted volume."""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from codebase_analysis.models.task import AnalysisJob, BuildRequest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteJobStore:
    """Use short transactions and one connection per operation/thread."""

    def __init__(self, path: Path, max_pending: int = 100) -> None:
        self.path = path
        self.max_pending = max_pending
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, request TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                result TEXT, error TEXT)''')
            db.execute('BEGIN IMMEDIATE')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(jobs)')}
            if 'generation' not in columns:
                db.execute('ALTER TABLE jobs ADD COLUMN generation INTEGER NOT NULL DEFAULT 0')
            if 'execution_mode' not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN execution_mode TEXT NOT NULL DEFAULT 'new'")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _decode(row) -> AnalysisJob | None:
        if row is None:
            return None
        return AnalysisJob(row['id'], BuildRequest(**json.loads(row['request'])),
                           row['status'], row['created_at'], row['updated_at'],
                           json.loads(row['result']) if row['result'] else None, row['error'],
                           row['generation'], row['execution_mode'])

    def submit(self, request: BuildRequest) -> AnalysisJob:
        """Enqueue once, atomically enforcing the active queue limit."""
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM jobs WHERE id=?', (request.identity,)).fetchone()
            if existing:
                return self._decode(existing)
            count = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
            if count >= self.max_pending:
                raise OverflowError('Analysis queue is full')
            now = _now()
            db.execute('INSERT INTO jobs (id,request,status,created_at,updated_at,result,error) VALUES (?,?,?,?,?,?,?)', (
                request.identity, json.dumps(asdict(request)), 'queued', now, now, None, None))
            return self._decode(db.execute('SELECT * FROM jobs WHERE id=?', (request.identity,)).fetchone())

    def get(self, identity: str) -> AnalysisJob | None:
        with self._connect() as db:
            return self._decode(db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone())

    def claim(self) -> AnalysisJob | None:
        """Move the oldest queued record to running in a single transaction."""
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?", (_now(), row['id']))
            return self._decode(db.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone())

    def finish(self, identity: str, result: dict | None, error: str | None) -> None:
        with self._connect() as db:
            db.execute("UPDATE jobs SET status=?,result=?,error=?,updated_at=? WHERE id=? AND status='running'",
                       ('failed' if error else 'succeeded', json.dumps(result) if result is not None else None,
                        error, _now(), identity))

    def retry(self, identity: str) -> AnalysisJob | None:
        """Requeue a failed generation for resume; active/succeeded jobs are unchanged."""
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone()
            if row is not None and row['status'] == 'failed':
                count = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
                if count >= self.max_pending:
                    raise OverflowError('Analysis queue is full')
                db.execute("UPDATE jobs SET status='queued',execution_mode='resume',error=NULL,updated_at=? WHERE id=?", (_now(), identity))
            return self._decode(db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone())

    def restart(self, identity: str) -> AnalysisJob | None:
        """Atomically create a fresh generation for a terminal job.

        Active jobs cannot be restarted. Retained older checkpoints remain
        isolated by generation and are not reused by the new execution.
        """
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone()
            if row is None:
                return None
            if row['status'] in {'queued', 'running'}:
                raise ValueError('Cannot restart an active analysis')
            count = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
            if count >= self.max_pending:
                raise OverflowError('Analysis queue is full')
            db.execute("""UPDATE jobs SET generation=generation+1,execution_mode='new',
                       status='queued',result=NULL,error=NULL,updated_at=? WHERE id=?""", (_now(), identity))
            return self._decode(db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone())

    def recover_running(self) -> None:
        """Requeue interrupted work after acquiring the exclusive worker lock.

        Ordinary failed jobs stay failed. This preserves the active queue count;
        no extra job or generation is created by recovery.
        """
        with self._connect() as db:
            db.execute("""UPDATE jobs SET status='queued',execution_mode='resume',
                       error=NULL,updated_at=? WHERE status='running'""", (_now(),))
