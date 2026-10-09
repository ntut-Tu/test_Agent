"""GitLab API transport, pagination and repository reads."""

from __future__ import annotations

from urllib.parse import quote, urlencode

from codebase_analysis.lib.clients.http import HttpClient
from codebase_analysis.lib.errors import RemoteError


class GitLabApi:
    """Share GitLab API configuration across MR and test retrieval adapters."""

    def __init__(
        self, project: str, token: str | None, client: HttpClient,
        api_url: str = "https://gitlab.com/api/v4",
    ) -> None:
        """Configure a GitLab project API connection.

        Args:
            project: Project path or numeric project ID represented as a string.
            token: PRIVATE-TOKEN credential, or None for unauthenticated access.
            client: Shared HTTP transport.
            api_url: API root including /api/v4 for self-managed GitLab.
        """
        self.project = project
        self.api_url = api_url.rstrip("/")
        self.client = client
        self.headers = {"Accept": "application/json"}
        if token:
            self.headers["PRIVATE-TOKEN"] = token

    def root(self, project: str | None = None) -> str:
        """Build an encoded project API URL.

        Args:
            project: Source project override, such as an MR's fork.

        Returns:
            API root for the override or configured project.
        """
        return f"{self.api_url}/projects/{quote(project or self.project, safe='')}"

    def get(self, path: str, project: str | None = None):
        """Fetch a project-relative API resource as JSON.

        Args:
            path: Endpoint path beginning with '/', optionally with a query.
            project: Optional source project override.

        Returns:
            Decoded JSON response.

        Raises:
            RemoteError: Request or JSON decoding fails.
        """
        return self.client.get(self.root(project) + path, self.headers).json()

    def pages(self, path: str, project: str | None = None):
        """Iterate a list endpoint in pages of 100 until a short page is returned.

        Args:
            path: Endpoint path without page or per_page parameters.
            project: Optional source project override.

        Yields:
            Items in API response order.

        Raises:
            RemoteError: Retrieval fails or a page is not a JSON list.
        """
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            items = self.get(f"{path}{separator}per_page=100&page={page}", project)
            if not isinstance(items, list):
                raise RemoteError("Expected a paginated GitLab list")
            yield from items
            if len(items) < 100:
                return
            page += 1

    def read_source(self, revision: str, path: str, repository: str | None = None) -> str:
        """Return UTF-8 source for path at revision, including source forks."""
        url = (
            f"{self.root(repository)}/repository/files/{quote(path, safe='')}/raw?"
            f"{urlencode({'ref': revision})}"
        )
        return self.client.get(url, self.headers).body.decode("utf-8")

    def tree(self, revision: str, project: str | None = None):
        """Iterate all repository tree pages pinned to the source revision."""
        query = urlencode({"recursive": "true", "ref": revision})
        return self.pages(f"/repository/tree?{query}", project)

    def read_file(self, path: str, revision: str, project: str | None = None) -> str:
        """Decode raw test contents as UTF-8 with replacement for invalid bytes."""
        response = self.client.get(
            f"{self.root(project)}/repository/files/{quote(path, safe='')}/raw?{urlencode({'ref': revision})}",
            self.headers,
        )
        return response.body.decode("utf-8", errors="replace")

    def pull_request(self, number: int) -> tuple[dict, list[dict]]:
        """Read MR metadata and diffs, rejecting incomplete diff responses."""
        data = self.get(f"/merge_requests/{number}")
        changes = list(self.pages(f"/merge_requests/{number}/diffs"))
        if any(item.get("collapsed") or item.get("too_large") for item in changes):
            raise RemoteError("GitLab returned an incomplete merge request diff")
        return data, changes
