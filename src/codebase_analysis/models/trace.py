"""Observed per-test calls and their provenance."""

from dataclasses import dataclass

from codebase_analysis.models.source import SourceMethod


@dataclass(frozen=True)
class MethodReference:
    """Source location supplied by the trace producer.

    Attributes:
        path: Repository-relative Java source path.
        name: Method name; constructors use their source class name.
        line: One-based source line inside the method, distinguishing overloads.
        class_name: Source-qualified declaring class name, using dots for nesting.
    """

    path: str
    name: str
    line: int
    class_name: str

    def matches(self, method: SourceMethod) -> bool:
        """Return whether the source location belongs to this method."""
        return (
            self.path == method.path and self.name == method.name and self.class_name == method.class_name
            and method.start_line <= self.line <= method.end_line
        )


@dataclass(frozen=True)
class TestInvocation:
    """One executed test and methods observed under that test's identity."""

    test: MethodReference
    calls: tuple[MethodReference, ...]


@dataclass(frozen=True)
class TraceReport:
    """CI trace tied to a source revision and the exact coverage XML bytes.

    Attributes:
        revision: Full source commit SHA used for the recorded execution.
        coverage_sha256: Hash of the corresponding archived coverage artifact.
        build_id: Human-readable CI build identifier, not an authenticated URL.
        scope: Description of the tests/profiles included in the run.
        complete: Whether the producer captured all calls in the stated scope.
        tests: Per-test invocations; flattened transitive calls retain test identity.
    """

    revision: str
    coverage_sha256: str
    build_id: str
    scope: str
    complete: bool
    tests: tuple[TestInvocation, ...]

    def verify(self, revision: str, coverage_sha256: str | None) -> None:
        """Require the trace revision and coverage bytes to match the analysis.

        Raises:
            ValueError: Either identifier is missing or does not match.
        """
        if self.revision != revision:
            raise ValueError("Jenkins trace revision does not match the PR/MR source commit")
        if not coverage_sha256 or self.coverage_sha256 != coverage_sha256:
            raise ValueError("Jenkins trace does not identify the downloaded coverage artifact")
