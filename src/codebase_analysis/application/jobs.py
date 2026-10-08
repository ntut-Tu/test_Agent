"""Submit and execute CI analysis without HTTP or database dependencies."""

import logging
from collections.abc import Callable
from dataclasses import asdict
from typing import Protocol

from codebase_analysis.domain.jobs import AnalysisJob, BuildRequest
from codebase_analysis.domain.models import AgentResult

logger = logging.getLogger(__name__)


class JobStore(Protocol):
    """Persistence port for atomic enqueue/claim and terminal transitions."""

    def submit(self, request: BuildRequest) -> AnalysisJob: ...
    def get(self, identity: str) -> AnalysisJob | None: ...
    def claim(self) -> AnalysisJob | None: ...
    def finish(self, identity: str, result: dict | None, error: str | None) -> None: ...
    def retry(self, identity: str) -> AnalysisJob | None: ...


class AnalysisJobs:
    """Enforce configured scope and coordinate one durable unit of analysis."""

    def __init__(self, store: JobStore, analyze: Callable[[BuildRequest], AgentResult],
                 *, provider: str, repository: str, job_name: str) -> None:
        self.store = store
        self.analyze = analyze
        self.scope = (provider, repository, job_name)

    def submit(self, request: BuildRequest) -> AnalysisJob:
        """Accept only the repository/job configured by the operator."""
        if (request.provider, request.repository, request.job_name) != self.scope:
            raise ValueError("Repository or Jenkins job does not match configured scope")
        return self.store.submit(request)

    def process_next(self) -> bool:
        """Execute one queued job; never expose remote/model exception text."""
        job = self.store.claim()
        if job is None:
            return False
        try:
            result = asdict(self.analyze(job.request))
        except Exception as exc:
            code = type(exc).__name__
            logger.error("Analysis %s failed (%s)", job.id, code)
            self.store.finish(job.id, None, code)
        else:
            self.store.finish(job.id, result, None)
        return True
