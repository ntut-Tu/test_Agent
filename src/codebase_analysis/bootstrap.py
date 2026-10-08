"""Composition root: connect settings and infrastructure to the application."""

from langchain.chat_models import init_chat_model

from codebase_analysis.application.agent import CodebaseAnalysis, CodebaseAnalysisAgent
from codebase_analysis.infrastructure.code_hosts.api import GitHubApi, GitLabApi
from codebase_analysis.infrastructure.code_hosts.pr_fetch import (
    GitHubPrFetcher,
    GitLabMrFetcher,
)
from codebase_analysis.infrastructure.code_hosts.test_retriever import (
    GitHubTestRetriever,
    GitLabTestRetriever,
)
from codebase_analysis.infrastructure.coverage.jenkins import JenkinsCoverage
from codebase_analysis.infrastructure.http import HttpClient
from codebase_analysis.infrastructure.llm.langchain import LangChainAnalysisModel
from codebase_analysis.infrastructure.settings import CollectionSettings, Settings
from codebase_analysis.infrastructure.source.java import JavaSourceAnalyzer
from codebase_analysis.infrastructure.source.repository import (
    GitHubSourceReader,
    GitLabSourceReader,
)
from codebase_analysis.infrastructure.trace.jenkins import JenkinsTrace


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


def build_agent(settings: Settings) -> CodebaseAnalysisAgent:
    """Assemble collection and a LangChain model from complete settings.

    Args:
        settings: Parsed values configuration, including model credentials.

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
    return CodebaseAnalysisAgent(collector, LangChainAnalysisModel(chat_model))
