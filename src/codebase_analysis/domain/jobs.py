"""Build identities and durable analysis job state, independent of HTTP/storage."""

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any


@dataclass(frozen=True)
class BuildRequest:
    """An immutable Jenkins build; artifact URLs come from deployment settings."""

    provider: str
    repository: str
    number: int
    head_sha: str
    job_name: str
    build_number: int

    @property
    def build_id(self) -> str:
        return f"{self.job_name}/{self.build_number}"

    @property
    def identity(self) -> str:
        """Deterministic identity makes repeated delivery idempotent."""
        return sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class AnalysisJob:
    """A persisted job with terminal result or a sanitized failure code."""

    id: str
    request: BuildRequest
    status: str
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: str | None = None
