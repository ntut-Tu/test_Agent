"""Child process used to test abrupt worker death and disk-only recovery."""

import json
import os
import sys
import time
from pathlib import Path

from codebase_analysis.repositories.checkpoints import open_checkpoints
from codebase_analysis.repositories.sqlite import SqliteJobStore
from codebase_analysis.tasks import AnalysisJobs
from codebase_analysis.worker import AnalysisWorker
from codebase_analysis.workflow import CodebaseAnalysisAgent
from tests.recovery_fixtures import BUILD, CountingModel, bound_collector


def main():
    directory, mode = Path(sys.argv[1]), sys.argv[2]

    class Model(CountingModel):
        def record(self, operation):
            with (directory / 'calls.jsonl').open('a') as stream:
                stream.write(json.dumps(operation) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            if mode == 'crash' and operation == 'tests':
                os._exit(17)

    store = SqliteJobStore(directory / 'jobs.sqlite3')
    store.submit(BUILD)

    def execute(job):
        with open_checkpoints(directory / 'checkpoints.sqlite3') as saver:
            agent = CodebaseAnalysisAgent(bound_collector(), Model([]), checkpointer=saver,
                                          configuration_fingerprint='recovery-fixture-v1')
            return agent.run(job.request.number, build=job.request, thread_id=job.thread_id,
                             resume=job.execution_mode == 'resume')

    jobs = AnalysisJobs(store, execute, provider=BUILD.provider, repository=BUILD.repository, job_name=BUILD.job_name)
    worker = AnalysisWorker(jobs, store, directory / 'worker.lock')
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            job = store.get(BUILD.identity)
            if job.status == 'succeeded':
                return
            if job.status == 'failed':
                raise RuntimeError(job.error)
            time.sleep(0.02)
        raise TimeoutError('Worker did not finish')
    finally:
        worker.stop()


if __name__ == '__main__':
    main()
