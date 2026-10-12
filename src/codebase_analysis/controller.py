"""Thin HTTP controller: authentication, DTOs, status codes, and service calls."""

from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from codebase_analysis.models.task import AnalysisJob
from codebase_analysis.schemas.http import SubmitAnalysis
from codebase_analysis.tasks import AnalysisJobs


def job_status(job: AnalysisJob) -> dict:
    return {'id': job.id, 'status': job.status, 'created_at': job.created_at,
            'updated_at': job.updated_at, 'error': job.error,
            'build_id': job.request.build_id, 'head_sha': job.request.head_sha,
            'generation': job.generation, 'execution_mode': job.execution_mode, 'thread_id': job.thread_id}


def analysis_router(jobs: AnalysisJobs, token: str) -> APIRouter:
    """Compose a controller with its application service and authentication."""
    def authenticate(authorization: Annotated[str | None, Header()] = None):
        expected = 'Bearer ' + token
        if authorization is None or not compare_digest(authorization.encode(), expected.encode()):
            raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})

    router = APIRouter(prefix='/analyses', dependencies=[Depends(authenticate)])

    @router.post('', status_code=202)
    def submit(body: SubmitAnalysis, response: Response):
        try:
            job = jobs.submit(body.to_domain())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        except OverflowError:
            raise HTTPException(503, 'Queue is full', headers={'Retry-After': '10'}) from None
        if job.status in {'succeeded', 'failed'}:
            response.status_code = 200
        return job_status(job)

    def existing(identity: str) -> AnalysisJob:
        job = jobs.store.get(identity)
        if job is None:
            raise HTTPException(404, 'Analysis not found')
        return job

    @router.get('/{identity}')
    def status(identity: str):
        return job_status(existing(identity))

    @router.get('/{identity}/result')
    def result(identity: str):
        job = existing(identity)
        if job.status != 'succeeded':
            raise HTTPException(409, 'Analysis has not succeeded')
        return job.result

    @router.post('/{identity}/retry', status_code=202)
    def retry(identity: str):
        try:
            job = jobs.store.retry(identity)
        except OverflowError:
            raise HTTPException(503, 'Queue is full', headers={'Retry-After': '10'}) from None
        if job is None:
            raise HTTPException(404, 'Analysis not found')
        return job_status(job)

    @router.post('/{identity}/restart', status_code=202)
    def restart(identity: str):
        try:
            job = jobs.store.restart(identity)
        except ValueError:
            raise HTTPException(409, 'Cannot restart an active analysis') from None
        except OverflowError:
            raise HTTPException(503, 'Queue is full', headers={'Retry-After': '10'}) from None
        if job is None:
            raise HTTPException(404, 'Analysis not found')
        return job_status(job)

    return router
