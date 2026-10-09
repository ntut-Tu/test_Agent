"""Normalize validated Java trace artifacts."""

import json

from pydantic import (
    ValidationError,
)

from codebase_analysis.lib.errors import RemoteError
from codebase_analysis.models.trace import MethodReference, TestInvocation, TraceReport
from codebase_analysis.schemas.trace import _Method, _Trace


def parse_trace(payload: bytes) -> TraceReport:
    """Parse a version-1 trace without exposing payload data on errors.

    Args:
        payload: UTF-8 JSON bytes satisfying the documented artifact contract.

    Returns:
        A normalized per-test trace.

    Raises:
        RemoteError: JSON, schema version, source paths or fields are invalid.
    """
    try:
        value = _Trace.model_validate(json.loads(payload))
    except (ValueError, UnicodeError, ValidationError):
        raise RemoteError("Invalid Jenkins trace artifact; expected Java trace schema version 1") from None

    def reference(method: _Method) -> MethodReference:
        return MethodReference(method.path, method.name, method.line, method.class_name)

    return TraceReport(
        value.revision, value.coverage_sha256, value.build_id, value.scope, value.complete,
        tuple(TestInvocation(reference(t.test), tuple(reference(c) for c in t.calls)) for t in value.tests),
    )
