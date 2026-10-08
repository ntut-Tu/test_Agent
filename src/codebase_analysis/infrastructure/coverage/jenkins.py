"""Retrieve a Jenkins coverage artifact and normalize its XML."""

from __future__ import annotations

import base64
from dataclasses import replace
from hashlib import sha256

from codebase_analysis.domain.models import CoverageReport
from codebase_analysis.infrastructure.coverage.metadata import parse_metadata
from codebase_analysis.infrastructure.coverage.xml import parse_coverage
from codebase_analysis.infrastructure.http import HttpClient


class JenkinsCoverage:
    """Read a published JaCoCo or Cobertura XML artifact from a Jenkins build."""

    def __init__(
        self, artifact_url: str, client: HttpClient,
        username: str | None = None, api_token: str | None = None,
        metadata_url: str | None = None,
    ) -> None:
        """Configure the coverage artifact source.

        Args:
            artifact_url: URL of a specific build's coverage XML artifact.
            client: Shared HTTP transport.
            username: Jenkins user for Basic authentication, if needed.
            api_token: Jenkins token, supplied together with username.
            metadata_url: Optional versioned coverage provenance JSON artifact.

        Raises:
            ValueError: Only one authentication field is provided.
        """
        if bool(username) != bool(api_token):
            raise ValueError("Jenkins username and API token must be supplied together")
        self.artifact_url = artifact_url
        self.metadata_url = metadata_url
        self.client = client
        self.headers: dict[str, str] = {}
        if username and api_token:
            encoded = base64.b64encode(f"{username}:{api_token}".encode()).decode("ascii")
            self.headers["Authorization"] = f"Basic {encoded}"

    def fetch(self) -> CoverageReport:
        """Download and normalize the configured coverage artifact.

        Returns:
            Per-file coverage suitable for domain matching.

        Raises:
            RemoteError: Retrieval fails or XML is invalid or unsupported.
            ValueError: A coverage line attribute is not an integer.
            KeyError: A required uncovered-line number is missing.
        """
        response = self.client.get(self.artifact_url, self.headers)
        provenance = parse_metadata(self.client.get(self.metadata_url, self.headers).body) if self.metadata_url else None
        return replace(parse_coverage(response.body), artifact_sha256=sha256(response.body).hexdigest(), provenance=provenance)
