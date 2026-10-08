"""SQLite job persistence for a single Agent instance with a mounted volume."""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from codebase_analysis.domain.jobs import AnalysisJob, BuildRequest


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
                           json.loads(row['result']) if row['result'] else None, row['error'])

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
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)', (
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
        """Explicitly retry failures, without rerunning succeeded or active jobs."""
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone()
            if row is not None and row['status'] == 'failed':
                count = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
                if count >= self.max_pending:
                    raise OverflowError('Analysis queue is full')
                db.execute("UPDATE jobs SET status='queued',error=NULL,updated_at=? WHERE id=?", (_now(), identity))
            return self._decode(db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone())

    def interrupt_running(self) -> None:
        """Mark interrupted work failed after acquiring the exclusive worker lock."""
        with self._connect() as db:
            db.execute("UPDATE jobs SET status='failed',error='Interrupted',updated_at=? WHERE status='running'", (_now(),))
