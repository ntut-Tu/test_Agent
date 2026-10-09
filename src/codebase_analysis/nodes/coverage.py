"""Execute the coverage analysis operation over collected evidence."""

from __future__ import annotations

from dataclasses import asdict

from codebase_analysis.lib.clients.langchain import LangChainClient
from codebase_analysis.models.analysis import AnalysisResult, LineFinding
from codebase_analysis.prompts.coverage import INSTRUCTIONS
from codebase_analysis.schemas.llm import _UncoveredLines


def identify_uncovered_lines(client: LangChainClient, context: AnalysisResult) -> tuple[LineFinding, ...]:
    """Ask the model to select and explain relevant uncovered lines.

    Args:
        client: Shared structured model transport.
        context: Collected evidence. Up to 200 coverage candidates are
            supplied, prioritizing lines added by the change.

    Returns:
        Selected lines and explanations. The application validates their
        references against collected evidence after all model operations.

    Raises:
        RemoteError: A returned value fails local schema validation.

    Provider invocation and structured-output parsing errors also propagate.
    """
    if not context.uncovered_lines:
        return ()
    ranked = sorted(
        context.uncovered_lines,
        key=lambda line: (not line.on_added_line, line.path, line.number),
    )
    result = client.invoke(
        _UncoveredLines,
        INSTRUCTIONS,
        {
            "pull_request": {"title": context.pull_request.title, "url": context.pull_request.url},
            "coverage_candidates_total": len(context.uncovered_lines),
            "coverage_candidates_omitted": max(0, len(ranked) - 200),
            "coverage_candidates": [asdict(line) for line in ranked[:200]],
            "unmatched_changed_paths": context.coverage_unmatched_paths,
            "missing_patch_paths": context.coverage_missing_patch_paths,
            "focal_methods": [
                {"id": focal.method.identity, "source": focal.annotated_source()}
                for focal in context.focal_methods
                if any(line.path == focal.method.path and line.number in focal.uncovered_lines for line in ranked[:200])
            ],
        },
    )
    return tuple(LineFinding(line.path, line.number, line.reason) for line in result.lines)
