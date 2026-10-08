"""Authenticated repository API access and pagination for GitHub and GitLab."""

from __future__ import annotations

from urllib.parse import quote

from codebase_analysis.infrastructure.errors import RemoteError
from codebase_analysis.infrastructure.http import HttpClient


class GitHubApi:
    """Share GitHub API configuration across PR and test retrieval adapters."""

    def __init__(
        self, repository: str, token: str | None, client: HttpClient,
        api_url: str = "https://api.github.com",
    ) -> None:
        """Configure a GitHub repository API connection.

        Args:
            repository: Repository identifier in owner/repo form.
            token: Bearer token, or None for unauthenticated access.
            client: Shared HTTP transport.
            api_url: API root, optionally overridden for GitHub Enterprise.

        Raises:
            ValueError: repository does not contain exactly two path segments.
        """
        if len(repository.split("/")) != 2:
            raise ValueError("GitHub repository must be owner/repo")
        self.repository = repository
        self.api_url = api_url.rstrip("/")
        self.client = client
        self.headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def root(self, repository: str | None = None) -> str:
        """Build an encoded repository API URL.

        Args:
            repository: Source repository override, such as a PR's fork.

        Returns:
            API root for the override or configured repository.
        """
        return f"{self.api_url}/repos/{quote(repository or self.repository, safe='/')}"

    def get(self, path: str, repository: str | None = None):
        """Fetch a repository-relative API resource as JSON.

        Args:
            path: Endpoint path beginning with '/', optionally with a query.
            repository: Optional source repository override.

        Returns:
            Decoded JSON response.

        Raises:
            RemoteError: Request or JSON decoding fails.
        """
        return self.client.get(self.root(repository) + path, self.headers).json()

    def pages(self, path: str, repository: str | None = None):
        """Iterate a list endpoint in pages of 100 until a short page is returned.

        Args:
            path: Endpoint path without page or per_page parameters.
            repository: Optional source repository override.

        Yields:
            Items in API response order.

        Raises:
            RemoteError: Retrieval fails or a page is not a JSON list.
        """
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            items = self.get(f"{path}{separator}per_page=100&page={page}", repository)
            if not isinstance(items, list):
                raise RemoteError("Expected a paginated GitHub list")
            yield from items
            if len(items) < 100:
                return
            page += 1


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
