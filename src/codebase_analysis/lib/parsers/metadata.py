"""Normalize coverage producer metadata."""

from pydantic import ValidationError

from codebase_analysis.lib.errors import RemoteError
from codebase_analysis.models.coverage import CoverageProvenance
from codebase_analysis.schemas.metadata import CoverageMetadata


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
