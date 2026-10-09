"""Coordinate deterministic remote evidence collection."""

from __future__ import annotations

from codebase_analysis.interfaces import (
    CoverageSource,
    PullRequestFetcher,
    SourceAnalyzer,
    SourceReader,
    TestRetriever,
    TraceSource,
)
from codebase_analysis.lib.rules.context import dynamic_contexts, group_focal_methods
from codebase_analysis.lib.rules.coverage import match_coverage
from codebase_analysis.lib.rules.paths import is_java_test_path
from codebase_analysis.lib.rules.provenance import verify_coverage_binding
from codebase_analysis.models.analysis import AnalysisResult


class CodebaseAnalysis:
    """Compose remote evidence collection, Java parsing and trace matching."""

    def __init__(
        self, pull_requests: PullRequestFetcher, coverage: CoverageSource,
        tests: TestRetriever, max_test_files: int = 20,
        *, source_reader: SourceReader | None = None,
        source_analyzer: SourceAnalyzer | None = None, trace: TraceSource | None = None,
    ) -> None:
        """Configure the collection dependencies.

        Args:
            pull_requests: Source of normalized PR/MR metadata.
            coverage: Source of normalized coverage for the relevant build.
            tests: Retriever for test files at the PR/MR source revision.
            max_test_files: Positive maximum number of test files to retrieve.
            source_reader: Reads production source files at the source SHA.
            source_analyzer: Parses Java methods and test context.
            trace: Optional Jenkins per-test observations.

        Raises:
            ValueError: max_test_files is less than one, or source dependencies
                are not supplied together.
        """
        if max_test_files < 1:
            raise ValueError("max_test_files must be positive")
        self.pull_requests = pull_requests
        self.coverage = coverage
        self.tests = tests
        self.max_test_files = max_test_files
        if (source_reader is None) != (source_analyzer is None):
            raise ValueError("source_reader and source_analyzer must be supplied together")
        self.source_reader = source_reader
        self.source_analyzer = source_analyzer
        self.trace = trace

    def run(self, number: int) -> AnalysisResult:
        """Collect and match evidence without invoking an LLM.

        Args:
            number: Positive repository-scoped PR number or MR IID.

        Returns:
            Change metadata, matched coverage, and bounded test candidates.

        Raises:
            ValueError: number is less than one, coverage provenance is absent,
                or metadata/trace does not match the source commit and XML.

        Errors from injected data sources propagate to the caller.
        """
        if number < 1:
            raise ValueError("PR/MR number must be positive")
        pr = self.pull_requests.fetch(number)
        report = self.coverage.fetch()
        changed_files = pr.files
        if self.source_analyzer is not None:
            changed_files = tuple(f for f in pr.files if f.path.endswith(".java") and not is_java_test_path(f.path))
        trace = self.trace.fetch() if self.trace else None
        verify_coverage_binding(report, pr.head_ref, trace)
        coverage_match = match_coverage(report, changed_files)

        focal_methods = ()
        unassigned = ()
        if self.source_analyzer is not None and self.source_reader is not None:
            methods = []
            lines: dict[str, set[int]] = {}
            for line in coverage_match.uncovered_lines:
                lines.setdefault(line.path, set()).add(line.number)
            for path in lines:
                source = self.source_reader.read(pr, path)
                methods.extend(self.source_analyzer.parse(path, source))
            focal_methods, unassigned = group_focal_methods(tuple(methods), lines)

        if trace is not None:
            traced_paths = tuple(dict.fromkeys(
                invocation.test.path for invocation in trace.tests
                if any(call.matches(focal.method) for call in invocation.calls for focal in focal_methods)
            ))
            tests, candidate_count = self.tests.fetch(pr, self.max_test_files, preferred_paths=traced_paths)
        else:
            tests, candidate_count = self.tests.fetch(pr, self.max_test_files)
        test_methods = tuple(
            method for test in tests for method in self.source_analyzer.parse(test.path, test.content)
        ) if self.source_analyzer is not None else ()
        observed = dynamic_contexts(focal_methods, test_methods, trace) if trace else ()
        uncovered_lines = coverage_match.uncovered_lines
        if self.source_analyzer is not None:
            assigned = {(f.method.path, number) for f in focal_methods for number in f.uncovered_lines}
            uncovered_lines = tuple(line for line in uncovered_lines if (line.path, line.number) in assigned)
        return AnalysisResult(
            pr,
            uncovered_lines,
            coverage_match.unmatched_paths,
            tests,
            candidate_count,
            candidate_count > len(tests),
            coverage_match.missing_patch_paths,
            coverage_match.changed_executable_count,
            coverage_match.covered_changed_count,
            focal_methods, test_methods, observed, unassigned, trace, report.provenance,
        )
