"""Collected evidence and validated analysis output."""

from __future__ import annotations

from dataclasses import dataclass

from codebase_analysis.models.coverage import CoverageProvenance, UncoveredLine
from codebase_analysis.models.pull_request import PullRequest
from codebase_analysis.models.source import (
    ExistingTest,
    FocalMethod,
    SourceMethod,
    TestContext,
)
from codebase_analysis.models.trace import TraceReport


@dataclass(frozen=True)
class AnalysisResult:
    """Collected evidence provided to the three LLM operations.

    Attributes:
        pull_request: Normalized change metadata and patches.
        uncovered_lines: Coverage candidates matched to changed files.
        coverage_unmatched_paths: Changed paths without an unambiguous match.
        existing_tests: Retrieved test candidates, subject to the file limit.
        test_candidates_total: Number of candidates before applying the limit.
        tests_truncated: Whether some candidate files were not retrieved.
        coverage_missing_patch_paths: Matched files without diff data.
        changed_executable_count: Executable changed lines present in coverage.
        covered_changed_count: Covered lines among those changed lines.
        focal_methods: Java methods containing uncovered changed lines.
        test_methods: Declarations parsed from the retrieved test files.
        dynamic_test_contexts: Per-method test associations with trace evidence.
        unassigned_uncovered_lines: Missing lines outside an unambiguous method.
        trace: Optional normalized trace after revision and artifact validation.
        coverage_provenance: Validated coverage producer declaration, when supplied.
    """

    pull_request: PullRequest
    uncovered_lines: tuple[UncoveredLine, ...]
    coverage_unmatched_paths: tuple[str, ...]
    existing_tests: tuple[ExistingTest, ...]
    test_candidates_total: int
    tests_truncated: bool
    coverage_missing_patch_paths: tuple[str, ...] = ()
    changed_executable_count: int = 0
    covered_changed_count: int = 0
    focal_methods: tuple[FocalMethod, ...] = ()
    test_methods: tuple[SourceMethod, ...] = ()
    dynamic_test_contexts: tuple[TestContext, ...] = ()
    unassigned_uncovered_lines: tuple[tuple[str, int], ...] = ()
    trace: TraceReport | None = None
    coverage_provenance: CoverageProvenance | None = None


@dataclass(frozen=True)
class LineFinding:
    """An LLM-selected uncovered line and its explanation.

    Attributes:
        path: Repository-relative path from the supplied coverage candidates.
        number: One-based line number from those candidates.
        reason: Model explanation of the line's relevance.
    """

    path: str
    number: int
    reason: str


@dataclass(frozen=True)
class LlmFindings:
    """Outputs of the three green operations in the architecture diagram.

    Attributes:
        pr_summary: Model-generated summary of the change.
        uncovered_line_analysis: Selected coverage candidates with explanations.
        existing_tests: Per-focal-method test contexts with evidence provenance.
    """

    pr_summary: str
    uncovered_line_analysis: tuple[LineFinding, ...]
    existing_tests: tuple[TestContext, ...]


@dataclass(frozen=True)
class AgentResult:
    """Collected evidence and findings returned after validation.

    Attributes:
        context: Evidence supplied to the analysis model.
        findings: Model output whose line and test references were validated.
    """

    context: AnalysisResult
    findings: LlmFindings
