"""Retrieve a Jenkins coverage artifact and normalize its XML."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from codebase_analysis.lib.clients.http import HttpClient
from codebase_analysis.lib.clients.jenkins import JenkinsClient
from codebase_analysis.lib.parsers.coverage import parse_coverage
from codebase_analysis.lib.parsers.metadata import parse_metadata
from codebase_analysis.models.coverage import CoverageReport


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
        self.artifact_url = artifact_url
        self.metadata_url = metadata_url
        self.client = JenkinsClient(client, username, api_token)
        self.headers = self.client.headers

    def fetch(self) -> CoverageReport:
        """Download and normalize the configured coverage artifact.

        Returns:
            Per-file coverage suitable for domain matching.

        Raises:
            RemoteError: Retrieval fails or XML is invalid or unsupported.
            ValueError: A coverage line attribute is not an integer.
            KeyError: A required uncovered-line number is missing.
        """
        payload = self.client.download(self.artifact_url)
        provenance = parse_metadata(self.client.download(self.metadata_url)) if self.metadata_url else None
        return replace(parse_coverage(payload), artifact_sha256=sha256(payload).hexdigest(), provenance=provenance)
