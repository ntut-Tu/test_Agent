"""Execute the pr analysis operation over collected evidence."""

from __future__ import annotations

from codebase_analysis.lib.clients.langchain import LangChainClient
from codebase_analysis.models.analysis import AnalysisResult
from codebase_analysis.nodes.context import _pr_data
from codebase_analysis.prompts.pr import INSTRUCTIONS
from codebase_analysis.schemas.llm import _PrSummary


def summarize_pr(client: LangChainClient, context: AnalysisResult) -> str:
    """Ask the model to summarize PR/MR metadata and changed-file patches.

    Args:
        client: Shared structured model transport.
        context: Collected PR/MR evidence. The prompt includes at most
            30 files, 2,000 characters per patch, and 8,000 description
            characters, with truncation markers.

    Returns:
        Generated summary text.

    Raises:
        RemoteError: A returned value fails local schema validation.

    Provider invocation and structured-output parsing errors also propagate.
    """
    result = client.invoke(
        _PrSummary,
        INSTRUCTIONS,
        {"pull_request": _pr_data(context)},
    )
    return result.summary
