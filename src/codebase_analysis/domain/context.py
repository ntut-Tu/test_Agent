"""Java method identities and evidence used to assemble test context."""

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


def group_focal_methods(
    methods: tuple[SourceMethod, ...], lines: dict[str, set[int]],
) -> tuple[tuple[FocalMethod, ...], tuple[tuple[str, int], ...]]:
    """Assign each uncovered line to the smallest enclosing method.

    Args:
        methods: Parsed methods of the changed production files.
        lines: Uncovered changed line numbers keyed by repository path.

    Returns:
        Focal methods and lines outside any identifiable method. Multiple
        same-line methods are treated as ambiguous rather than guessed.
    """
    grouped: dict[SourceMethod, list[int]] = {}
    unassigned = []
    for path, numbers in lines.items():
        for number in sorted(numbers):
            candidates = [m for m in methods if m.path == path and m.start_line <= number <= m.end_line]
            candidates.sort(key=lambda m: m.end_line - m.start_line)
            if not candidates or (
                len(candidates) > 1
                and candidates[0].end_line - candidates[0].start_line
                == candidates[1].end_line - candidates[1].start_line
            ):
                unassigned.append((path, number))
            else:
                grouped.setdefault(candidates[0], []).append(number)
    return (
        tuple(FocalMethod(method, tuple(numbers)) for method, numbers in grouped.items()),
        tuple(unassigned),
    )
