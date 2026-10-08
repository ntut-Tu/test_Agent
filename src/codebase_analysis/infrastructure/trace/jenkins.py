"""Validate the versioned Java per-test trace artifact contract."""

import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

from codebase_analysis.domain.trace import MethodReference, TestInvocation, TraceReport
from codebase_analysis.infrastructure.errors import RemoteError
from codebase_analysis.infrastructure.http import HttpClient


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _Method(_Record):
    path: str = Field(json_schema_extra={
        "pattern": r"^(?!/)(?!.*(?:^|/)\.{1,2}(?:/|$))[^\\:]+\.java$",
    })
    name: Annotated[str, StringConstraints(min_length=1)]
    line: int = Field(ge=1)
    class_name: Annotated[str, StringConstraints(min_length=1)]

    @field_validator("path")
    @classmethod
    def relative_java_path(cls, value: str) -> str:
        if (
            not value.endswith(".java") or value.startswith("/") or "\\" in value
            or ":" in value or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise ValueError("Expected a repository-relative Java path")
        return value


class _Test(_Record):
    test: _Method
    calls: list[_Method]


class _Trace(_Record):
    schema_version: Literal[1]
    revision: Annotated[str, StringConstraints(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
    coverage_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    build_id: Annotated[str, StringConstraints(min_length=1)]
    scope: Annotated[str, StringConstraints(min_length=1)]
    complete: bool
    tests: list[_Test]


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


class JenkinsTrace:
    """Read a trace artifact using the configured Jenkins authentication."""

    def __init__(self, url: str, client: HttpClient, headers: dict[str, str]) -> None:
        """Inject artifact URL, shared HTTP client and authentication headers."""
        self.url = url
        self.client = client
        self.headers = dict(headers)

    def fetch(self) -> TraceReport:
        """Download and validate the trace artifact; failures propagate."""
        return parse_trace(self.client.get(self.url, self.headers).body)
