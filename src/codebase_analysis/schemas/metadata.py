"""Versioned coverage provenance wire contract."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CoverageMetadata(BaseModel):
    """Strict wire contract for coverage metadata; also exports JSON Schema."""

    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    schema_version: Literal[1]
    revision: str = Field(pattern=r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
    coverage_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    build_id: str = Field(min_length=1)
    scope: str = Field(min_length=1)
