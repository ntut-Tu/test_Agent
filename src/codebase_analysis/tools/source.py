"""Read source text from the PR/MR source repository at its exact commit."""


from codebase_analysis.lib.clients.github import GitHubApi
from codebase_analysis.lib.clients.gitlab import GitLabApi
from codebase_analysis.models.pull_request import PullRequest


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
        return self.api.read_source(pr.head_ref, path, pr.head_repository)


class GitLabSourceReader:
    """Read individual source files through the GitLab raw-file API."""

    def __init__(self, api: GitLabApi) -> None:
        """Inject the authenticated project API client."""
        self.api = api

    def read(self, pr: PullRequest, path: str) -> str:
        """Return UTF-8 source for path at pr.head_ref, including source forks."""
        return self.api.read_source(pr.head_ref, path, pr.head_repository)
