"""GitHub API transport, pagination and repository reads."""

from __future__ import annotations

import base64
from urllib.parse import quote, urlencode

from codebase_analysis.lib.clients.http import HttpClient
from codebase_analysis.lib.errors import RemoteError


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

    def read_source(self, revision: str, path: str, repository: str | None = None) -> str:
        """Return UTF-8 source for path at revision, including source forks.

        Raises:
            RemoteError: The API did not return base64 file content.
        """
        data = self.get(
            f"/contents/{quote(path, safe='/')}?{urlencode({'ref': revision})}", repository,
        )
        if data.get("encoding") != "base64":
            raise RemoteError("Source API did not return base64 content")
        return base64.b64decode(data["content"]).decode("utf-8")

    def tree(self, revision: str, repository: str | None = None) -> list[dict]:
        """List a complete recursive tree at the requested source revision.

        Raises:
            RemoteError: GitHub truncates the recursive tree response.
        """
        commit = self.get(f"/git/commits/{quote(revision, safe='')}", repository)
        tree = self.get(f"/git/trees/{quote(commit['tree']['sha'], safe='')}?recursive=1", repository)
        if tree.get("truncated"):
            raise RemoteError("GitHub repository tree was truncated")
        return tree["tree"]

    def read_blob(self, entry: dict, repository: str | None = None) -> str:
        """Decode a listed blob as UTF-8, replacing invalid byte sequences."""
        blob = self.get(f"/git/blobs/{quote(entry['sha'], safe='')}", repository)
        if blob.get("encoding") != "base64":
            raise RemoteError(f"Unexpected GitHub blob encoding for {entry['path']}")
        return base64.b64decode(blob["content"], validate=False).decode("utf-8", errors="replace")

    def pull_request(self, number: int) -> tuple[dict, list[dict]]:
        """Read PR metadata and complete changed-file pages.

        Raises:
            RemoteError: The listing reaches GitHub's 3,000-file limit.
        """
        data = self.get(f"/pulls/{number}")
        changes = list(self.pages(f"/pulls/{number}/files"))
        if len(changes) >= 3000:
            raise RemoteError("GitHub PR file listing may exceed its 3000-file API limit")
        return data, changes
