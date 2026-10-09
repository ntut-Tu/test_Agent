"""Compose the three analysis operations behind the workflow interface."""

from codebase_analysis.lib.clients.langchain import LangChainClient
from codebase_analysis.models.analysis import AnalysisResult, LineFinding
from codebase_analysis.models.source import TestContext
from codebase_analysis.nodes.coverage import identify_uncovered_lines
from codebase_analysis.nodes.existing_tests import select_existing_tests
from codebase_analysis.nodes.pr import summarize_pr


class AnalysisNodes:
    """Share one model client across independently defined analysis operations."""

    def __init__(self, client: LangChainClient) -> None:
        """Inject the model transport used by all operations."""
        self.client = client

    def summarize_pr(self, context: AnalysisResult) -> str:
        """Summarize the collected PR context."""
        return summarize_pr(self.client, context)

    def identify_uncovered_lines(self, context: AnalysisResult) -> tuple[LineFinding, ...]:
        """Explain the collected uncovered candidates."""
        return identify_uncovered_lines(self.client, context)

    def select_existing_tests(self, context: AnalysisResult) -> tuple[TestContext, ...]:
        """Keep observed callers and select model recommendations."""
        return select_existing_tests(self.client, context)
