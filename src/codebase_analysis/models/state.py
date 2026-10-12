"""JSON-compatible state persisted between sequential analysis nodes."""

from typing import Any, TypedDict


class AnalysisState(TypedDict, total=False):
    """Persist evidence and node outputs, never clients or settings objects.

    The dictionaries use the existing dataclass field names. Rehydration is
    centralized in the state parser; checkpoints do not pickle Python objects.
    """

    number: int
    build: dict[str, Any] | None
    context: dict[str, Any]
    pr_summary: str
    uncovered_line_analysis: list[dict[str, Any]]
    existing_tests: list[dict[str, Any]]
    result: dict[str, Any]
