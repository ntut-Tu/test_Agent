"""Run independent read-only checks of remote collection without an LLM."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

from codebase_analysis.application.agent import CodebaseAnalysis
from codebase_analysis.domain.context import group_focal_methods
from codebase_analysis.domain.coverage import (
    CoverageBindingError,
    match_coverage,
    verify_coverage_binding,
)
from codebase_analysis.domain.paths import is_java_test_path


@dataclass(frozen=True)
class SmokeCheck:
    """One check result for the calling interface to display.

    Attributes:
        name: Stable name identifying the checked capability.
        status: PASS, WARN, FAIL, or SKIP.
        detail: Summary counts or an explanation without remote response data.
        error: Captured failure for diagnostic formatting, excluded from repr.
    """

    name: str
    status: Literal["PASS", "WARN", "FAIL", "SKIP"]
    detail: str = ""
    error: Exception | None = field(default=None, repr=False)


class CollectionSmokeTest:
    """Check the collection adapters and their coverage matching together."""

    def __init__(self, collector: CodebaseAnalysis) -> None:
        """Inject the same collector used by the full analysis agent.

        Args:
            collector: Configured PR/MR, coverage, and test-file sources.
        """
        self.collector = collector

    def run(self, number: int) -> Iterator[SmokeCheck]:
        """Check each capability and continue when an independent check fails.

        Args:
            number: Positive PR number or GitLab MR IID.

        Yields:
            Results for PR/MR retrieval, coverage retrieval/parsing, provenance
            verification, existing tests, and coverage matching. Dependent checks are skipped if
            required evidence is unavailable. Empty data is a warning.

        Raises:
            ValueError: number is not positive.
        """
        if number < 1:
            raise ValueError("PR/MR number must be positive")
        pr = None
        report = None
        retrieved_tests = None
        trace = None
        coverage_bound = False
        try:
            pr = self.collector.pull_requests.fetch(number)
        except Exception as exc:
            yield SmokeCheck("pr_fetch", "FAIL", error=exc)
        else:
            yield SmokeCheck("pr_fetch", "PASS", f"changed_files={len(pr.files)}")

        try:
            report = self.collector.coverage.fetch()
        except Exception as exc:
            yield SmokeCheck("coverage_fetch", "FAIL", error=exc)
        else:
            status = "PASS" if report.files else "WARN"
            yield SmokeCheck("coverage_fetch", status, f"coverage_files={len(report.files)}")

        if self.collector.trace is None:
            yield SmokeCheck("trace_fetch", "WARN", "trace_url not configured; dynamic evidence unavailable")
        else:
            try:
                trace = self.collector.trace.fetch()
            except Exception as exc:
                yield SmokeCheck("trace_fetch", "FAIL", error=exc)
            else:
                yield SmokeCheck("trace_fetch", "PASS" if trace.complete else "WARN", f"tests={len(trace.tests)}, complete={trace.complete}")
                if pr is None or report is None:
                    yield SmokeCheck("trace_binding", "SKIP", "PR/MR or coverage retrieval failed")
                else:
                    try:
                        trace.verify(pr.head_ref, report.artifact_sha256)
                    except ValueError:
                        yield SmokeCheck("trace_binding", "FAIL", "revision or coverage SHA-256 mismatch")
                    else:
                        yield SmokeCheck("trace_binding", "PASS", "source revision and coverage artifact verified")

        if pr is None or report is None:
            yield SmokeCheck("coverage_binding", "SKIP", "PR/MR or coverage retrieval failed")
        else:
            try:
                verify_coverage_binding(report, pr.head_ref, trace)
            except CoverageBindingError as exc:
                yield SmokeCheck("coverage_binding", "FAIL", str(exc))
            else:
                coverage_bound = True
                yield SmokeCheck("coverage_binding", "PASS", "PR/MR head and coverage SHA-256 verified")

        if pr is None:
            yield SmokeCheck("existing_tests", "SKIP", "PR/MR retrieval failed")
        else:
            try:
                tests, total = self.collector.tests.fetch(pr, self.collector.max_test_files)
                retrieved_tests = tests
            except Exception as exc:
                yield SmokeCheck("existing_tests", "FAIL", error=exc)
            else:
                status = "PASS" if tests else "WARN"
                yield SmokeCheck(
                    "existing_tests", status,
                    f"retrieved={len(tests)}, candidates={total}, truncated={total > len(tests)}",
                )

        if not coverage_bound:
            yield SmokeCheck("coverage_match", "SKIP", "coverage binding unavailable or failed")
        else:
            try:
                files = pr.files
                if self.collector.source_analyzer is not None:
                    files = tuple(f for f in files if f.path.endswith(".java") and not is_java_test_path(f.path))
                matched = match_coverage(report, files)
            except Exception as exc:
                yield SmokeCheck("coverage_match", "FAIL", error=exc)
            else:
                status = "WARN" if matched.unmatched_paths or matched.missing_patch_paths else "PASS"
                yield SmokeCheck(
                    "coverage_match", status,
                    f"uncovered_lines={len(matched.uncovered_lines)}, "
                    f"unmatched_paths={len(matched.unmatched_paths)}, "
                    f"missing_patches={len(matched.missing_patch_paths)}",
                )
                if self.collector.source_reader is not None and self.collector.source_analyzer is not None:
                    try:
                        by_path: dict[str, set[int]] = {}
                        for line in matched.uncovered_lines:
                            by_path.setdefault(line.path, set()).add(line.number)
                        methods = tuple(
                            method for path in by_path
                            for method in self.collector.source_analyzer.parse(
                                path, self.collector.source_reader.read(pr, path),
                            )
                        )
                        focal, unassigned = group_focal_methods(methods, by_path)
                        parsed_tests = tuple(
                            method for test in (retrieved_tests or ())
                            for method in self.collector.source_analyzer.parse(test.path, test.content)
                        )
                    except Exception as exc:
                        yield SmokeCheck("java_context", "FAIL", error=exc)
                    else:
                        yield SmokeCheck(
                            "java_context", "WARN" if unassigned or retrieved_tests is None else "PASS",
                            f"focal_methods={len(focal)}, test_declarations={len(parsed_tests)}, unassigned_lines={len(unassigned)}",
                        )
