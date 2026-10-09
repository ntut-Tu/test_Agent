"""Java declarations and their test context."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SourceMethod:
    """One parsed Java method or constructor at a pinned source revision.

    Attributes:
        path: Repository-relative source path.
        class_name: Package-qualified class name, including nested classes.
        name: Method or constructor name.
        parameters: Source parameter declaration, preserving overload identity.
        start_line: One-based first line including method annotations.
        end_line: Inclusive last line.
        source: Complete declaration and body.
        is_test: Whether standard test annotations or JUnit 3 conventions apply.
        file_context: Full declaring file, including imports, class setup and helpers.
    """

    path: str
    class_name: str
    name: str
    parameters: str
    start_line: int
    end_line: int
    source: str
    is_test: bool
    file_context: str

    @property
    def identity(self) -> str:
        """Return an unambiguous source identifier for model selections."""
        return f"{self.path}::{self.class_name}.{self.name}{self.parameters}@{self.start_line}"


@dataclass(frozen=True)
class FocalMethod:
    """A changed method with uncovered executable lines.

    Attributes:
        method: Parsed method and its source context.
        uncovered_lines: One-based uncovered line numbers inside this method.
    """

    method: SourceMethod
    uncovered_lines: tuple[int, ...]

    def annotated_source(self) -> str:
        """Return source with uncovered lines marked for model analysis."""
        return "\n".join(
            line + (" // UNCOVERED" if number in self.uncovered_lines else "")
            for number, line in enumerate(self.method.source.splitlines(), self.method.start_line)
        )


@dataclass(frozen=True)
class TestContext:
    """A focal method paired with an observed or model-recommended test.

    Attributes:
        focal_id: SourceMethod identity of the production method.
        test: Existing test declaration and full declaring-file context.
        evidence: dynamic for observed calls; llm for a recommendation only.
        reason: Explanation of the association.
    """

    focal_id: str
    test: SourceMethod
    evidence: Literal["dynamic", "llm"]
    reason: str


@dataclass(frozen=True)
class ExistingTest:
    """A test candidate retrieved from the source revision.

    Attributes:
        path: Repository-relative file path selected by filename heuristics.
        content: Decoded file contents; selection does not imply execution.
    """

    path: str
    content: str
