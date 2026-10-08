"""Immutable data exchanged by collection, analysis, and validation."""

from __future__ import annotations

from dataclasses import dataclass

from codebase_analysis.domain.context import FocalMethod, SourceMethod, TestContext
from codebase_analysis.domain.trace import TraceReport


@dataclass(frozen=True)
class ChangedFile:
    """One file changed by a PR/MR.

    Attributes:
        path: Repository-relative path on the new side of the diff.
        status: Change kind, such as added, modified, renamed, or removed.
        patch: Unified diff, or None when the host did not supply one.
        previous_path: Original path for a renamed file, otherwise None.
    """

    path: str
    status: str
    patch: str | None
    previous_path: str | None = None


@dataclass(frozen=True)
class PullRequest:
    """Normalized GitHub PR or GitLab merge request.

    Attributes:
        number: Repository-scoped PR number or GitLab MR IID.
        title: Change title.
        description: Change description; empty when absent.
        url: Web URL of the PR/MR.
        head_ref: Source commit SHA used for retrieving existing tests.
        base_ref: Base commit SHA reported by the host.
        files: Changed files supplied by the host.
        head_repository: Source repository name or project ID, including forks.
            None means use the configured repository.
    """

    number: int
    title: str
    description: str
    url: str
    head_ref: str
    base_ref: str
    files: tuple[ChangedFile, ...]
    head_repository: str | None = None


@dataclass(frozen=True)
class FileCoverage:
    """Coverage for a source file, including files with no uncovered lines.

    Attributes:
        path: Source path as recorded in the coverage report.
        uncovered_numbers: One-based line numbers classified as uncovered.
        executable_numbers: All executable line numbers present in the report.
    """

    path: str
    uncovered_numbers: frozenset[int]
    executable_numbers: frozenset[int] = frozenset()


@dataclass(frozen=True)
class CoverageProvenance:
    """CI producer's declaration binding XML bytes to the tested source.

    Attributes:
        revision: Exact tested source commit, never the pre-merge head label
            for a report produced from merged source.
        coverage_sha256: SHA-256 of the archived coverage XML.
        build_id: Jenkins job/build identifier.
        scope: Maven command and test scope used by the producer.
    """

    revision: str
    coverage_sha256: str
    build_id: str
    scope: str


@dataclass(frozen=True)
class CoverageReport:
    """Normalized coverage, independent of the remote artifact format.

    Attributes:
        files: Per-file coverage entries.
        artifact_sha256: Digest of the original XML bytes, when downloaded.
        provenance: Optional CI declaration verified before line matching.
    """

    files: tuple[FileCoverage, ...]
    artifact_sha256: str | None = None
    provenance: CoverageProvenance | None = None


@dataclass(frozen=True)
class UncoveredLine:
    """An uncovered line matched to a changed file.

    Attributes:
        path: Repository-relative changed-file path.
        number: One-based line number in the new revision.
        on_added_line: Whether the supplied patch marks this line as added.
    """

    path: str
    number: int
    on_added_line: bool


@dataclass(frozen=True)
class ExistingTest:
    """A test candidate retrieved from the source revision.

    Attributes:
        path: Repository-relative file path selected by filename heuristics.
        content: Decoded file contents; selection does not imply execution.
    """

    path: str
    content: str


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
