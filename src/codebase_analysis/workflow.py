"""Sequence collection and the three model analysis operations."""

from __future__ import annotations

from codebase_analysis.collection import CodebaseAnalysis
from codebase_analysis.interfaces import (
    AnalysisModel,
)
from codebase_analysis.lib.rules.validation import validate_findings
from codebase_analysis.models.analysis import AgentResult, LlmFindings
from codebase_analysis.models.task import BuildRequest


class CodebaseAnalysisAgent:
    """Use an LLM to analyze PR, coverage, and existing-test context."""

    def __init__(self, collector: CodebaseAnalysis, model: AnalysisModel) -> None:
        """Compose evidence collection with an analysis model.

        Args:
            collector: Collects the evidence required by all three operations.
            model: Implements summary, uncovered-line, and existing-test analysis.
        """
        self.collector = collector
        self.model = model

    def run(self, number: int, *, build: BuildRequest | None = None) -> AgentResult:
        """Collect evidence, run the three LLM operations, and validate references.

        Args:
            number: Positive repository-scoped PR number or MR IID.
            build: Optional submitted CI identity, verified before model calls.

        Returns:
            Collected context and validated model findings.

        Raises:
            ValueError: number is invalid for the collector.
            InvalidFindingsError: Model findings reference unavailable evidence.

        Collection and model errors propagate without returning a partial result.
        """
        context = self.collector.run(number)
        if build is not None:
            if context.pull_request.head_ref != build.head_sha:
                raise ValueError("PR head changed since the submitted build")
            if context.coverage_provenance is None or context.coverage_provenance.build_id != build.build_id:
                raise ValueError("Coverage belongs to a different build")
            if context.trace is None or context.trace.build_id != build.build_id:
                raise ValueError("Trace belongs to a different build")
        findings = LlmFindings(
            pr_summary=self.model.summarize_pr(context),
            uncovered_line_analysis=self.model.identify_uncovered_lines(context),
            existing_tests=self.model.select_existing_tests(context),
        )
        validate_findings(context, findings)
        return AgentResult(context, findings)
