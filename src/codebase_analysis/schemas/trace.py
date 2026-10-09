"""Versioned Java trace wire contract."""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)


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
