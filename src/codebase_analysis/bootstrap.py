"""Compose clients, tools, analysis nodes and build-specific settings."""

import json
from hashlib import sha256
from urllib.parse import quote

from langchain.chat_models import init_chat_model
from langgraph.checkpoint.base import BaseCheckpointSaver

from codebase_analysis.collection import CodebaseAnalysis
from codebase_analysis.lib.clients.github import GitHubApi
from codebase_analysis.lib.clients.gitlab import GitLabApi
from codebase_analysis.lib.clients.http import HttpClient
from codebase_analysis.lib.clients.langchain import LangChainClient
from codebase_analysis.lib.parsers.java import JavaSourceAnalyzer
from codebase_analysis.models.task import BuildRequest
from codebase_analysis.nodes.analysis import AnalysisNodes
from codebase_analysis.prompts import coverage as coverage_prompt
from codebase_analysis.prompts import existing_tests, pr
from codebase_analysis.settings import CollectionSettings, Settings
from codebase_analysis.tools.coverage import JenkinsCoverage
from codebase_analysis.tools.existing_tests import (
    GitHubTestRetriever,
    GitLabTestRetriever,
)
from codebase_analysis.tools.pull_request import GitHubPrFetcher, GitLabMrFetcher
from codebase_analysis.tools.source import GitHubSourceReader, GitLabSourceReader
from codebase_analysis.tools.trace import JenkinsTrace
from codebase_analysis.workflow import CodebaseAnalysisAgent


def build_collector(settings: CollectionSettings) -> CodebaseAnalysis:
    """Assemble remote collection without constructing or calling a model.

    Args:
        settings: Validated code host, Jenkins, and collection settings.

    Returns:
        Collector using the same remote adapters as the full agent.

    Raises:
        ValueError: Repository or collection settings are invalid.
    """
    if not settings.jenkins.artifact_url:
        raise ValueError("Select a Jenkins build before constructing the collector")
    client = HttpClient()
    host = settings.code_host
    token = host.token.get_secret_value() or None
    if host.provider == "github":
        api = GitHubApi(host.repository, token, client, host.api_url or "https://api.github.com")
        pull_requests = GitHubPrFetcher(api)
        tests = GitHubTestRetriever(api, suffix=".java")
        source_reader = GitHubSourceReader(api)
    else:
        api = GitLabApi(host.repository, token, client, host.api_url or "https://gitlab.com/api/v4")
        pull_requests = GitLabMrFetcher(api)
        tests = GitLabTestRetriever(api, suffix=".java")
        source_reader = GitLabSourceReader(api)

    coverage = JenkinsCoverage(
        settings.jenkins.artifact_url,
        client,
        metadata_url=settings.jenkins.metadata_url,
        username=settings.jenkins.username or None,
        api_token=settings.jenkins.api_token.get_secret_value() or None,
    )
    return CodebaseAnalysis(
        pull_requests, coverage, tests, max_test_files=settings.analysis.max_test_files,
        source_reader=source_reader, source_analyzer=JavaSourceAnalyzer(),
        trace=JenkinsTrace(settings.jenkins.trace_url, client, coverage.headers) if settings.jenkins.trace_url else None,
    )


def build_agent(settings: Settings, *, checkpointer: BaseCheckpointSaver | None = None) -> CodebaseAnalysisAgent:
    """Assemble collection and a LangChain model from complete settings.

    Args:
        settings: Parsed values configuration, including model credentials.
        checkpointer: Optional saver whose connection lifetime is managed by the caller.

    Returns:
        Agent ready to run analysis. Construction does not collect evidence.

    Raises:
        ImportError: The selected model provider package is not installed.
        ValueError: Repository or model initialization settings are invalid.

    Other provider initialization errors propagate to the caller.
    """
    collector = build_collector(settings)
    options = dict(settings.llm.options)
    if settings.llm.api_key.get_secret_value():
        options["api_key"] = settings.llm.api_key.get_secret_value()
    chat_model = init_chat_model(
        settings.llm.model, model_provider=settings.llm.provider, **options,
    )
    return CodebaseAnalysisAgent(
        collector, AnalysisNodes(LangChainClient(chat_model)), checkpointer=checkpointer,
        configuration_fingerprint=analysis_fingerprint(settings),
    )


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


def analysis_fingerprint(settings: Settings) -> str:
    """Identify settings and prompts that cannot be mixed during resume.

    Only the digest is persisted. Credentials in named secret fields are excluded
    so credential rotation does not invalidate progress. Provider options are
    hashed, never stored as checkpoint metadata.
    """
    inputs = {
        'provider': settings.llm.provider, 'model': settings.llm.model,
        'options': settings.llm.options,
        'collection': settings.analysis.model_dump(mode='json'),
        'code_host': settings.code_host.model_dump(mode='json', exclude={'token'}),
        'jenkins': settings.jenkins.model_dump(mode='json', exclude={'username', 'api_token'}),
        'prompts': [pr.INSTRUCTIONS, coverage_prompt.INSTRUCTIONS, existing_tests.INSTRUCTIONS],
    }
    return sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
