"""Parse the versioned Jenkins coverage provenance artifact."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from codebase_analysis.domain.models import CoverageProvenance
from codebase_analysis.infrastructure.errors import RemoteError


class CoverageMetadata(BaseModel):
    """Strict wire contract for coverage metadata; also exports JSON Schema."""

    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    schema_version: Literal[1]
    revision: str = Field(pattern=r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
    coverage_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    build_id: str = Field(min_length=1)
    scope: str = Field(min_length=1)


def parse_metadata(payload: bytes) -> CoverageProvenance:
    """Decode producer metadata without exposing invalid remote payloads.

    Args:
        payload: Raw UTF-8 JSON artifact bytes.

    Returns:
        Domain provenance declaring the tested revision and XML digest.

    Raises:
        RemoteError: Invalid JSON or unsupported contract fields.
    """
    try:
        value = CoverageMetadata.model_validate_json(payload)
    except ValidationError:
        raise RemoteError("Invalid coverage metadata artifact") from None
    return CoverageProvenance(value.revision, value.coverage_sha256, value.build_id, value.scope)
