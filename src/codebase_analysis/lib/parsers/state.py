"""Rehydrate persisted dictionaries into the existing analysis dataclasses."""

from pydantic import TypeAdapter, ValidationError

from codebase_analysis.models.analysis import AgentResult, AnalysisResult

_CONTEXT = TypeAdapter(AnalysisResult)
_RESULT = TypeAdapter(AgentResult)


class CheckpointDataError(ValueError):
    """Stored state does not satisfy the current data contract."""


def parse_context(value: dict) -> AnalysisResult:
    """Decode evidence without including stored source text in errors."""
    try:
        return _CONTEXT.validate_python(value)
    except ValidationError:
        raise CheckpointDataError("Invalid persisted analysis context") from None


def parse_result(value: dict) -> AgentResult:
    """Decode a completed result without exposing invalid stored data."""
    try:
        return _RESULT.validate_python(value)
    except ValidationError:
        raise CheckpointDataError("Invalid persisted analysis result") from None
