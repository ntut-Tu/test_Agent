"""ASGI composition root; bind the controller, job store, worker and Agent."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from codebase_analysis.bootstrap import build_agent, settings_for_build
from codebase_analysis.controller import analysis_router
from codebase_analysis.repositories.checkpoints import open_checkpoints
from codebase_analysis.repositories.sqlite import SqliteJobStore
from codebase_analysis.settings import Settings, SettingsError, load_settings
from codebase_analysis.tasks import AnalysisJobs
from codebase_analysis.worker import AnalysisWorker


def create_app(settings: Settings | None = None, *, analyze=None) -> FastAPI:
    """Create one ASGI app; injected analysis enables tests without model calls."""
    settings = settings or load_settings(os.environ.get('AGENT_VALUES', 'values.yaml'))
    token = settings.service.api_token.get_secret_value()
    if len(token) < 32 or not settings.jenkins.base_url:
        raise SettingsError('HTTP service requires service.api_token (32+ chars) and jenkins.base_url')
    data = Path(settings.service.data_directory)
    store = SqliteJobStore(data / 'jobs.sqlite3', settings.service.max_pending)

    def run(job):
        if analyze is not None:
            return analyze(job.request)
        with open_checkpoints(data / 'checkpoints.sqlite3') as saver:
            agent = build_agent(settings_for_build(settings, job.request), checkpointer=saver)
            return agent.run(job.request.number, build=job.request, thread_id=job.thread_id,
                             resume=job.execution_mode == 'resume')

    jobs = AnalysisJobs(store, run, provider=settings.code_host.provider,
                        repository=settings.code_host.repository, job_name=settings.jenkins.job_name)
    worker = AnalysisWorker(jobs, store, data / 'worker.lock')

    @asynccontextmanager
    async def lifespan(app):
        worker.start()
        try:
            yield
        finally:
            worker.stop()

    app = FastAPI(title='Test Agent', lifespan=lifespan, root_path=settings.service.root_path,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(analysis_router(jobs, token))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse(status_code=422, content={'detail': [
            {'loc': error['loc'], 'type': error['type']} for error in exc.errors()
        ]})

    @app.get('/health/live')
    def live():
        return {'status': 'ok'}

    @app.get('/health/ready')
    def ready():
        if not worker.ready:
            raise HTTPException(503, 'Worker unavailable')
        return {'status': 'ready'}

    return app
