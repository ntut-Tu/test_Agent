"""Bind each submitted build to immutable artifact URLs and an Agent instance."""

from urllib.parse import quote

from codebase_analysis.domain.jobs import BuildRequest
from codebase_analysis.infrastructure.settings import Settings


def settings_for_build(settings: Settings, build: BuildRequest) -> Settings:
    """Derive trusted artifact paths without mutating shared deployment settings."""
    if (build.provider, build.repository, build.job_name) != (
        settings.code_host.provider, settings.code_host.repository, settings.jenkins.job_name,
    ):
        raise ValueError('Build is outside configured repository/job scope')
    if not settings.jenkins.base_url:
        raise ValueError('jenkins.base_url is required for automatic build analysis')
    path = '/'.join('job/' + quote(part, safe='') for part in build.job_name.split('/'))
    base = f'{settings.jenkins.base_url.rstrip("/")}/{path}/{build.build_number}/artifact/agent-analysis'
    jenkins = settings.jenkins.model_copy(update={
        'artifact_url': f'{base}/jacoco.xml',
        'metadata_url': f'{base}/coverage-metadata.json',
        'trace_url': f'{base}/java-test-trace.json',
    })
    return settings.model_copy(update={'jenkins': jenkins})
