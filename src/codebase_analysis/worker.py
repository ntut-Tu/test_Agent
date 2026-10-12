"""Single-process durable queue worker, separate from HTTP request handling."""

import fcntl
from pathlib import Path
from threading import Event, Thread

from codebase_analysis.repositories.sqlite import SqliteJobStore
from codebase_analysis.tasks import AnalysisJobs


class AnalysisWorker:
    """Guard a data volume against multiple workers and process queued builds."""

    def __init__(self, jobs: AnalysisJobs, store: SqliteJobStore, lock_path: Path) -> None:
        self.jobs, self.store, self.lock_path = jobs, store, lock_path
        self.stop_event = Event()
        self.thread = Thread(target=self._run, name='analysis-worker', daemon=True)
        self.lock = None

    def start(self) -> None:
        self.lock = self.lock_path.open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise RuntimeError('Use one Agent instance/worker per data volume') from None
        self.store.recover_running()
        self.thread.start()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            if not self.jobs.process_next():
                self.stop_event.wait(0.5)

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=30)
        # Keep the lock held until process exit if an external model call is still running.
        if not self.thread.is_alive() and self.lock is not None:
            self.lock.close()

    @property
    def ready(self) -> bool:
        return self.thread.is_alive() and not self.stop_event.is_set()
