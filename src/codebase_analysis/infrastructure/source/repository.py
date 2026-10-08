"""Read source text from the PR/MR source repository at its exact commit."""

import base64
from urllib.parse import quote, urlencode

from codebase_analysis.domain.models import PullRequest
from codebase_analysis.infrastructure.code_hosts.api import GitHubApi, GitLabApi
from codebase_analysis.infrastructure.errors import RemoteError


class GitHubSourceReader:
    """Read individual source files through the GitHub contents API."""

    def __init__(self, api: GitHubApi) -> None:
        """Inject the authenticated repository API client."""
        self.api = api

    def read(self, pr: PullRequest, path: str) -> str:
        """Return UTF-8 source for path at pr.head_ref, including source forks.

        Raises:
            RemoteError: The API did not return base64 file content.
        """
        data = self.api.get(
            f"/contents/{quote(path, safe='/')}?{urlencode({'ref': pr.head_ref})}", pr.head_repository,
        )
        if data.get("encoding") != "base64":
            raise RemoteError("Source API did not return base64 content")
        return base64.b64decode(data["content"]).decode("utf-8")


class GitLabSourceReader:
    """Read individual source files through the GitLab raw-file API."""

    def __init__(self, api: GitLabApi) -> None:
        """Inject the authenticated project API client."""
        self.api = api

    def read(self, pr: PullRequest, path: str) -> str:
        """Return UTF-8 source for path at pr.head_ref, including source forks."""
        url = (
            f"{self.api.root(pr.head_repository)}/repository/files/{quote(path, safe='')}/raw?"
            f"{urlencode({'ref': pr.head_ref})}"
        )
        return self.api.client.get(url, self.api.headers).body.decode("utf-8")
