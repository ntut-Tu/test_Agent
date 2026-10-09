"""Associate missing lines and observed test calls with source methods."""

from codebase_analysis.models.source import FocalMethod, SourceMethod, TestContext
from codebase_analysis.models.trace import TraceReport


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


def dynamic_contexts(
    focal_methods: tuple[FocalMethod, ...], tests: tuple[SourceMethod, ...], trace: TraceReport,
) -> tuple[TestContext, ...]:
    """Associate methods only through calls observed for a particular test.

    Args:
        focal_methods: Production methods containing uncovered changed lines.
        tests: Parsed declarations from retrieved test files.
        trace: Validated, revision-bound per-test observations.

    Returns:
        Unique observed test associations. Unretrieved or ambiguous test
        locations do not become evidence; callers can use LLM fallback.
    """
    result = {}
    for invocation in trace.tests:
        candidates = [test for test in tests if invocation.test.matches(test)]
        if len(candidates) != 1:
            continue
        test = candidates[0]
        for focal in focal_methods:
            if any(call.matches(focal.method) for call in invocation.calls):
                key = (focal.method.identity, test.identity)
                result[key] = TestContext(
                    focal.method.identity, test, "dynamic",
                    "Observed invocation in a per-test Jenkins trace; this does not prove coverage of the missing lines.",
                )
    return tuple(result.values())
