"""Execute the existing_tests analysis operation over collected evidence."""

from __future__ import annotations

from codebase_analysis.lib.clients.langchain import LangChainClient
from codebase_analysis.lib.errors import RemoteError
from codebase_analysis.models.analysis import AnalysisResult
from codebase_analysis.models.source import TestContext
from codebase_analysis.nodes.context import _pr_data
from codebase_analysis.prompts.existing_tests import INSTRUCTIONS
from codebase_analysis.schemas.llm import _ExistingTests


def select_existing_tests(client: LangChainClient, context: AnalysisResult) -> tuple[TestContext, ...]:
    """Keep observed callers and recommend test methods for remaining targets.

    Args:
        client: Shared structured model transport.
        context: Collected Java methods, test declarations and trace evidence.

    Returns:
        Observed contexts and recommendations carrying separate provenance.
        Full declaring files remain attached to selected tests; LLM fallback
        does not establish that a test executed the target method.

    Raises:
        RemoteError: A returned value fails local schema validation.

    Provider invocation and structured-output parsing errors also propagate.
    """
    observed = context.dynamic_test_contexts
    observed_ids = {item.focal_id for item in observed}
    missing = [focal for focal in context.focal_methods if focal.method.identity not in observed_ids]
    candidates = {method.identity: method for method in context.test_methods if method.is_test}
    if not missing or not candidates:
        return observed
    result = client.invoke(
        _ExistingTests,
        INSTRUCTIONS,
        {
            "pull_request": _pr_data(context),
            "test_candidates_total": context.test_candidates_total,
            "tests_truncated": context.tests_truncated,
            "focal_methods": [
                {"focal_id": focal.method.identity, "source": focal.annotated_source()}
                for focal in missing
            ],
            "test_methods": [
                {
                    "test_id": identity, "source": method.source,
                    "file_context": method.file_context[:12000],
                    "file_context_truncated": len(method.file_context) > 12000,
                }
                for identity, method in candidates.items()
            ],
        },
    )
    allowed = {focal.method.identity for focal in missing}
    selected = {}
    for selection in result.selections:
        if selection.focal_id not in allowed or selection.test_id not in candidates:
            raise RemoteError("Model selected an unknown focal or test method")
        key = (selection.focal_id, selection.test_id)
        selected[key] = TestContext(selection.focal_id, candidates[selection.test_id], "llm", selection.reason)
    return (*observed, *selected.values())
